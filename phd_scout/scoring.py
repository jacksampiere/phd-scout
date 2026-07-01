"""Score listings against profile.md via the Claude API.

Contract (per CLAUDE.md): send the full ``profile.md`` rubric plus one listing to
the model and get back structured JSON. The model returns the two score axes, the
robustness forms, an in-core-domain flag, and a justification; the §3 surfacing
decision is computed *here* (``decide_surface``) so the threshold logic lives in
one editable place rather than being delegated to the model.

This module is domain-agnostic: what counts as "in the core domain", which
robustness forms exist, and what the axes mean all live in ``profile.md``, not
here. Retune the search by editing the profile, not this file (the surfacing
thresholds in ``decide_surface`` are the one exception, per the contract).

The model output is parsed defensively — fenced ```json blocks are stripped and
malformed output is skipped (returns ``None``), never raised — so one bad
response can't crash a run.

We deliberately use prompt-and-parse rather than the API's structured-outputs
mode: the rubric is sent as-is and the parser tolerates fences/garbage, matching
the locked scoring contract.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)


class FatalScoringError(RuntimeError):
    """Unrecoverable scoring failure (auth, permission, or exhausted credit).

    Raised when an API error would be identical for every listing, so the run
    should abort loudly rather than silently skip all listings into an empty
    digest. Per-listing problems (a transient blip, one malformed response) are
    skipped instead.
    """


# --- Config (edit here) ----------------------------------------------------

# Default scoring model. Swap to "claude-haiku-4-5" for the cheap path.
SCORING_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
PROFILE_PATH = Path(__file__).resolve().parent.parent / "profile.md"

# Fields the model must return (justification + the two axes + context).
_REQUIRED_FIELDS = ("domain_fit", "robustness", "robustness_forms", "justification")

_SYSTEM_TEMPLATE = """\
You are a research-fit scorer for a PhD-opportunity scout. You are given a
RESEARCH PROFILE (the rubric) and a single JOB LISTING. Score the listing against
the profile and respond with ONLY a JSON object — no prose, no code fences.

Score on two independent 0–5 axes, both defined in the profile's §3:
- domain_fit: integer 0–5 (Component A — the domain-fit axis).
- robustness: integer 0–5 (Component B — the organizing-criterion axis; see §2–§3).

Also return:
- robustness_forms: array of short strings naming which form(s) of the organizing
  criterion (§2) the listing exhibits, using the profile's own names for them. Use
  [] if none. If the listing satisfies the criterion in a way NOT listed in §2,
  name it and prefix the string with "novel: ".
- in_core_domain: boolean — true if the listing falls within the core domain of
  research interest described in the profile (§1–§2), even if its methodological
  fit is weak. This gates one of the §3 surfacing rules; judge it from the
  profile, not from any fixed notion of the field.
- justification: one or two sentences explaining the scores.

Do NOT decide whether to surface the listing — only score it. Respond with exactly
this JSON shape and nothing else:
{{"domain_fit": <int 0-5>, "robustness": <int 0-5>, "robustness_forms": [<str>, ...], \
"in_core_domain": <bool>, "justification": "<str>"}}

