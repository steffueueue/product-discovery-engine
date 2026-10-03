from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from product_discovery_engine.application.evidence_validation import (
    EvidenceReviewInput,
    EvidenceValidationService,
)
from product_discovery_engine.domain.audit import EventType
from product_discovery_engine.domain.common import Ordinal, SourceType
from product_discovery_engine.domain.evidence import (
    Evidence,
    EvidenceDirection,
    EvidenceTarget,
    Freshness,
)
from product_discovery_engine.domain.evidence_assessment import (
    EvidenceQualityAssessment,
    EvidenceScope,
    FreshnessRecord,
    QualityInput,
    assess_freshness,
    assess_quality,
    invalidate_evidence,
)
from product_discovery_engine.domain.evidence_origins import (
    EvidenceOrigin,
    OriginKind,
    group_sources,
    link_origins,
)
from product_discovery_engine.domain.evidence_policy import (
    CoverageBasis,
    DirectnessBasis,
    IndependenceBasis,
    ReliabilityBasis,
)
from product_discovery_engine.domain.triangulation import TriangulationCategory, triangulate
from product_discovery_engine.domain.validation_methods import ValidationMethod
from tests.m3_helpers import ACTOR, AT, basis, evidence, knowledge, origin, policies


def quality(item: Evidence, inputs: QualityInput) -> EvidenceQualityAssessment:
    freshness = assess_freshness(
        item,
        policy=policies().freshness,
        actor=ACTOR,
        at=AT,
        assessment_id=uuid4(),
        event_id=uuid4(),
    ).after
    return assess_quality(
        item,
        inputs,
        relevant_evidence=(item,),
        relationships=(origin(item),),
        freshness=freshness,
        policy=policies().quality,
        actor=ACTOR,
        at=AT,
        assessment_id=uuid4(),
        event_id=uuid4(),
    )


@pytest.mark.parametrize("level", list(DirectnessBasis))
def test_directness_rubric(level: DirectnessBasis) -> None:
    item = evidence()
    inputs = QualityInput.model_validate({**basis(item).model_dump(), "directness": level})
    assert quality(item, inputs).directness == policies().quality.directness[level]


@pytest.mark.parametrize("level", list(ReliabilityBasis))
def test_reliability_rubric(level: ReliabilityBasis) -> None:
    item = evidence()
    inputs = QualityInput.model_validate({**basis(item).model_dump(), "reliability": level})
    assert quality(item, inputs).reliability == policies().quality.reliability[level]


@pytest.mark.parametrize("level", list(CoverageBasis))
def test_coverage_rubric(level: CoverageBasis) -> None:
    item = evidence()
    inputs = QualityInput.model_validate({**basis(item).model_dump(), "coverage": level})
    assert quality(item, inputs).coverage == policies().quality.coverage[level]


def test_quality_has_audit_basis_no_count_bonus_and_unknown_is_explicit() -> None:
    item = evidence()
    assessed = quality(item, basis(item))
    assert assessed.aggregate == Ordinal.MEDIUM
    assert assessed.event.event_type == EventType.EVIDENCE_QUALITY_ASSESSED
    assert assessed.input_basis.population_basis
    unknown = QualityInput.model_validate({**basis(item).model_dump(), "reliability": None})
    assert quality(item, unknown).aggregate is None
    with pytest.raises(ValidationError, match="aggregate"):
        EvidenceQualityAssessment.model_validate(
            {**assessed.model_dump(), "aggregate": Ordinal.VERY_HIGH}
        )


def test_rigorous_qualitative_method_not_privileged_or_penalized_by_source_type() -> None:
    interview = evidence(source_type=SourceType.INTERVIEW)
    analytics = evidence(source_type=SourceType.ANALYTICS)
    assert quality(interview, basis(interview)).reliability == Ordinal.VERY_HIGH
    assert (
        quality(interview, basis(interview)).aggregate
        == quality(analytics, basis(analytics)).aggregate
    )


def test_sample_existence_does_not_establish_population_prevalence() -> None:
    existence = evidence()
    frequency = evidence(target=EvidenceTarget.FREQUENCY, population="All customers")
    assert quality(existence, basis(existence)).coverage == Ordinal.MEDIUM
    assert quality(frequency, basis(frequency)).coverage == Ordinal.LOW
    assert "7 of 10" in frequency.statement
    assert quality(frequency, basis(frequency)).input_basis.population_basis


