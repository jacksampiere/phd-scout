"""Job-board fetchers for phd_scout.

Each fetcher returns a list of normalized listings shaped as::

    {"id", "title", "url", "description", "source", "date"}

Fetchers degrade gracefully: any fetcher that errors logs a warning and returns
an empty list, so a dead or blocked board never crashes the run.

Live-verified 2026-06-16:
  - Nature Careers: real RSS feed. The ``countrycode`` / ``query`` params are
    ignored by the server (it returns the latest ~20 jobs globally), so we fetch
    once and let downstream scoring handle keyword + geography filtering.
  - EURAXESS: the old ``api.euraxess.ec.europa.eu`` host is dead, detail pages are
    JS-rendered, and the search-results page is keyword-blind — its server-rendered
    HTML returns the latest ~10 jobs regardless of ``keywords`` (filtering happens
    client-side via a JS/AJAX path that needs a headless browser). So we fetch the
    latest listings and rely on downstream scoring to filter. See ``fetch_euraxess``.
  - jobs.ac.uk: the RSS feed is defunct (``format=rss`` returns HTML); the search
    page server-renders listings, so we parse those.
  - FindAPhD: hard Cloudflare-blocked (403 "Just a moment...") on every endpoint,
    even with a browser User-Agent. The fetcher logs and skips; the digest should
    carry a manual-check link instead.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import quote_plus, urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# --- Config (edit here) ----------------------------------------------------

# Browser-like UA: EURAXESS and Nature reject the default requests UA.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_TIMEOUT = 20  # seconds

# Keyword queries for the keyword-driven sources (EURAXESS, jobs.ac.uk).
# Results are deduped per source, so overlap between keywords is harmless.
KEYWORDS = [
    "machine learning",
    "deep learning",
    "representation learning",
    "biosignal",
    "biology",
]

NATURE_RSS_URL = "https://www.nature.com/naturecareers/jobsrss/"
EURAXESS_BASE = "https://euraxess.ec.europa.eu"
EURAXESS_SEARCH = EURAXESS_BASE + "/jobs/search?keywords={q}"
JOBSACUK_BASE = "https://www.jobs.ac.uk"
# Keyword search lives in the ?keywords= query param. The path form
# (/search/<slug>) silently ignores the term and returns latest jobs.
JOBSACUK_SEARCH = JOBSACUK_BASE + "/search/?keywords={q}"
FINDAPHD_SEARCH = "https://www.findaphd.com/phds/?Keywords=machine+learning"

# --- HTTP + parsing helpers ------------------------------------------------


def _get(url: str, source: str) -> requests.Response | None:
    """GET ``url`` with the configured UA/timeout, or None on any failure."""
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as exc:
        logger.warning("%s: request failed (%s): %s", source, url, exc)
        return None
    if not resp.ok:
        logger.warning("%s: HTTP %s for %s", source, resp.status_code, url)
        return None
    return resp


def _clean(text: str | None, limit: int = 500) -> str:
    """Strip HTML tags, collapse whitespace, and truncate."""
    if not text:
        return ""
    plain = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:limit]


def _find_jobposting(html: str) -> dict | None:
    """Return the schema.org JobPosting object from a page's JSON-LD, or None."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        # JSON-LD may be a single object, a list, or wrapped in @graph.
        candidates = data if isinstance(data, list) else data.get("@graph", [data])
        for obj in candidates:
            if isinstance(obj, dict) and obj.get("@type") == "JobPosting":
                return obj
    return None


# --- Fetchers --------------------------------------------------------------


def fetch_nature() -> list[dict]:
    """Latest Nature Careers jobs via RSS."""
    resp = _get(NATURE_RSS_URL, "Nature Careers")
    if resp is None:
        return []
    feed = feedparser.parse(resp.content)
    listings: list[dict] = []
    for entry in feed.entries:
        link = entry.get("link", "")
        listings.append(
            {
                "id": entry.get("id") or entry.get("guid") or link,
                "title": _clean(entry.get("title"), limit=300),
                "url": link,
                "description": _clean(entry.get("summary")),
                "source": "Nature Careers",
                "date": entry.get("published") or None,
            }
        )
    return listings


