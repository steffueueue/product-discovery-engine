"""Qualitative sufficiency, explicit applicability, reviewed gaps and immutable history."""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from examples.spec_delivery import SearchSpecification, search_specification
from product_discovery_engine.domain.audit import Actor, ActorKind
from product_discovery_engine.domain.common import Unknown
from product_discovery_engine.domain.spec_completeness import (
    ApplicabilityDecision,
    CompletenessState,
    SpecCompletenessAssessment,
)
from product_discovery_engine.domain.spec_completeness_policy import (
    DimensionState,
    GapClassification,
    SpecCompletenessPolicy,
    SpecDimension,
)
from product_discovery_engine.domain.spec_gaps import GapStatus, GapType, SpecGap
from product_discovery_engine.domain.spec_items import ContentOrigin, SpecItem, SpecItemType
from product_discovery_engine.infrastructure.configuration import load_spec_completeness_policy
from tests.m5_helpers import ACTOR, AT, FakeDraftingProvider


@pytest.fixture(scope="module")
def search() -> SearchSpecification:
    return search_specification()


def test_draft_is_valid_and_completeness_is_separate(search: SearchSpecification) -> None:
    empty = search.drafting.create(search.draft.context, actor=ACTOR, at=AT).after
    assessment = search.delivery.assess(empty, actor=ACTOR, at=AT)
    assert empty.items == () and empty.status.value == "draft"
    assert assessment.result.state == CompletenessState.INCOMPLETE
    assert SpecDimension.ACCEPTANCE in assessment.result.missing_requirements
    assert assessment.result.blocking_gaps


def test_dimensions_and_classification(search: SearchSpecification) -> None:
    assessment = search.delivery.assess(
        search.draft, actor=ACTOR, at=AT, applicability=search.applicability
    )
    dimensions = {r.dimension: r.state for r in assessment.result.dimensions}
    assert dimensions[SpecDimension.INTENT] == DimensionState.SUFFICIENT
    assert dimensions[SpecDimension.SOLUTION] == DimensionState.NOT_APPLICABLE
    assert dimensions[SpecDimension.DATA] == DimensionState.NOT_APPLICABLE
    assert dimensions[SpecDimension.INTERFACES] == DimensionState.UNKNOWN
    assert len(assessment.result.blocking_gaps) == len(assessment.result.non_blocking_gaps) == 1
    assert SpecDimension.INTERFACES in assessment.result.unknown_conditions
    assert (
        SpecCompletenessAssessment.model_validate_json(assessment.model_dump_json()) == assessment
    )


def test_optional_missing_does_not_block(search: SearchSpecification) -> None:
    items = tuple(i for i in search.draft.items if i.kind != SpecItemType.ANALYTICS)
    revision = search.drafting.revise(
        search.draft,
        search.draft.context,
        items,
        actor=ACTOR,
        at=AT,
        reason="Remove optional analytics unknown",
    )
    assessment = search.delivery.assess(
        revision.after, actor=ACTOR, at=AT, applicability=search.applicability
    )
    analytics = next(g for g in assessment.gaps if g.dimension == SpecDimension.ANALYTICS)
    assert analytics.classification == GapClassification.NON_BLOCKING
    assert analytics.gap_type == GapType.MISSING
    assert analytics.id not in assessment.result.blocking_gaps


def test_non_applicable_interface_needs_explicit_human_context(search: SearchSpecification) -> None:
    decisions = tuple(
        ApplicabilityDecision.model_validate({**a.model_dump(), "applicable": False})
        if a.dimension == SpecDimension.INTERFACES
        else a
        for a in search.applicability
    )
    assessment = search.delivery.assess(search.draft, actor=ACTOR, at=AT, applicability=decisions)
    assert assessment.result.state == CompletenessState.COMPLETE
    assert not assessment.result.blocking_gaps
    assert (
        next(
            r for r in assessment.result.dimensions if r.dimension == SpecDimension.INTERFACES
        ).state
        == DimensionState.NOT_APPLICABLE
    )
    missing = search.delivery.assess(search.draft, actor=ACTOR, at=AT)
    assert (
        next(r for r in missing.result.dimensions if r.dimension == SpecDimension.INTERFACES).state
        == DimensionState.UNKNOWN
    )
    wrong = ApplicabilityDecision.model_validate(
        {**decisions[0].model_dump(), "context_fact_id": uuid4()}
    )
    with pytest.raises(ValueError, match="supplied human context"):
        search.delivery.assess(search.draft, actor=ACTOR, at=AT, applicability=(wrong,))
    with pytest.raises(ValueError):
        search.delivery.assess(
            search.draft, actor=ACTOR, at=AT, applicability=decisions + (decisions[0],)
        )


def test_applicability_cannot_exempt_acceptance(search: SearchSpecification) -> None:
    decision = ApplicabilityDecision.model_validate(
        {
            **search.applicability[0].model_dump(),
            "dimension": SpecDimension.ACCEPTANCE,
            "applicable": False,
        }
    )
    with pytest.raises(ValueError, match="always-required"):
        search.delivery.assess(search.draft, actor=ACTOR, at=AT, applicability=(decision,))