@pytest.mark.parametrize(
    "target",
    [
        EvidenceTarget.REACH,
        EvidenceTarget.FREQUENCY,
        EvidenceTarget.ECONOMICS,
        EvidenceTarget.BUSINESS_IMPACT,
        EvidenceTarget.CAUSAL_MECHANISM,
        EvidenceTarget.SOLUTION,
        EvidenceTarget.DESIRABILITY,
    ],
)
def test_problem_evidence_cannot_validate_other_targets(target: EvidenceTarget) -> None:
    item = evidence()
    scope = EvidenceScope.model_validate({**EvidenceScope.of(item).model_dump(), "target": target})
    assert (
        triangulate(scope, (item,), (origin(item),), policy=policies().triangulation).category
        == TriangulationCategory.NO_EVIDENCE
    )
    with pytest.raises(ValueError, match="exact evidence target"):
        quality(item, QualityInput.model_validate({**basis(item).model_dump(), "scope": scope}))


def test_different_claim_and_population_never_cross_validate() -> None:
    item = evidence()
    for patch in ({"claim_id": UUID(int=999)}, {"population": "All customers"}):
        scope = EvidenceScope.model_validate({**EvidenceScope.of(item).model_dump(), **patch})
        assert (
            triangulate(scope, (item,), (), policy=policies().triangulation).relevant_item_count
            == 0
        )


@pytest.mark.parametrize(
    ("days", "state"), [(0, Freshness.CURRENT), (90, Freshness.REVIEW_DUE), (365, Freshness.STALE)]
)
def test_freshness_thresholds_are_audited(days: int, state: Freshness) -> None:
    item = evidence(collected=date(2026, 1, 1))
    assessed = assess_freshness(
        item,
        policy=policies().freshness,
        actor=ACTOR,
        at=AT.replace(month=1, day=1) + timedelta(days=days),
        assessment_id=uuid4(),
        event_id=uuid4(),
    )
    assert assessed.after.state == state
    assert assessed.event is not None
    assert assessed.event.metadata.reason == assessed.after.reason


def test_freshness_history_explicit_review_historical_context_and_invalidation() -> None:
    item = Evidence.model_validate({**evidence().model_dump(), "review_after": date(2026, 10, 2)})
    first = knowledge((item,), (origin(item),))
    assert first.freshness_records[0].after.state == Freshness.REVIEW_DUE
    second = knowledge((item,), (origin(item),), at=AT + timedelta(days=1), previous=first)
    assert second.freshness_records[0].event is None
    old = evidence(collected=date(2020, 1, 1))
    record = assess_freshness(
        old,
        policy=policies().freshness,
        actor=ACTOR,
        at=AT,
        context="historical",
        assessment_id=uuid4(),
        event_id=uuid4(),
    )
    assert record.after.state == Freshness.REVIEW_DUE
    assert "false" not in record.after.reason or "not declared false" in record.after.reason
    change = invalidate_evidence(
        item, actor=ACTOR, at=AT, reason="Instrumentation error", event_id=uuid4()
    )
    assert change.before.invalidated_on is None
    assert change.event.event_type == EventType.EVIDENCE_INVALIDATED
    invalid = knowledge((change.after,), (origin(change.after),), previous=first)
    assert invalid.freshness_records[0].after.state == Freshness.INVALIDATED
    assert invalid.evidence == (change.after,)
    assert invalid.triangulation.invalidated_evidence_ids == (item.id,)
    with pytest.raises(ValidationError):
        FreshnessRecord.model_validate({**invalid.freshness_records[0].model_dump(), "event": None})
    with pytest.raises(ValueError):
        invalidate_evidence(change.after, actor=ACTOR, at=AT, reason="again", event_id=uuid4())


def test_future_validity_unknown_context_and_naive_time_fail() -> None:
    item = Evidence.model_validate({**evidence().model_dump(), "valid_from": date(2027, 1, 1)})
    with pytest.raises(ValueError, match="not yet valid"):
        knowledge((item,))
    with pytest.raises(ValueError, match="unknown freshness"):
        assess_freshness(
            evidence(),
            policy=policies().freshness,
            actor=ACTOR,
            at=AT,
            context="misspelled",
            assessment_id=uuid4(),
            event_id=uuid4(),
        )
    with pytest.raises(ValueError, match="aware"):
        knowledge((evidence(),), at=AT.replace(tzinfo=None))


def test_three_reports_same_corpus_never_triangulate_or_improve_quality() -> None:
    items = tuple(evidence(n) for n in range(1, 4))
    relations = tuple(
        origin(e, "ticket-corpus", ValidationMethod.SUPPORT_TICKET_ANALYSIS) for e in items
    )
    result = knowledge(items, relations)
    assert result.triangulation.relevant_item_count == 3
    assert result.triangulation.independent_source_group_count == 1
    assert result.triangulation.category == TriangulationCategory.SINGLE_SOURCE
    assert all(q.independence_basis == IndependenceBasis.SHARED_FAMILY for q in result.quality)
    assert all(q.aggregate == Ordinal.LOW for q in result.quality)
    assert all(r.event.event_type == EventType.EVIDENCE_ORIGIN_LINKED for r in relations)


