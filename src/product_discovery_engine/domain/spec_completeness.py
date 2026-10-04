"""Recomputable structural completeness; semantic adequacy remains a human review."""

from enum import StrEnum
from uuid import UUID, uuid5

from pydantic import AwareDatetime, Field, model_validator

from .audit import Actor, ActorKind, AuditEvent, EventType, ObjectKind
from .common import DomainModel, ReferenceIds, Text, Unknown
from .delivery_context import ReferenceKind
from .delivery_selection import require_human
from .spec_completeness_policy import (
    ApplicabilityRule,
    DimensionState,
    GapClassification,
    SpecCompletenessPolicy,
    SpecDimension,
)
from .spec_content import DeliverySpecBody, SpecVersionReference
from .spec_gaps import GapBasis, GapStatus, GapType, SpecGap, spec_event
from .spec_items import ContentOrigin


class ApplicabilityDecision(DomainModel):
    dimension: SpecDimension
    applicable: bool = Field(strict=True)
    context_fact_id: UUID
    actor: Actor
    at: AwareDatetime
    rationale: Text

    @model_validator(mode="after")
    def human_decision(self) -> "ApplicabilityDecision":
        require_human(self.actor)
        return self


class CompletenessState(StrEnum):
    INCOMPLETE = "incomplete"
    NEEDS_REVIEW = "needs_review"
    COMPLETE = "complete"


class DimensionResult(DomainModel):
    dimension: SpecDimension
    state: DimensionState
    required: bool
    item_ids: ReferenceIds
    explanation: Text


class CompletenessResult(DomainModel):
    state: CompletenessState
    dimensions: tuple[DimensionResult, ...]
    missing_requirements: tuple[SpecDimension, ...]
    unresolved_gaps: ReferenceIds
    blocking_gaps: ReferenceIds
    non_blocking_gaps: ReferenceIds
    review_required_gaps: ReferenceIds
    unknown_conditions: tuple[SpecDimension, ...]
    explanation: Text


def structural_results(
    spec: DeliverySpecBody,
    policy: SpecCompletenessPolicy,
    applicability: tuple[ApplicabilityDecision, ...],
) -> tuple[DimensionResult, ...]:
    if len({a.dimension for a in applicability}) != len(applicability):
        raise ValueError("duplicate applicability decisions")
    declared = {a.dimension: a for a in applicability}
    for decision in applicability:
        if (
            policy.requirement(decision.dimension).applicability
            != ApplicabilityRule.EXPLICIT_CONTEXT
        ):
            raise ValueError("applicability decision cannot exempt an always-required dimension")
        fact = next(
            (f for f in spec.context.delivery_facts if f.id == decision.context_fact_id), None
        )
        if (
            fact is None
            or fact.kind != ReferenceKind.HUMAN_DECISION
            or fact.recorded_by != decision.actor
            or decision.at < fact.recorded_at
        ):
            raise ValueError("applicability needs an explicitly supplied human context decision")
    results: list[DimensionResult] = []
    for rule in policy.dimensions:
        items = tuple(i for i in spec.items if i.kind in rule.item_types)
        state: DimensionState | None = None
        explanation = "Required supplied statements and their provenance are structurally present"
        if rule.applicability == ApplicabilityRule.SOLUTION_PRESENT:
            solution = spec.context.hypothesis.content.solution_hypothesis
            if solution is None:
                state, explanation = (
                    DimensionState.NOT_APPLICABLE,
                    "No solution intent in supplied hypothesis",
                )
            elif isinstance(solution, Unknown):
                state, explanation = (
                    DimensionState.UNKNOWN,
                    "Solution applicability is explicitly unknown",
                )
        elif rule.applicability == ApplicabilityRule.EXPLICIT_CONTEXT:
            applicability_decision = declared.get(rule.dimension)
            if applicability_decision is None:
                state, explanation = (
                    DimensionState.UNKNOWN,
                    "Applicability has not been explicitly decided",
                )
            elif not applicability_decision.applicable:
                state, explanation = DimensionState.NOT_APPLICABLE, applicability_decision.rationale
        if state is None:
            if rule.dimension == SpecDimension.OWNERSHIP:
                state = (
                    DimensionState.SUFFICIENT
                    if spec.context.hypothesis.content.owner
                    else DimensionState.UNKNOWN
                )
                explanation = (
                    "Accountable selected-hypothesis owner"
                    if state == DimensionState.SUFFICIENT
                    else "Accountable owner absent"
                )
            elif rule.dimension == SpecDimension.TRACEABILITY:
                statements = tuple(s for i in spec.items for s in i.statements())
                known = tuple(s for s in statements if not isinstance(s.statement, Unknown))
                state = (
                    DimensionState.SUFFICIENT
                    if known and all(s.references for s in known)
                    else DimensionState.INSUFFICIENT
                )
                explanation = (
                    "Known clauses retain supplied references"
                    if state == DimensionState.SUFFICIENT
                    else "Known specification clauses need provenance references"
                )
            elif not items:
                state, explanation = DimensionState.INSUFFICIENT, "No item supplies this dimension"
            else:
                statements = tuple(s for i in items for s in i.statements())
                unknown = any(isinstance(s.statement, Unknown) for s in statements)
                unsupported = any(s.origin == ContentOrigin.AI_PROPOSAL for s in statements)
                if all(isinstance(s.statement, Unknown) for s in statements):
                    state, explanation = (
                        DimensionState.UNKNOWN,
                        "Supplied content explicitly preserves unknown information",
                    )
                elif unknown or unsupported:
                    state = DimensionState.PARTIAL
                    explanation = "Unknown clauses or proposals need explicit decisions"
                else:
                    state = DimensionState.SUFFICIENT
        results.append(
            DimensionResult(
                dimension=rule.dimension,
                state=state,
                required=rule.required,
                item_ids=tuple(i.id for i in items),
                explanation=explanation,
            )
        )
    return tuple(results)


