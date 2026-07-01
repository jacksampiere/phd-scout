"""Offline tests for seen.json state — dedup and round-trip, using tmp_path.

No mocking: these hit a real (temporary) file on disk, exercising the same
read/write path the digest and daily.yml use.
"""

from __future__ import annotations

from phd_scout import state


def test_load_seen_missing_file_is_empty(tmp_path) -> None:
    assert state.load_seen(tmp_path / "does-not-exist.json") == set()


def test_load_seen_malformed_file_degrades_to_empty(tmp_path) -> None:
    bad = tmp_path / "seen.json"
    bad.write_text("{ this is not valid json", encoding="utf-8")
    # A corrupt state file must not crash the run — worst case a duplicate send.
    assert state.load_seen(bad) == set()

    not_a_list = tmp_path / "obj.json"
    not_a_list.write_text('{"seen": ["a"]}', encoding="utf-8")
    assert state.load_seen(not_a_list) == set()


def test_save_then_load_round_trips(tmp_path) -> None:
    path = tmp_path / "seen.json"
    state.save_seen({"b", "a", "c"}, path)
    # Persisted as a sorted array for stable, diff-friendly commits.
    assert path.read_text(encoding="utf-8").startswith("[")
    assert state.load_seen(path) == {"a", "b", "c"}


def test_filter_unseen_drops_known_within_batch_and_idless() -> None:
    seen = {"seen-1"}
    listings = [
        {"id": "seen-1", "title": "already sent"},
        {"id": "new-1", "title": "fresh"},
        {"id": "new-1", "title": "duplicate in same batch"},
        {"id": "new-2", "title": "also fresh"},
        {"title": "no id at all"},
    ]
    fresh = state.filter_unseen(listings, seen)
    assert [x["id"] for x in fresh] == ["new-1", "new-2"]


def test_mark_seen_adds_ids_without_mutating_input() -> None:
    seen = {"old"}
    listings = [{"id": "new-1"}, {"id": "new-2"}, {"title": "idless"}]
    updated = state.mark_seen(seen, listings)
    assert updated == {"old", "new-1", "new-2"}
    assert seen == {"old"}  # original set left untouched
