"""Entry point: ``python -m phd_scout [--dry-run]``.

Stage 1 wires up the source fetchers and the ``--dry-run`` diagnostic. Scoring,
state, and the email digest land in later stages; until then the default run
falls back to the dry-run view.
"""

from __future__ import annotations

import argparse
import logging

from phd_scout import sources


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
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    if args.dry_run:
        _print_dry_run()
        return

    # Later stages (scoring → state → digest) plug in here. Until then, the full
    # run is the dry-run view so the entrypoint is always exercisable.
    logging.getLogger(__name__).info(
        "Full pipeline not yet implemented; showing dry-run output."
    )
    _print_dry_run()


if __name__ == "__main__":
    main()