def fetch_euraxess() -> list[dict]:
    """Latest EURAXESS jobs from the search-results page.

    The search HTML is keyword-blind (see module docstring): it returns the
    latest ~10 jobs regardless of query, so we fetch once and let downstream
    scoring filter. A single static fetch — no keyword loop, because iterating
    keywords would just re-fetch the same latest jobs.
    """
    resp = _get(EURAXESS_SEARCH.format(q=""), "EURAXESS")
    if resp is None:
        return []
    listings: list[dict] = []
    seen: set[str] = set()
    soup = BeautifulSoup(resp.text, "html.parser")
    for anchor in soup.select('a[href*="/jobs/"]'):
        href = anchor.get("href", "")
        match = re.search(r"/jobs/(\d+)", href)
        if not match:
            continue  # skips nav links like /jobs/search
        job_id = match.group(1)
        title = anchor.get_text(strip=True)
        if not title or job_id in seen:
            continue
        seen.add(job_id)
        # Best-effort context from the surrounding card (employer, posted date).
        parent = anchor.find_parent(["article", "li", "div"])
        desc = _clean(parent.get_text(" ", strip=True)) if parent else title
        listings.append(
            {
                "id": f"euraxess:{job_id}",
                "title": title,
                "url": urljoin(EURAXESS_BASE, href),
                "description": desc or title,
                "source": "EURAXESS",
                "date": None,
            }
        )
    return listings


def _jobsacuk_detail(url: str) -> tuple[str, str | None]:
    """Fetch a jobs.ac.uk detail page → (description, date).

    Uses the page's schema.org JobPosting JSON-LD (description + datePosted +
    employer + location). Returns ("", None) on any failure so the caller can
    fall back to the title — a missing detail page never drops the listing.
    """
    resp = _get(url, "jobs.ac.uk")
    if resp is None:
        return "", None
    posting = _find_jobposting(resp.text)
    if posting is None:
        return "", None
    employer = posting.get("hiringOrganization") or {}
    employer_name = employer.get("name", "") if isinstance(employer, dict) else ""
    location = posting.get("jobLocation") or {}
    if isinstance(location, list):
        location = location[0] if location else {}
    address = location.get("address", {}) if isinstance(location, dict) else {}
    place = address.get("addressLocality", "") if isinstance(address, dict) else ""
    prefix = " — ".join(p for p in (employer_name, place) if p)
    body = _clean(posting.get("description"), limit=1200)
    description = f"{prefix}. {body}" if prefix else body
    return description, posting.get("datePosted") or None


def fetch_jobsacuk() -> list[dict]:
    """jobs.ac.uk jobs: keyword search for candidates, enriched per detail page.

    The search results give id/title/url; each job's detail page carries a
    schema.org JobPosting with the full abstract + date, which we fetch so the
    scorer sees more than a bare title. Detail-fetch failures fall back to the
    title (see ``_jobsacuk_detail``).
    """
    candidates: dict[str, dict] = {}  # job_id -> {title, url}
    for keyword in KEYWORDS:
        resp = _get(JOBSACUK_SEARCH.format(q=quote_plus(keyword)), "jobs.ac.uk")
        if resp is None:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for anchor in soup.select('a[href^="/job/"]'):
            href = anchor.get("href", "")
            match = re.match(r"/job/([A-Z0-9]+)", href)
            if not match:
                continue
            job_id = match.group(1)
            title = anchor.get_text(strip=True)
            if not title or job_id in candidates:
                continue
            candidates[job_id] = {"title": title, "url": urljoin(JOBSACUK_BASE, href)}

    listings: list[dict] = []
    for job_id, cand in candidates.items():
        description, date = _jobsacuk_detail(cand["url"])
        listings.append(
            {
                "id": f"jobsacuk:{job_id}",
                "title": cand["title"],
                "url": cand["url"],
                "description": description or cand["title"],
                "source": "jobs.ac.uk",
                "date": date,
            }
        )
    return listings


def fetch_findaphd() -> list[dict]:
    """FindAPhD is Cloudflare-blocked; log and skip.

    The digest carries a manual-check link instead. If the block ever lifts,
    this fetcher will start returning a response and can be built out then.
    """
    resp = _get(FINDAPHD_SEARCH, "FindAPhD")
    if resp is None or "Just a moment" in resp.text:
        logger.warning(
            "FindAPhD: Cloudflare-blocked — skipping; "
            "surface a manual-check link in the digest."
        )
        return []
    # Reachable only if the block lifts; no parser implemented yet.
    logger.info("FindAPhD: now reachable — parser not yet implemented.")
    return []


# --- Registry --------------------------------------------------------------

FETCHERS = {
    "Nature Careers": fetch_nature,
    "EURAXESS": fetch_euraxess,
    "jobs.ac.uk": fetch_jobsacuk,
    "FindAPhD": fetch_findaphd,
}


def fetch_all() -> dict[str, list[dict]]:
    """Run every fetcher, isolating failures so one bad source can't crash the run."""
    results: dict[str, list[dict]] = {}
    for name, fetcher in FETCHERS.items():
        try:
            results[name] = fetcher()
        except Exception as exc:  # belt-and-braces: fetchers also self-guard
            logger.warning("%s: fetcher crashed: %s", name, exc)
            results[name] = []
    return results