@pytest.mark.parametrize(
    "kind,dimension",
    [
        (SpecItemType.ACCEPTANCE_CRITERION, SpecDimension.ACCEPTANCE),
        (SpecItemType.FUNCTIONAL_REQUIREMENT, SpecDimension.FUNCTIONAL),
        (SpecItemType.SCOPE, SpecDimension.SCOPE),
    ],
)
def test_missing_required_content(
    search: SearchSpecification, kind: SpecItemType, dimension: SpecDimension
) -> None:
    revision = search.drafting.revise(
        search.draft,
        search.draft.context,
        tuple(i for i in search.draft.items if i.kind != kind),
        actor=ACTOR,
        at=AT,
        reason="Explicitly incomplete revision",
    )
    assessment = search.delivery.assess(
        revision.after, actor=ACTOR, at=AT, applicability=search.applicability
    )
    assert dimension in assessment.result.missing_requirements
    assert (
        next(g for g in assessment.gaps if g.dimension == dimension).classification
        == GapClassification.BLOCKING
    )


def test_accepted_ai_content_is_still_unsupported_and_needs_review(
    search: SearchSpecification,
) -> None:
    from product_discovery_engine.application.delivery_specification import (
        DeliverySpecificationService,
    )
    from product_discovery_engine.domain.spec_proposals import ItemDisposition, ItemReview

    proposal = SpecItem(
        id=uuid4(),
        kind=SpecItemType.ACCEPTANCE_CRITERION,
        statement="Search provides appropriate results",
        origin=ContentOrigin.AI_PROPOSAL,
        references=(),
    )
    drafting = DeliverySpecificationService(FakeDraftingProvider((proposal,)))
    record = drafting.draft(search.draft.context, at=AT)
    review = drafting.review(
        record,
        (
            ItemReview(
                item_id=proposal.id,
                disposition=ItemDisposition.ACCEPTED,
                rationale="Accept explicitly as a proposal",
            ),
        ),
        actor=ACTOR,
        at=AT,
    )
    draft = drafting.create(search.draft.context, actor=ACTOR, at=AT, reviews=(review,)).after
    assessment = search.delivery.assess(draft, actor=ACTOR, at=AT)
    assert (
        next(g for g in assessment.gaps if g.dimension == SpecDimension.ACCEPTANCE).classification
        == GapClassification.REVIEW_REQUIRED
    )
    assert SpecDimension.TRACEABILITY in assessment.result.missing_requirements
    assert (
        next(g for g in assessment.gaps if g.dimension == SpecDimension.TRACEABILITY).gap_type
        == GapType.TRACEABILITY_GAP
    )


@pytest.mark.parametrize("classification", list(GapClassification))
def test_semantic_gaps_need_explicit_human_classification(
    search: SearchSpecification, classification: GapClassification
) -> None:
    gap = search.delivery.materialize_semantic_gap(
        search.draft,
        dimension=SpecDimension.FUNCTIONAL,
        gap_type=GapType.AMBIGUOUS,
        statement="Meaning of appropriate results is ambiguous",
        rationale="Explicit reviewer concern",
        source_basis="human:review",
        classification=classification,
        actor=ACTOR,
        at=AT,
    )
    assessment = search.delivery.assess(
        search.draft, actor=ACTOR, at=AT, applicability=search.applicability, semantic_gaps=(gap,)
    )
    assert gap in assessment.gaps
    assert SpecGap.model_validate_json(gap.model_dump_json()) == gap
    with pytest.raises(ValueError, match="AI proposal"):
        search.delivery.materialize_semantic_gap(
            search.draft,
            dimension=SpecDimension.FUNCTIONAL,
            gap_type=GapType.AMBIGUOUS,
            statement="AI concern",
            rationale="Proposal is advisory",
            source_basis="ai:proposal",
            classification=classification,
            actor=Actor(kind=ActorKind.AI, id="fake"),
            at=AT,
        )