=== RESEARCH PROFILE ===
{profile}
"""


# --- Profile + client ------------------------------------------------------


def load_profile(path: Path | str = PROFILE_PATH) -> str:
    """Read the scoring rubric (profile.md)."""
    return Path(path).read_text(encoding="utf-8")


def get_client() -> anthropic.Anthropic:
    """Anthropic client; reads ANTHROPIC_API_KEY from the environment."""
    return anthropic.Anthropic()


# --- §3 surfacing logic (single source of truth) ---------------------------


def decide_surface(domain_fit: int, robustness: int, in_core_domain: bool) -> bool:
    """Mirror profile.md §3 surfacing thresholds. Edit here to retune in code.

    Surface if any of:
      - A >= 3 and B >= 2 (the sweet spot), or
      - A >= 4 (strong domain fit, surface regardless), or
      - B >= 4 and in the core domain (novel robustness form to learn from).
    """
    if domain_fit >= 3 and robustness >= 2:
        return True
    if domain_fit >= 4:
        return True
    if robustness >= 4 and in_core_domain:
        return True
    return False


# --- Response parsing ------------------------------------------------------


def parse_response(text: str | None) -> dict | None:
    """Extract the JSON score object from model text, or None if unparseable.

    Strips ```json fences, isolates the outermost {...}, and json.loads it.
    Returns None on malformed output rather than raising.
    """
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(stripped[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if any(field not in data for field in _REQUIRED_FIELDS):
        logger.warning("scoring: response missing required fields: %s", data)
        return None
    return data


def _normalize(data: dict) -> dict | None:
    """Coerce parsed fields to expected types; return None if scores aren't numeric."""
    try:
        domain_fit = int(data["domain_fit"])
        robustness = int(data["robustness"])
    except (TypeError, ValueError):
        logger.warning("scoring: non-numeric scores: %s", data)
        return None
    forms = data.get("robustness_forms") or []
    if not isinstance(forms, list):
        forms = [str(forms)]
    return {
        "domain_fit": domain_fit,
        "robustness": robustness,
        "robustness_forms": [str(f) for f in forms],
        "in_core_domain": bool(data.get("in_core_domain", False)),
        "justification": str(data.get("justification", "")).strip(),
    }


# --- Scoring ---------------------------------------------------------------

# HTTP statuses that mean the whole run is doomed (bad key / no access).
_FATAL_STATUSES = {401, 403}


def _raise_if_fatal(exc: anthropic.APIError) -> None:
    """Re-raise as FatalScoringError if the error dooms every call; else return.

    Auth (401) and permission (403) are always fatal. A 400 is fatal only when
    it's a billing/credit-exhaustion error (otherwise a 400 is treated as a
    per-listing problem — e.g. one oversized listing). Connection blips, rate
    limits, and 5xx have no fatal status and fall through to per-listing skip.
    """
    status = getattr(exc, "status_code", None)
    message = str(exc).lower()
    if status in _FATAL_STATUSES:
        raise FatalScoringError(f"fatal API error (HTTP {status}): {exc}") from exc
    if status == 400 and ("credit balance" in message or "billing" in message):
        raise FatalScoringError(f"out of API credit (HTTP 400): {exc}") from exc


def _listing_block(listing: dict) -> str:
    return (
        "JOB LISTING\n"
        f"Source: {listing.get('source', '')}\n"
        f"Title: {listing.get('title', '')}\n"
        f"URL: {listing.get('url', '')}\n"
        f"Date: {listing.get('date') or 'unknown'}\n"
        f"Description: {listing.get('description', '')}"
    )


def score_listing(
    listing: dict,
    profile_text: str,
    client: anthropic.Anthropic,
) -> dict | None:
    """Score one listing. Returns the listing merged with scores, or None on failure.

    The returned record adds: domain_fit, robustness, robustness_forms,
    in_core_domain, justification, and the computed `surface` flag.
    """
    system = [
        {
            "type": "text",
            "text": _SYSTEM_TEMPLATE.format(profile=profile_text),
            "cache_control": {"type": "ephemeral"},  # rubric is stable across a run
        }
    ]
    try:
        resp = client.messages.create(
            model=SCORING_MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": _listing_block(listing)}],
        )
    except anthropic.APIError as exc:
        _raise_if_fatal(exc)  # aborts the run on auth/permission/billing errors
        logger.warning("scoring: API error for %s: %s", listing.get("id"), exc)
        return None

    text = next((b.text for b in resp.content if b.type == "text"), None)
    parsed = parse_response(text)
    if parsed is None:
        logger.warning(
            "scoring: unparseable response for %s; skipping", listing.get("id")
        )
        return None
    scores = _normalize(parsed)
    if scores is None:
        return None

    scores["surface"] = decide_surface(
        scores["domain_fit"], scores["robustness"], scores["in_core_domain"]
    )
    return {**listing, **scores}


def score_listings(
    listings: list[dict],
    profile_text: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> list[dict]:
    """Score many listings, skipping any that fail. Returns scored records."""
    if profile_text is None:
        profile_text = load_profile()
    if client is None:
        client = get_client()
    scored: list[dict] = []
    for listing in listings:
        record = score_listing(listing, profile_text, client)
        if record is not None:
            scored.append(record)
    return scored