def test_source_overlap_and_transitive_bridges_merge_even_with_different_families() -> None:
    a, b, c = evidence(1), evidence(2), evidence(3)
    ra, rb = origin(a, "a"), origin(b, "b")
    rc = link_origins(
        c,
        (ra.origins[0], rb.origins[0]),
        rationale="Combined report",
        actor=ACTOR,
        at=AT,
        event_id=uuid4(),
    )
    for items in ((a, b, c), (c, a, b), (b, c, a)):
        assert len(group_sources(items, (ra, rb, rc))) == 1
    same_ref = evidence(4, reference=a.source.reference)
    assert len(group_sources((a, same_ref), (ra, origin(same_ref, "different-family")))) == 1


def test_independent_mixed_methods_triangulate_without_claiming_truth() -> None:
    items = tuple(evidence(n) for n in range(1, 4))
    methods = (
        ValidationMethod.CUSTOMER_INTERVIEW,
        ValidationMethod.BEHAVIORAL_ANALYTICS,
        ValidationMethod.SUPPORT_TICKET_ANALYSIS,
    )
    relations = tuple(origin(e, method=m) for e, m in zip(items, methods, strict=True))
    result = knowledge(items, relations)
    assert result.triangulation.category == TriangulationCategory.TRIANGULATED
    assert result.triangulation.independent_method_diversity == 3
    assert all(q.aggregate == Ordinal.MEDIUM for q in result.quality)
    assert "not evidence quality" in result.triangulation.explanation


def test_method_diversity_must_span_independent_groups() -> None:
    a, b, c = evidence(1), evidence(2), evidence(3)
    one = origin(a, "a", ValidationMethod.CUSTOMER_INTERVIEW).origins[0]
    extra = EvidenceOrigin(
        id=uuid4(),
        kind=OriginKind.DATASET,
        family_key="a",
        source_reference="extra:a",
        method=ValidationMethod.BEHAVIORAL_ANALYTICS,
    )
    ra = link_origins(
        a, (one, extra), rationale="Same dataset reanalysis", actor=ACTOR, at=AT, event_id=uuid4()
    )
    result = knowledge((a, b, c), (ra, origin(b), origin(c)))
    assert result.triangulation.independent_method_diversity == 2
    assert result.triangulation.category == TriangulationCategory.MULTIPLE_SOURCES


def test_mixed_evidence_and_stale_contradiction_remain_visible() -> None:
    a = evidence(1)
    b = evidence(2, direction=EvidenceDirection.CONTRADICTS, collected=date(2020, 1, 1))
    result = knowledge((a, b), (origin(a), origin(b)))
    assert result.evidence == (a, b)
    assert result.triangulation.category == TriangulationCategory.MIXED_UNRESOLVED
    assert result.triangulation.supporting_groups and result.triangulation.contradicting_groups
    assert result.freshness_records[1].after.state == Freshness.STALE
    with pytest.raises(ValueError, match="including contradictions"):
        EvidenceValidationService(policies()).assess(
            EvidenceScope.of(a),
            (a, b),
            (),
            (EvidenceReviewInput(evidence_id=a.id, basis=basis(a)),),
            actor=ACTOR,
            at=AT,
        )


def test_unmapped_origins_and_duplicates_cannot_certify_independence() -> None:
    items = (evidence(1), evidence(2), evidence(3))
    result = knowledge(items)
    assert result.triangulation.category == TriangulationCategory.UNRESOLVED_ORIGINS
    assert result.triangulation.independent_source_group_count == 0
    with pytest.raises(ValueError, match="duplicate"):
        knowledge((items[0], items[0]))


def test_reassessment_cannot_remove_contradictions_or_use_future_source_linkage() -> None:
    a = evidence(1)
    b = evidence(2, direction=EvidenceDirection.CONTRADICTS)
    before = knowledge((a, b), (origin(a), origin(b)))
    with pytest.raises(ValueError, match="retain prior evidence"):
        knowledge((a,), previous=before)
    relation = origin(a)
    from product_discovery_engine.domain.evidence_origins import OriginRelationship

    future = OriginRelationship.model_validate(
        {
            **relation.model_dump(),
            "event": {**relation.event.model_dump(), "occurred_at": AT + timedelta(days=1)},
        }
    )
    with pytest.raises(ValueError, match="future"):
        knowledge((a,), (future,))


