"""Offline tests for digest formatting — no SMTP, no network.

Only ``format_digest`` is exercised; ``send_digest`` is the network boundary and
is left to the live end-to-end send, not the offline suite.
"""

from __future__ import annotations

from datetime import date

from phd_scout import digest
from phd_scout.sources import FINDAPHD_SEARCH


def _rec(**overrides) -> dict:
    base = {
        "title": "PhD in ML for physiological signals",
        "url": "https://example.org/job/1",
        "source": "jobsacuk",
        "date": "2026-06-20",
        "domain_fit": 4,
        "robustness": 3,
        "in_core_domain": True,
        "robustness_forms": ["hard-to-acquire data / access as a moat"],
        "location": "United Kingdom",
        "geo_out_of_scope": False,
        "known": None,
        "position_type": "phd",
        "justification": "Strong biosignal SSL fit.",
        "surface": True,
    }
    base.update(overrides)
    return base


def test_format_digest_renders_known_geo_and_findaphd() -> None:
    known = _rec(title="Wearables PhD", known="Oxford — Wearables Group")
    flagged = _rec(title="ML PhD abroad", geo_out_of_scope=True, location="Singapore")
    subject, text, html = digest.format_digest(
        [known, flagged], today=date(2026, 6, 30)
    )

    assert subject == "PhD Scout — 2 new matches — 2026-06-30"

    # §8: known listings are surfaced and tagged, not suppressed.
    assert "[KNOWN]" in text
    assert "Oxford — Wearables Group" in text
    assert "KNOWN" in html  # the HTML badge

    # §7: out-of-scope geography is flagged (with the location), never filtered.
    assert "geography?" in text
    assert "Singapore" in text
    assert flagged["title"] in text  # still present despite the flag

    # FindAPhD manual-check nudge rides in every digest, both bodies.
    assert FINDAPHD_SEARCH in text
    assert FINDAPHD_SEARCH in html


def test_format_digest_tags_role_type_and_puts_phd_first() -> None:
    # A weaker PhD should still sort above a stronger postdoc (§6b: PhD is target).
    postdoc = _rec(title="strong postdoc", position_type="postdoc", domain_fit=5)
    phd = _rec(title="weaker phd", position_type="phd", domain_fit=3)
    _, text, html = digest.format_digest([postdoc, phd])

    assert text.index("weaker phd") < text.index("strong postdoc")
    assert "[PhD]" in text
    assert "[Postdoc]" in text
    assert "Postdoc" in html  # role badge rendered


def test_format_digest_sorts_strongest_first() -> None:
    weak = _rec(title="weaker", domain_fit=3, robustness=2)
    strong = _rec(title="stronger", domain_fit=5, robustness=4)
    _, text, _ = digest.format_digest([weak, strong])
    assert text.index("stronger") < text.index("weaker")


def test_format_digest_escapes_html_in_titles() -> None:
    _, _, html = digest.format_digest([_rec(title="ML <script> & signals")])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_format_digest_empty_still_carries_reminder() -> None:
    subject, text, html = digest.format_digest([], today=date(2026, 6, 30))
    assert subject == "PhD Scout — 0 new matches — 2026-06-30"
    assert FINDAPHD_SEARCH in text
    assert FINDAPHD_SEARCH in html