def dimension_acceptable(result: DimensionResult, policy: SpecCompletenessPolicy) -> bool:
    return result.state in {DimensionState.SUFFICIENT, DimensionState.NOT_APPLICABLE} or (
        result.state == DimensionState.PARTIAL
        and policy.requirement(result.dimension).minimum == DimensionState.PARTIAL
    )


def structural_gaps(
    spec: DeliverySpecBody,
    policy: SpecCompletenessPolicy,
    dimensions: tuple[DimensionResult, ...],
    actor: Actor,
    at: AwareDatetime,
) -> tuple[SpecGap, ...]:
    gaps: list[SpecGap] = []
    for result in dimensions:
        if dimension_acceptable(result, policy):
            continue
        rule = policy.requirement(result.dimension)
        kind = (
            GapType.UNRESOLVED_UNKNOWN
            if result.state == DimensionState.UNKNOWN
            else GapType.UNSUPPORTED
            if result.state == DimensionState.PARTIAL
            else GapType.TRACEABILITY_GAP
            if result.dimension == SpecDimension.TRACEABILITY
            else GapType.MISSING
        )
        classification = rule.gap_classification
        if kind == GapType.UNSUPPORTED:
            classification = GapClassification.REVIEW_REQUIRED
        gap_id = uuid5(spec.id, f"{spec.version}:{policy.version}:{result.dimension}:{kind}")
        gaps.append(
            SpecGap(
                id=gap_id,
                spec=SpecVersionReference(id=spec.id, version=spec.version),
                dimension=result.dimension,
                gap_type=kind,
                affected_item_ids=result.item_ids,
                statement=rule.requested_information,
                rationale=result.explanation,
                source_basis=f"policy:{policy.version}:{result.dimension.value}",
                basis=GapBasis.STRUCTURAL,
                classification=classification,
                detected_classification=classification,
                detected_at=at,
                detected_by=actor,
                event=spec_event(
                    EventType.SPEC_GAP_DETECTED,
                    ObjectKind.SPEC_GAP,
                    gap_id,
                    actor,
                    at,
                    uuid5(gap_id, f"detected:{at.isoformat()}:{actor.id}"),
                    (spec.id,),
                    result.explanation,
                    spec.version,
                ),
            )
        )
    return tuple(gaps)


