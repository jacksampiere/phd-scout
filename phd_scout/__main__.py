"""Entry point: ``python -m phd_scout [--dry-run]``.

Stage 1 wires up the source fetchers and the ``--dry-run`` diagnostic. Scoring,
state, and the email digest land in later stages; until then the default run
falls back to the dry-run view.
"""

from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from phd_scout import scoring, sources


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
            f"core={listing['in_core_domain']}  ({listing['source']})"
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
        help="Cap how many listings --score processes (sampled across sources).",
    )
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    if args.dry_run:
        _print_dry_run()
        return

    if args.score:
        try:
            _print_scored(args.limit)
        except scoring.FatalScoringError as exc:
            # Loud, non-zero exit so the scheduled job fails visibly (and emails
            # you) instead of silently producing an empty digest.
            logging.getLogger(__name__).error("Aborting run: %s", exc)
            sys.exit(1)
        return

    # Later stages (scoring → state → digest) plug in here. Until then, the full
    # run is the dry-run view so the entrypoint is always exercisable.
    logging.getLogger(__name__).info(
        "Full pipeline not yet implemented; showing dry-run output."
    )
    _print_dry_run()


if __name__ == "__main__":
    main()