def test_gap_review_preserves_original_and_audited_classification(
    search: SearchSpecification,
) -> None:
    original = search.delivery.materialize_semantic_gap(
        search.draft,
        dimension=SpecDimension.FUNCTIONAL,
        gap_type=GapType.CONFLICTING,
        statement="Competing requirement readings",
        rationale="Reviewer identifies conflict",
        source_basis="human:notes",
        classification=GapClassification.REVIEW_REQUIRED,
        actor=ACTOR,
        at=AT,
    )
    changed = search.delivery.review_gap(
        original,
        actor=ACTOR,
        at=AT,
        rationale="Explicitly classify delivery impact",
        classification=GapClassification.BLOCKING,
    )
    assert original.classification == GapClassification.REVIEW_REQUIRED
    assert changed.reviews[-1].previous_classification == original.classification
    resolved = search.delivery.review_gap(
        changed,
        actor=ACTOR,
        at=AT,
        rationale="Human decision resolves readings",
        classification=GapClassification.NON_BLOCKING,
        status=GapStatus.RESOLVED,
        resolution_references=(uuid4(),),
    )
    assert resolved.status == GapStatus.RESOLVED and changed.status == GapStatus.OPEN
    assert SpecGap.model_validate_json(resolved.model_dump_json()) == resolved
    with pytest.raises(ValueError, match="explicit human references"):
        search.delivery.review_gap(
            changed,
            actor=ACTOR,
            at=AT,
            rationale="No resulting state supplied",
            classification=GapClassification.NON_BLOCKING,
            status=GapStatus.RESOLVED,
        )
    with pytest.raises(ValueError):
        SpecGap.model_validate({**original.model_dump(), "classification": "invented"})
    with pytest.raises(ValueError, match="reviewed history"):
        SpecGap.model_validate(
            {**changed.model_dump(), "classification": GapClassification.NON_BLOCKING}
        )


def test_stale_gaps_and_assessments_cannot_be_reused(search: SearchSpecification) -> None:
    assessment = search.delivery.assess(
        search.draft, actor=ACTOR, at=AT, applicability=search.applicability
    )
    revision = search.drafting.revise(
        search.draft,
        search.draft.context,
        search.draft.items
        + (
            SpecItem(
                id=uuid4(),
                kind=SpecItemType.RISK,
                statement=Unknown(reason="Risk to review"),
                origin=ContentOrigin.UNKNOWN,
                references=(),
            ),
        ),
        actor=ACTOR,
        at=AT,
        reason="Material risk added",
    )
    with pytest.raises(ValueError, match="exact current spec"):
        assessment.require_current(revision.after, search.delivery.policy, AT)
    with pytest.raises(ValueError, match="stale or cross-spec"):
        assessment.gaps[0].require_scope(revision.after)
    with pytest.raises(ValueError, match="stale or future"):
        assessment.require_current(search.draft, search.delivery.policy, AT + timedelta(hours=24))
    with pytest.raises(ValidationError, match="structural gaps clear by revision"):
        search.delivery.review_gap(
            assessment.gaps[0],
            actor=ACTOR,
            at=AT,
            rationale="Cannot waive missing content",
            classification=GapClassification.NON_BLOCKING,
        )


@pytest.mark.parametrize(
    "failure",
    [
        "missing_dimension",
        "duplicate_dimension",
        "bad_minimum",
        "optional_acceptance",
        "nonblocking_required",
        "bad_applicability",
        "unknown_dimension",
        "missing_condition",
        "optional_invariant",
        "zero_expiry",
        "bool_expiry",
        "missing_version",
    ],
)
def test_policy_rejects_unsafe_or_invalid_configuration(
    search: SearchSpecification, failure: str
) -> None:
    data = search.delivery.policy.model_dump()
    dimensions = list(data["dimensions"])
    conditions = list(data["gate_conditions"])
    if failure == "missing_dimension":
        dimensions.pop()
    elif failure == "duplicate_dimension":
        dimensions[-1] = dimensions[0]
    elif failure == "bad_minimum":
        dimensions[0]["minimum"] = "unknown"
    elif failure == "optional_acceptance":
        next(r for r in dimensions if r["dimension"] == SpecDimension.ACCEPTANCE)["required"] = (
            False
        )
    elif failure == "nonblocking_required":
        dimensions[0]["gap_classification"] = "non_blocking"
    elif failure == "bad_applicability":
        dimensions[0]["applicability"] = "invented"
    elif failure == "unknown_dimension":
        dimensions[0]["dimension"] = "invented"
    elif failure == "missing_condition":
        conditions.pop()
    elif failure == "optional_invariant":
        conditions[0]["required"] = False
    elif failure == "zero_expiry":
        data["validity_hours"] = 0
    elif failure == "bool_expiry":
        data["validity_hours"] = True
    elif failure == "missing_version":
        data.pop("version")
    data["dimensions"], data["gate_conditions"] = dimensions, conditions
    with pytest.raises(ValidationError):
        SpecCompletenessPolicy.model_validate(data)


def test_actual_toml_loads_validated_policy(search: SearchSpecification) -> None:
    assert (
        load_spec_completeness_policy(Path("config/spec-completeness.v1.toml"))
        == search.delivery.policy
    )


def test_assessment_tampering_and_ai_authority_rejected(search: SearchSpecification) -> None:
    assessment = search.delivery.assess(
        search.draft, actor=ACTOR, at=AT, applicability=search.applicability
    )
    data = assessment.model_dump()
    data["result"]["state"] = CompletenessState.COMPLETE
    with pytest.raises(ValidationError, match="reconstruct"):
        SpecCompletenessAssessment.model_validate(data)
    with pytest.raises(ValueError, match="AI"):
        search.delivery.assess(search.draft, actor=Actor(kind=ActorKind.AI, id="fake"), at=AT)