def completeness_result(
    dimensions: tuple[DimensionResult, ...],
    gaps: tuple[SpecGap, ...],
    policy: SpecCompletenessPolicy,
) -> CompletenessResult:
    unresolved = tuple(g for g in gaps if g.status == GapStatus.OPEN)
    blocking = tuple(g.id for g in unresolved if g.classification == GapClassification.BLOCKING)
    review = tuple(
        g.id for g in unresolved if g.classification == GapClassification.REVIEW_REQUIRED
    )
    unacceptable = tuple(
        r.dimension for r in dimensions if r.required and not dimension_acceptable(r, policy)
    )
    unknown = tuple(r.dimension for r in dimensions if r.state == DimensionState.UNKNOWN)
    incomplete = blocking or any(
        r.required and r.state in {DimensionState.UNKNOWN, DimensionState.INSUFFICIENT}
        for r in dimensions
    )
    state = (
        CompletenessState.INCOMPLETE
        if incomplete
        else CompletenessState.NEEDS_REVIEW
        if review or unacceptable
        else CompletenessState.COMPLETE
    )
    return CompletenessResult(
        state=state,
        dimensions=dimensions,
        missing_requirements=unacceptable,
        unresolved_gaps=tuple(g.id for g in unresolved),
        blocking_gaps=blocking,
        non_blocking_gaps=tuple(
            g.id for g in unresolved if g.classification == GapClassification.NON_BLOCKING
        ),
        review_required_gaps=review,
        unknown_conditions=unknown,
        explanation="Qualitative structural sufficiency; semantics require human review",
    )


class SpecCompletenessAssessment(DomainModel):
    id: UUID
    spec: DeliverySpecBody
    policy: SpecCompletenessPolicy
    applicability: tuple[ApplicabilityDecision, ...]
    semantic_gaps: tuple[SpecGap, ...] = ()
    assessed_by: Actor
    assessed_at: AwareDatetime
    gaps: tuple[SpecGap, ...]
    result: CompletenessResult
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "SpecCompletenessAssessment":
        if self.assessed_by.kind == ActorKind.AI:
            raise ValueError("AI cannot determine authoritative completeness")
        material_at = self.spec.revision.at if self.spec.revision else self.spec.created_at
        if self.assessed_at < material_at or any(
            a.at > self.assessed_at for a in self.applicability
        ):
            raise ValueError("assessment cannot precede material inputs")
        for gap in self.semantic_gaps:
            gap.require_scope(self.spec)
            if (
                gap.basis != GapBasis.HUMAN_REVIEW
                or not material_at <= gap.detected_at <= self.assessed_at
                or any(r.at > self.assessed_at for r in gap.reviews)
            ):
                raise ValueError("semantic concerns need prior human materialization")
        if len({g.id for g in self.semantic_gaps}) != len(self.semantic_gaps):
            raise ValueError("duplicate semantic gaps")
        dimensions = structural_results(self.spec, self.policy, self.applicability)
        expected = (
            structural_gaps(self.spec, self.policy, dimensions, self.assessed_by, self.assessed_at)
            + self.semantic_gaps
        )
        if len({g.id for g in expected}) != len(expected):
            raise ValueError("assessment requires unique authoritative gap identities")
        if self.gaps != expected or self.result != completeness_result(
            dimensions, expected, self.policy
        ):
            raise ValueError("completeness and gaps must reconstruct from exact policy and inputs")
        if self.event != spec_event(
            EventType.SPEC_COMPLETENESS_ASSESSED,
            ObjectKind.DELIVERY_SPEC,
            self.spec.id,
            self.assessed_by,
            self.assessed_at,
            self.event.id,
            (self.id,),
            self.policy.version,
            self.spec.version,
        ):
            raise ValueError("completeness audit must bind exact assessment")
        return self

    @property
    def policy_version(self) -> str:
        return self.policy.version

    def require_current(
        self, spec: DeliverySpecBody, policy: SpecCompletenessPolicy, at: AwareDatetime
    ) -> None:
        from datetime import timedelta

        from .spec_content import spec_body

        if self.spec != spec_body(spec) or self.policy != policy:
            raise ValueError("assessment must bind exact current spec and full policy")
        if not self.assessed_at <= at < self.assessed_at + timedelta(hours=policy.validity_hours):
            raise ValueError("stale or future completeness assessment")
