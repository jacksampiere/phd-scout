"""Offline tests for scoring's pure logic — no API, no network, no mocking.

Covers the two pieces of scoring that live in code (not the model): the §3
surfacing decision (``decide_surface``), the defensive JSON parser
(``parse_response``), and the fatal-vs-skip error classifier
(``_raise_if_fatal``). The model call itself is not tested here — it needs a
live API and belongs to manual calibration, not the offline suite.
"""

from __future__ import annotations

import pytest

from phd_scout import scoring


class _FakeAPIError(Exception):
    """Duck-types what ``_raise_if_fatal`` reads off an anthropic error.

    The classifier only touches ``status_code`` and ``str(exc)``, so a plain
    exception carrying those is enough to exercise every branch without
    constructing (and coupling to) the SDK's response-backed error types.
    """

    def __init__(self, status_code: int | None, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_decide_surface_covers_all_three_section3_rules() -> None:
    # Rule 1 — the sweet spot: A>=3 and B>=2.
    assert scoring.decide_surface(domain_fit=3, robustness=2, in_core_domain=False)
    # Rule 2 — strong domain fit surfaces regardless of robustness: A>=4.
    assert scoring.decide_surface(domain_fit=4, robustness=0, in_core_domain=False)
    # Rule 3 — novel robustness form worth learning from: B>=4 AND in core domain.
    assert scoring.decide_surface(domain_fit=1, robustness=4, in_core_domain=True)

    # Clear skip — high robustness but OUTSIDE the core (biomedical) domain, so
    # rule 3's gate blocks it and nothing else clears.
    assert not scoring.decide_surface(domain_fit=2, robustness=4, in_core_domain=False)
    # Clear skip — nothing reaches any threshold.
    assert not scoring.decide_surface(domain_fit=1, robustness=1, in_core_domain=True)


def test_parse_response_handles_clean_fenced_and_garbage() -> None:
    payload = (
        '{"domain_fit": 4, "robustness": 3, '
        '"robustness_forms": ["hard-to-acquire data / access as a moat"], '
        '"in_core_domain": true, "justification": "Strong biosignal SSL fit."}'
    )
    clean = scoring.parse_response(payload)
    assert clean is not None
    assert clean["domain_fit"] == 4
    assert clean["robustness_forms"] == ["hard-to-acquire data / access as a moat"]
    assert clean["in_core_domain"] is True

    # A ```json fenced block parses identically to the bare object.
    assert scoring.parse_response("```json\n" + payload + "\n```") == clean

    # Prose wrapped around the object is tolerated (outermost braces isolated).
    chatty = scoring.parse_response("Here you go:\n" + payload + "\nHope that helps")
    assert chatty == clean

    # Malformed / incomplete / empty input returns None, never raises.
    assert scoring.parse_response("not json at all") is None
    assert scoring.parse_response('{"domain_fit": 4}') is None  # missing fields
    assert scoring.parse_response("") is None
    assert scoring.parse_response(None) is None


def test_raise_if_fatal_classifies_fatal_vs_per_listing_errors() -> None:
    # 401 auth and 403 permission are always fatal.
    with pytest.raises(scoring.FatalScoringError):
        scoring._raise_if_fatal(_FakeAPIError(401, "invalid x-api-key"))
    with pytest.raises(scoring.FatalScoringError):
        scoring._raise_if_fatal(_FakeAPIError(403, "forbidden"))

    # A 400 is fatal only when it's a billing/credit-exhaustion error.
    with pytest.raises(scoring.FatalScoringError):
        scoring._raise_if_fatal(_FakeAPIError(400, "Your credit balance is too low"))

    # A non-billing 400 is a per-listing problem — return without raising.
    assert scoring._raise_if_fatal(_FakeAPIError(400, "listing text too long")) is None
    # Rate limits and 5xx have no fatal status → per-listing skip, no raise.
    assert scoring._raise_if_fatal(_FakeAPIError(429, "rate limited")) is None
    assert scoring._raise_if_fatal(_FakeAPIError(500, "internal server error")) is None
    assert scoring._raise_if_fatal(_FakeAPIError(None, "connection reset")) is None
