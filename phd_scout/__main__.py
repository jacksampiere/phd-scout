"""Entry point: ``python -m phd_scout [--dry-run | --score | --preview]``.

Diagnostic ladder (per CLAUDE.md's diagnostics-before-automation working style):
``--dry-run`` prints raw listings (no API), ``--score`` prints scores (API, no
email/state), ``--send-test`` emails a synthetic digest (SMTP only, no API),
``--preview`` renders the digest email without sending or touching state, and the
default no-flag run is the full pipeline: fetch → dedup → score → email the
surfaced matches → commit ``seen.json``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable

from dotenv import load_dotenv

from phd_scout import digest, scoring, sources, state


def _print_dry_run() -> None:
    """Fetch every source and print raw normalized listings, grouped by source."""
    all_listings = sources.fetch_all()
    total = 0
    bar = "=" * 72
    for source_name, listings in all_listings.items():
        print(f"\n{bar}\n{source_name}  —  {len(listings)} listing(s)\n{bar}")
        for i, listing in enumerate(listings, 1):
            print(f"\n[{i}] {listing['title']}")
            print(f"    id:   {listing['id']}")
            print(f"    url:  {listing['url']}")
            print(f"    date: {listing['date']}")
            desc = listing["description"] or ""
            suffix = "…" if len(desc) > 200 else ""
            print(f"    desc: {desc[:200]}{suffix}")
        total += len(listings)
    n_sources = len(all_listings)
    print(f"\n{bar}\nTOTAL: {total} listing(s) across {n_sources} source(s)\n{bar}")


def _interleave(all_listings: dict[str, list[dict]]) -> list[dict]:
    """Round-robin across sources so a capped sample spans every board."""
    mixed: list[dict] = []
    columns = [list(v) for v in all_listings.values()]
    while any(columns):
        for col in columns:
            if col:
                mixed.append(col.pop(0))
    return mixed


def _print_scored(limit: int | None) -> None:
    """Fetch, score a (capped) sample, and print scores + justifications."""
    all_listings = sources.fetch_all()
    sample = _interleave(all_listings)
    if limit is not None:
        sample = sample[:limit]
    print(f"Scoring {len(sample)} listing(s) with {scoring.SCORING_MODEL}…\n")

    scored = scoring.score_listings(sample)
    bar = "=" * 72
    surfaced = 0
    for listing in scored:
        flag = "SURFACE" if listing["surface"] else "skip"
        if listing["surface"]:
            surfaced += 1
        forms = ", ".join(listing["robustness_forms"]) or "—"
        print(f"{bar}")
        print(
            f"[{flag}] A={listing['domain_fit']} B={listing['robustness']} "
            f"core={listing['in_core_domain']} type={listing['position_type']}  "
            f"({listing['source']})"
        )
        print(f"  {listing['title']}")
        print(f"  forms: {forms}")
        print(f"  why:   {listing['justification']}")
    failed = len(sample) - len(scored)
    print(f"\n{bar}")
    print(
        f"Scored {len(scored)}/{len(sample)} | surfaced {surfaced} | "
        f"skipped {len(scored) - surfaced} | {failed} failed to parse"
    )
    print(bar)


def _run_pipeline(preview: bool, limit: int | None = None) -> None:
    """Full run: fetch → dedup → score new → email surfaced → commit state.

    Dedup happens *before* scoring so API calls are spent only on listings we
    haven't seen. State is committed only after a clean pass (send succeeded, or
    nothing to send); a ``FatalScoringError`` or SMTP failure aborts before the
    ``seen.json`` write, so the next run retries the same listings. ``preview``
    renders the digest to stdout and sends/commits nothing. ``limit`` caps how
    many new listings are scored (sampled across sources) — handy to bound cost
    while previewing.
    """
    log = logging.getLogger(__name__)
    seen = state.load_seen()
    fetched = _interleave(sources.fetch_all())
    fresh = state.filter_unseen(fetched, seen)
    if limit is not None:
        fresh = fresh[:limit]
    log.info("pipeline: %d fetched, %d new after dedup", len(fetched), len(fresh))
    if not fresh:
        log.info("pipeline: nothing new to score; done.")
        return

    scored = scoring.score_listings(fresh)
    surfaced = [rec for rec in scored if rec["surface"]]
    log.info(
        "pipeline: scored %d/%d, %d surfaced", len(scored), len(fresh), len(surfaced)
    )
    subject, text_body, html_body = digest.format_digest(surfaced)

    if preview:
        print(subject, end="\n\n")
        print(text_body)
        log.info("preview: not sending; state left untouched.")
        return

    if surfaced:
        digest.send_digest(subject, text_body, html_body)
    else:
        log.info("pipeline: no surfaced matches; no email sent.")

    # Reached only on a clean pass — commit the newly-considered listings so we
    # neither re-score nor re-send them next run.
    state.save_seen(state.mark_seen(seen, fresh))
    log.info("pipeline: marked %d listing(s) seen.", len(fresh))


def _send_test() -> None:
    """Send one synthetic digest to verify Gmail SMTP without spending any API.

    Isolates the email boundary (credentials, app password, delivery) from
    fetching and scoring so the two can be debugged independently.
    """
    sample = [
        {
            "title": "TEST — PhD in self-supervised learning for physiological signals",
            "url": "https://example.org/test-listing",
            "source": "send-test",
            "date": "2026-06-30",
            "domain_fit": 5,
            "robustness": 4,
            "in_core_domain": True,
            "robustness_forms": ["hard-to-acquire data / access as a moat"],
            "location": "United Kingdom",
            "geo_out_of_scope": False,
            "known": None,
            "justification": "Synthetic listing sent by --send-test to check delivery.",
        }
    ]
    subject, text_body, html_body = digest.format_digest(sample)
    digest.send_digest(f"[test] {subject}", text_body, html_body)
    print("Test digest sent.")


def _run_guarded(fn: Callable[[], None]) -> None:
    """Run a scoring-backed step, exiting loudly on a fatal (whole-run) error.

    A non-zero exit makes a scheduled job fail visibly (and email you) instead of
    silently producing an empty digest.
    """
    try:
        fn()
    except scoring.FatalScoringError as exc:
        logging.getLogger(__name__).error("Aborting run: %s", exc)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="phd_scout",
        description="Scout PhD opportunities and email a scored digest of matches.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print raw listings per source; no scoring or email.",
    )
    parser.add_argument(
        "--score",
        action="store_true",
        help="Fetch, score listings against profile.md, and print scores. No email.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap how many listings are scored, sampled across sources "
        "(applies to --score and the --preview / full run).",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Run the full pipeline but print the digest instead of sending it; "
        "sends no email and does not update seen.json.",
    )
    parser.add_argument(
        "--send-test",
        action="store_true",
        help="Send one synthetic digest to verify Gmail SMTP. No fetch or scoring.",
    )
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    if args.dry_run:
        _print_dry_run()
        return

    if args.send_test:
        _send_test()
        return

    if args.score:
        _run_guarded(lambda: _print_scored(args.limit))
        return

    _run_guarded(lambda: _run_pipeline(preview=args.preview, limit=args.limit))


if __name__ == "__main__":
    main()
