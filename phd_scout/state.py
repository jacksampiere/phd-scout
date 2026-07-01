"""seen.json state: remember which listings have already been sent.

The digest must never re-send a listing. State is a committed ``seen.json`` (a
plain sorted JSON array of listing ids) that ``daily.yml`` pushes back after each
run. The functions here are pure and side-effect-free except ``save_seen`` — the
dedup logic (``filter_unseen``, ``mark_seen``) takes and returns sets so it is
trivially testable offline without touching disk.

Read is defensive: a missing or malformed ``seen.json`` degrades to "nothing seen
yet" (log + empty set) rather than crashing the run, matching the fail-safe rule.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Committed state file at the repo root, next to profile.md.
STATE_PATH = Path(__file__).resolve().parent.parent / "seen.json"


def load_seen(path: Path | str = STATE_PATH) -> set[str]:
    """Return the set of already-seen listing ids.

    A missing or unreadable/malformed file degrades to an empty set (logged), so
    a corrupt state file can't crash a run — worst case is a one-off duplicate.
    """
    p = Path(path)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        logger.warning("state: could not read %s; treating as empty", p)
        return set()
    if not isinstance(data, list):
        logger.warning("state: %s is not a JSON list; treating as empty", p)
        return set()
    return {str(x) for x in data}


def save_seen(seen: set[str], path: Path | str = STATE_PATH) -> None:
    """Write the seen-id set as a sorted JSON array (stable, diff-friendly)."""
    Path(path).write_text(json.dumps(sorted(seen), indent=2) + "\n", encoding="utf-8")


def filter_unseen(listings: list[dict], seen: set[str]) -> list[dict]:
    """Return listings whose id is not in ``seen`` (also de-dups within the batch).

    Listings without an id are dropped — an un-idable listing can't be tracked, so
    surfacing it would risk re-sending it every run.
    """
    fresh: list[dict] = []
    batch_ids: set[str] = set()
    for listing in listings:
        lid = str(listing.get("id") or "")
        if not lid or lid in seen or lid in batch_ids:
            continue
        batch_ids.add(lid)
        fresh.append(listing)
    return fresh


def mark_seen(seen: set[str], listings: list[dict]) -> set[str]:
    """Return a new seen-set with the ids of ``listings`` added (ids-less skipped)."""
    updated = set(seen)
    for listing in listings:
        lid = str(listing.get("id") or "")
        if lid:
            updated.add(lid)
    return updated