def test_assessment_requires_claim_reference_even_for_legacy_evidence() -> None:
    with pytest.raises(ValidationError, match="explicit claim"):
        EvidenceScope.of(evidence(claim_id=None))


def test_review_updates_recency_without_rewriting_historical_observations() -> None:
    old = evidence(collected=date(2020, 1, 1))
    before = knowledge((old,), (origin(old),))
    reviewed = Evidence.model_validate({**old.model_dump(), "reviewed_on": date(2026, 10, 3)})
    after = knowledge((reviewed,), (origin(reviewed),), previous=before)
    assert before.freshness_records[0].after.state == Freshness.STALE
    assert after.freshness_records[0].after.state == Freshness.CURRENT
    assert after.freshness_records[0].event is not None
    assert before.evidence[0].statement == after.evidence[0].statement
    assert old.reviewed_on is None


def test_invalidation_precedes_future_validity_metadata() -> None:
    item = Evidence.model_validate(
        {
            **evidence().model_dump(),
            "valid_from": date(2027, 1, 1),
            "invalidated_on": date(2026, 10, 3),
            "invalidation_reason": "Invalid source",
        }
    )
    assert knowledge((item,)).freshness_records[0].after.state == Freshness.INVALIDATED


def test_reassessment_cannot_rewrite_evidence_or_reverse_invalidation() -> None:
    item = evidence()
    before = knowledge((item,))
    rewritten = Evidence.model_validate(
        {**item.model_dump(), "statement": "Replacement observation"}
    )
    with pytest.raises(ValueError, match="rewrite"):
        knowledge((rewritten,), previous=before)
    invalidated = invalidate_evidence(
        item, actor=ACTOR, at=AT, reason="Bad measurement", event_id=uuid4()
    ).after
    invalid = knowledge((invalidated,), previous=before)
    with pytest.raises(ValueError, match="invalidation history"):
        knowledge((item,), previous=invalid)


@pytest.mark.parametrize("direction", list(EvidenceDirection))
def test_aggregation_treats_pure_support_and_disconfirmation_symmetrically(
    direction: EvidenceDirection,
) -> None:
    items = tuple(evidence(n, direction=direction) for n in range(1, 4))
    methods = (
        ValidationMethod.CUSTOMER_INTERVIEW,
        ValidationMethod.BEHAVIORAL_ANALYTICS,
        ValidationMethod.SUPPORT_TICKET_ANALYSIS,
    )
    state = knowledge(
        items, tuple(origin(e, method=m) for e, m in zip(items, methods, strict=True))
    )
    assert state.triangulation.category == TriangulationCategory.TRIANGULATED
    assert state.triangulation.independent_source_group_count == 3
    if direction == EvidenceDirection.CONTRADICTS:
        assert not state.triangulation.supporting_groups
        assert len(state.triangulation.contradicting_groups) == 3
    else:
        assert not state.triangulation.contradicting_groups
        assert len(state.triangulation.supporting_groups) == 3
    assert all(q.aggregate == Ordinal.MEDIUM for q in state.quality)


@pytest.mark.parametrize(
    ("collected", "invalidated", "expected"),
    [
        (date(2026, 10, 1), False, Ordinal.VERY_HIGH),
        (date(2026, 4, 1), False, Ordinal.MEDIUM),
        (date(2020, 1, 1), False, Ordinal.LOW),
        (date(2026, 10, 1), True, Ordinal.VERY_LOW),
    ],
)
def test_recency_dimension_follows_policy(
    collected: date, invalidated: bool, expected: Ordinal
) -> None:
    item = evidence(collected=collected)
    if invalidated:
        item = invalidate_evidence(
            item, actor=ACTOR, at=AT, reason="Source corrected", event_id=uuid4()
        ).after
    state = knowledge((item,), (origin(item),))
    assert state.quality[0].recency == expected


def test_reconstructed_triangulation_cannot_fabricate_counts_or_direction() -> None:
    from product_discovery_engine.application.evidence_validation import KnowledgeState
    from product_discovery_engine.domain.triangulation import TriangulationAssessment

    item = evidence()
    state = knowledge((item,), (origin(item),))
    for patch in (
        {"relevant_item_count": True},
        {"independent_source_group_count": 3},
        {"category": TriangulationCategory.TRIANGULATED},
    ):
        with pytest.raises(ValidationError):
            TriangulationAssessment.model_validate({**state.triangulation.model_dump(), **patch})
    data = state.model_dump()
    data["triangulation"]["contradicting_groups"] = data["triangulation"]["supporting_groups"]
    data["triangulation"]["supporting_groups"] = ()
    with pytest.raises(ValidationError, match="evidence directions"):
        KnowledgeState.model_validate(data)
