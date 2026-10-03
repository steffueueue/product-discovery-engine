from datetime import date, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from product_discovery_engine.domain.common import Provenance, SourceReference
from product_discovery_engine.domain.evidence import (
    Evidence,
    EvidenceDirection,
    EvidenceTarget,
    Freshness,
    FreshnessPolicy,
)


@pytest.fixture
def evidence(source: SourceReference, provenance: Provenance) -> Evidence:
    return Evidence(
        id=UUID(int=4),
        hypothesis_id=UUID(int=10),
        statement="Setup failed for 4 users",
        source=source,
        collected_on=date(2026, 1, 1),
        target=EvidenceTarget.PROBLEM,
        direction=EvidenceDirection.SUPPORTS,
        methodology_notes="Observed moderated setup",
        provenance=provenance,
    )


@pytest.mark.parametrize("direction", list(EvidenceDirection))
def test_direction_preserved(evidence: Evidence, direction: EvidenceDirection) -> None:
    value = Evidence.model_validate({**evidence.model_dump(), "direction": direction})
    assert value.direction == direction


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (0, Freshness.CURRENT),
        (29, Freshness.CURRENT),
        (30, Freshness.REVIEW_DUE),
        (89, Freshness.REVIEW_DUE),
        (90, Freshness.STALE),
        (100, Freshness.STALE),
    ],
)
def test_freshness_boundaries(evidence: Evidence, days: int, expected: Freshness) -> None:
    policy = FreshnessPolicy(version=1, review_after_days=30, stale_after_days=90)
    assert (
        evidence.freshness(as_of=evidence.collected_on + timedelta(days=days), policy=policy)
        == expected
    )


def test_review_resets_clock_and_policy_is_explicit(evidence: Evidence) -> None:
    reviewed = Evidence.model_validate({**evidence.model_dump(), "reviewed_on": date(2026, 3, 1)})
    assert (
        reviewed.freshness(
            as_of=date(2026, 3, 5),
            policy=FreshnessPolicy(version=2, review_after_days=3, stale_after_days=10),
        )
        == Freshness.REVIEW_DUE
    )
    assert (
        reviewed.freshness(
            as_of=date(2026, 3, 5),
            policy=FreshnessPolicy(version=1, review_after_days=30, stale_after_days=90),
        )
        == Freshness.CURRENT
    )


def test_invalidation_precedes_freshness(evidence: Evidence) -> None:
    value = Evidence.model_validate(
        {
            **evidence.model_dump(),
            "invalidated_on": date(2026, 1, 2),
            "invalidation_reason": "Source corrected the observation",
        }
    )
    assert (
        value.freshness(
            as_of=date(2026, 1, 2),
            policy=FreshnessPolicy(version=1, review_after_days=30, stale_after_days=90),
        )
        == Freshness.INVALIDATED
    )
    assert evidence.invalidated_on is None


@pytest.mark.parametrize(
    "patch",
    [
        {"reviewed_on": date(2025, 12, 31)},
        {"invalidated_on": date(2026, 1, 2)},
        {"invalidation_reason": "missing date"},
        {"target": EvidenceTarget.ASSUMPTION},
        {"target_assumption_id": UUID(int=5)},
    ],
)
def test_invalid_evidence_states(evidence: Evidence, patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate({**evidence.model_dump(), **patch})


def test_primary_source_must_match_provenance(evidence: Evidence) -> None:
    with pytest.raises(ValidationError, match="primary source"):
        Evidence.model_validate(
            {
                **evidence.model_dump(),
                "source": {**evidence.source.model_dump(), "reference": "different-source"},
            }
        )


@pytest.mark.parametrize(("review", "stale"), [(30, 30), (90, 30), (-1, 90), (0, 0)])
def test_invalid_policy(review: int, stale: int) -> None:
    with pytest.raises(ValidationError):
        FreshnessPolicy(version=1, review_after_days=review, stale_after_days=stale)


def test_historical_freshness_requires_historical_snapshot(evidence: Evidence) -> None:
    policy = FreshnessPolicy(version=1, review_after_days=30, stale_after_days=90)
    with pytest.raises(ValueError):
        evidence.freshness(as_of=date(2025, 1, 1), policy=policy)
    for patch in (
        {"reviewed_on": date(2026, 2, 1)},
        {"invalidated_on": date(2026, 2, 1), "invalidation_reason": "Invalid sample"},
    ):
        value = Evidence.model_validate({**evidence.model_dump(), **patch})
        with pytest.raises(ValueError):
            value.freshness(as_of=date(2026, 1, 2), policy=policy)


def test_ai_summary_cannot_replace_primary_evidence(evidence: Evidence) -> None:
    data = evidence.model_dump()
    data["source"]["source_type"] = "ai_summary"
    data["provenance"]["sources"] = (data["source"], *data["provenance"]["sources"])
    with pytest.raises(ValidationError, match="AI summary"):
        Evidence.model_validate(data)


def test_ai_summary_alone_does_not_establish_provenance() -> None:
    with pytest.raises(ValidationError, match="underlying source"):
        Provenance.model_validate(
            {
                "sources": [
                    {"source_type": "ai_summary", "reference": "summary:42"},
                ],
                "ai_generated": True,
            }
        )


def test_ai_assistance_retains_underlying_source_and_contradiction(evidence: Evidence) -> None:
    summary = SourceReference.model_validate(
        {"source_type": "ai_summary", "reference": "summary:42"}
    )
    provenance = Provenance(sources=(evidence.source, summary), ai_generated=True)
    assisted = Evidence.model_validate(
        {
            **evidence.model_dump(),
            "provenance": provenance,
            "direction": EvidenceDirection.CONTRADICTS,
        }
    )
    assert assisted.source == evidence.source
    assert assisted.provenance.ai_generated
    assert summary in assisted.provenance.sources
    assert assisted.direction == EvidenceDirection.CONTRADICTS


def test_zero_day_review_threshold_is_explicitly_supported(evidence: Evidence) -> None:
    assert (
        evidence.freshness(
            as_of=evidence.collected_on,
            policy=FreshnessPolicy(version=1, review_after_days=0, stale_after_days=1),
        )
        == Freshness.REVIEW_DUE
    )


def test_freshness_rejects_timestamp_instead_of_calendar_date(evidence: Evidence) -> None:
    from datetime import UTC, datetime

    with pytest.raises(ValueError, match="calendar date"):
        evidence.freshness(
            as_of=datetime(2026, 1, 1, tzinfo=UTC),
            policy=FreshnessPolicy(version=1, review_after_days=30, stale_after_days=90),
        )
