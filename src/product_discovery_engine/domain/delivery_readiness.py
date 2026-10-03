"""Knowledge maturity by explicit dimensions; never a build or portfolio recommendation."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .assumptions import ValidationState
from .audit import Actor, AuditEvent, EventType
from .common import DomainModel, ReferenceIds, Text, Unknown
from .decisioning_inputs import (
    ChallengeDisposition,
    ContradictionDisposition,
    ReadinessInput,
)
from .decisioning_policy import (
    DeliveryReadinessPolicy,
    EvidenceRequirement,
    ReadinessDimension,
    ReadinessState,
    at_least,
)
from .discovery_priority import decision_audit, require_decision_audit
from .evidence import EvidenceDirection, Freshness
from .evidence_assessment import EvidenceScope
from .evidence_origins import SourceGroup, group_sources
from .triangulation import independent_method_count
from .validation import ValidationConclusion, ValidationStatus


class DimensionState(StrEnum):
    UNKNOWN = "unknown"
    INSUFFICIENT = "insufficient"
    PARTIAL = "partial"
    SUFFICIENT = "sufficient"
    NOT_APPLICABLE = "not_applicable"


class DimensionResult(DomainModel):
    dimension: ReadinessDimension
    state: DimensionState
    required: bool
    explanation: Text
    scope: EvidenceScope | None = None
    supporting_evidence_ids: ReferenceIds = ()
    historical_evidence_ids: ReferenceIds = ()


class ReadinessResult(DomainModel):
    dimensions: tuple[DimensionResult, ...]
    blocking_gaps: tuple[Text, ...]
    non_blocking_concerns: tuple[Text, ...]
    unresolved_contradictions: ReferenceIds
    unresolved_high_risk_assumptions: ReferenceIds
    freshness_concerns: ReferenceIds
    challenge_concerns: tuple[Text, ...]
    state: ReadinessState
    explanation: Text


def _combine(states: tuple[DimensionState, ...]) -> DimensionState:
    for state in (DimensionState.INSUFFICIENT, DimensionState.UNKNOWN, DimensionState.PARTIAL):
        if state in states:
            return state
    return DimensionState.SUFFICIENT


def _evidence_dimension(
    inputs: ReadinessInput,
    requirement: EvidenceRequirement,
) -> tuple[DimensionResult, DimensionState, DimensionState, DimensionState]:
    dimension = requirement.dimension
    solution = inputs.hypothesis.content.solution_hypothesis
    if requirement.solution_only and solution is None:
        result = DimensionResult(
            dimension=dimension,
            state=DimensionState.NOT_APPLICABLE,
            required=False,
            explanation="No solution hypothesis exists",
        )
        return result, result.state, result.state, result.state
    scope = next((s for s in inputs.target_scopes if s.target == requirement.target), None)
    packet = next((k for k in inputs.knowledge if k.scope == scope), None)
    if scope is None or packet is None or not packet.evidence or scope.population is None:
        result = DimensionResult(
            dimension=dimension,
            state=DimensionState.UNKNOWN,
            required=False,
            scope=scope,
            explanation="Missing exact claim/population evidence scope",
        )
        return result, result.state, result.state, result.state
    supports = tuple(
        (e, q)
        for e, q in zip(packet.evidence, packet.quality, strict=True)
        if e.direction == EvidenceDirection.SUPPORTS
    )
    quality_supports = tuple(
        e
        for e, q in supports
        if q.aggregate is not None
        and at_least(q.aggregate, requirement.minimum_quality)
        and q.freshness.state != Freshness.INVALIDATED
    )
    quality_state = (
        DimensionState.SUFFICIENT
        if quality_supports
        else (
            DimensionState.UNKNOWN
            if any(q.aggregate is None for _, q in supports)
            else DimensionState.INSUFFICIENT
        )
    )
    fresh_supports = tuple(
        e for e, q in supports if q.freshness.state in requirement.acceptable_freshness
    )
    freshness_state = DimensionState.SUFFICIENT if fresh_supports else DimensionState.INSUFFICIENT
    review_due = any(q.freshness.state == Freshness.REVIEW_DUE for _, q in supports)
    if fresh_supports and review_due:
        freshness_state = DimensionState.PARTIAL
    eligible = tuple(e for e in quality_supports if e in fresh_supports)
    # Filtering old/weak/contradicting records must not erase known source overlap.
    # Keep full-history connected components, but count only qualifying support methods.
    eligible_ids = {e.id for e in eligible}
    relations = {r.evidence_id: r for r in packet.origin_relationships}
    qualifying_groups = []
    for group in group_sources(packet.evidence, packet.origin_relationships):
        ids = tuple(id for id in group.evidence_ids if id in eligible_ids)
        if ids:
            methods = tuple(
                sorted(
                    {o.method for id in ids if id in relations for o in relations[id].origins},
                    key=str,
                )
            )
            qualifying_groups.append(
                SourceGroup(
                    evidence_ids=ids,
                    origin_ids=group.origin_ids,
                    family_keys=group.family_keys,
                    methods=methods,
                    traceable=all(id in relations for id in ids),
                )
            )
    independent_groups = tuple(g for g in qualifying_groups if g.traceable)
    independent = (
        len(independent_groups) >= requirement.minimum_independent_groups
        and independent_method_count(independent_groups) >= requirement.minimum_distinct_methods
    )
    triangulation_state = DimensionState.SUFFICIENT if independent else DimensionState.INSUFFICIENT
    state = _combine((quality_state, freshness_state, triangulation_state))
    if requirement.solution_only and isinstance(solution, Unknown):
        state = DimensionState.UNKNOWN
    if (
        dimension == ReadinessDimension.PROBLEM_EVIDENCE
        and isinstance(inputs.hypothesis.content.problem_statement, Unknown)
        or dimension == ReadinessDimension.TARGET_SEGMENT
        and isinstance(inputs.hypothesis.content.target_segment, Unknown)
    ):
        state = DimensionState.UNKNOWN
    return (
        DimensionResult(
            dimension=dimension,
            state=state,
            required=False,
            scope=scope,
            supporting_evidence_ids=tuple(e.id for e in eligible),
            historical_evidence_ids=tuple(e.id for e in packet.evidence),
            explanation=(
                f"Exact {scope.target.value} claim/population only: quality={quality_state.value}, "
                f"freshness={freshness_state.value}, independence={triangulation_state.value}. "
                "Other evidence targets and supporting majorities cannot satisfy this claim."
            ),
        ),
        quality_state,
        freshness_state,
        triangulation_state,
    )


def evaluate_readiness(inputs: ReadinessInput, policy: DeliveryReadinessPolicy) -> ReadinessResult:
    dimensions: dict[ReadinessDimension, DimensionResult] = {}
    required_evidence = []
    for requirement in policy.evidence_requirements:
        result, quality, freshness, independence = _evidence_dimension(inputs, requirement)
        if not policy.review_due_requires_review and freshness == DimensionState.PARTIAL:
            freshness = DimensionState.SUFFICIENT
            if result.state == DimensionState.PARTIAL:
                result = DimensionResult.model_validate(
                    {**result.model_dump(), "state": DimensionState.SUFFICIENT}
                )
        dimensions[result.dimension] = result
        if (
            result.dimension in policy.required_dimensions
            and result.state != DimensionState.NOT_APPLICABLE
        ):
            required_evidence.append((quality, freshness, independence))

    def add(dimension: ReadinessDimension, state: DimensionState, explanation: str) -> None:
        dimensions[dimension] = DimensionResult(
            dimension=dimension, state=state, required=False, explanation=explanation
        )

    for dimension, index in (
        (ReadinessDimension.EVIDENCE_QUALITY, 0),
        (ReadinessDimension.EVIDENCE_FRESHNESS, 1),
        (ReadinessDimension.TRIANGULATION, 2),
    ):
        add(
            dimension,
            _combine(tuple(r[index] for r in required_evidence)),
            "Evaluated separately across required exact evidence targets; no quantity bonus",
        )
    content = inputs.hypothesis.content
    add(
        ReadinessDimension.OUTCOME_CLARITY,
        DimensionState.UNKNOWN
        if isinstance(content.desired_outcome, Unknown)
        else DimensionState.SUFFICIENT,
        "Explicit desired outcome; no inferred business impact",
    )
    add(
        ReadinessDimension.OWNERSHIP,
        DimensionState.UNKNOWN if content.owner is None else DimensionState.SUFFICIENT,
        "An accountable hypothesis owner is required",
    )
    strategy_state = DimensionState.SUFFICIENT
    if (
        content.strategy is None
        or inputs.strategy_context is None
        or isinstance(inputs.strategy_context.objective, Unknown)
    ):
        strategy_state = DimensionState.UNKNOWN
    elif policy.strategy_requires_human_acknowledgement and inputs.strategy_acknowledgement is None:
        strategy_state = DimensionState.PARTIAL
    add(
        ReadinessDimension.STRATEGY,
        strategy_state,
        "Versioned explicit strategy and configured human acknowledgement; AI fit is advisory",
    )

    risk_states = []
    unresolved_risks = []
    critical_assumptions = []
    for item in inputs.assumptions:
        risk = item.risk
        if risk is None or risk.decision_impact is None or risk.uncertainty is None:
            risk_states.append(DimensionState.UNKNOWN)
            unresolved_risks.append(item.assumption.id)
            continue
        critical_impact = at_least(risk.decision_impact, policy.critical_impact)
        critical = critical_impact and (
            at_least(risk.uncertainty, policy.critical_uncertainty)
            or item.assumption.validation_state == ValidationState.REFUTED
        )
        if critical_impact:
            critical_assumptions.append(item.assumption.id)
        if critical:
            accepted = item.treatment is not None and policy.allow_human_assumption_treatment
            risk_states.append(
                DimensionState.SUFFICIENT if accepted else DimensionState.INSUFFICIENT
            )
            if not accepted:
                unresolved_risks.append(item.assumption.id)
    add(
        ReadinessDimension.ASSUMPTION_RISK,
        _combine(tuple(risk_states)),
        "Critical impact/uncertainty or refutation needs resolution or explicit human treatment; "
        "low-impact uncertainty may remain",
    )

    contradiction_states = []
    unresolved_contradictions: list[UUID] = []
    for packet in inputs.knowledge:
        ids = tuple(
            e.id
            for e in packet.evidence
            if e.direction == EvidenceDirection.CONTRADICTS and e.invalidated_on is None
        )
        if not ids:
            continue
        review = next((r for r in inputs.contradictions if r.scope == packet.scope), None)
        state = DimensionState.UNKNOWN
        if review is not None:
            if review.disposition in {
                ContradictionDisposition.UNRESOLVED_MATERIAL,
                ContradictionDisposition.INVALIDATES_CRITICAL,
            }:
                state = DimensionState.INSUFFICIENT
            elif review.disposition == ContradictionDisposition.HEALTHY_MIXED:
                state = DimensionState.PARTIAL
            elif policy.allow_accepted_contradictions:
                state = DimensionState.SUFFICIENT
            else:
                state = DimensionState.PARTIAL
        if state != DimensionState.SUFFICIENT:
            unresolved_contradictions.extend(ids)
        contradiction_states.append(state)
    add(
        ReadinessDimension.CONTRADICTIONS,
        _combine(tuple(contradiction_states)),
        "Contradictions remain visible; explicit human classification, no majority voting",
    )

    required_validations = set(inputs.required_validation_ids)
    results_by_activity = {r.activity_id: r for r in inputs.validation_results}
    freshness_by_id = {
        q.evidence_id: q.freshness.state for k in inputs.knowledge for q in k.quality
    }

    def validation_state(activity_id: UUID) -> DimensionState:
        activity = next(v for v in inputs.validations if v.id == activity_id)
        if activity.status != ValidationStatus.COMPLETED:
            return DimensionState.INSUFFICIENT
        validation_result = results_by_activity.get(activity_id)
        if validation_result is None:
            return DimensionState.UNKNOWN
        freshness_states = tuple(
            freshness_by_id[id] for id in validation_result.generated_evidence_ids
        )
        if Freshness.INVALIDATED in freshness_states or (
            policy.require_current_validation_evidence
            and any(state != Freshness.CURRENT for state in freshness_states)
        ):
            return DimensionState.INSUFFICIENT
        if validation_result.conclusion in {
            ValidationConclusion.INCONCLUSIVE,
            ValidationConclusion.PARTIALLY_SUPPORTED,
        }:
            return DimensionState.PARTIAL
        return DimensionState.SUFFICIENT

    validation_states = [validation_state(id) for id in required_validations]
    if policy.require_completed_critical_validation:
        for assumption_id in critical_assumptions:
            relevant = tuple(
                v for v in inputs.validations if v.target_assumption_id == assumption_id
            )
            states = tuple(validation_state(v.id) for v in relevant)
            # Later defensible learning may resolve an earlier inconclusive result.
            if DimensionState.SUFFICIENT not in states:
                validation_states.append(_combine(states) if states else DimensionState.UNKNOWN)
    add(
        ReadinessDimension.VALIDATION,
        _combine(tuple(validation_states)),
        "Required and critical-assumption validations need completed criteria-bound results; "
        "inconclusive learning remains open",
    )

    challenge_state = DimensionState.SUFFICIENT
    challenge_concerns = []
    if inputs.challenge is None:
        challenge_state = DimensionState.UNKNOWN
        challenge_concerns.append("Challenge Mode completion missing")
    elif policy.challenge_requires_human_review:
        if inputs.challenge.review is None:
            challenge_state = DimensionState.PARTIAL
            challenge_concerns.append("Challenge Mode needs accountable human review")
        else:
            challenge_states: list[DimensionState] = []
            for challenge_item in inputs.challenge.items:
                if challenge_item.human_severity is None:
                    challenge_states.append(DimensionState.UNKNOWN)
                    challenge_concerns.append(f"Unknown human severity: {challenge_item.item_id}")
                elif challenge_item.disposition == ChallengeDisposition.UNRESOLVED:
                    if at_least(challenge_item.human_severity, policy.serious_challenge_at_least):
                        challenge_states.append(DimensionState.INSUFFICIENT)
                    challenge_concerns.append(
                        f"Unresolved reviewed challenge: {challenge_item.item_id}"
                    )
            challenge_state = _combine(tuple(challenge_states))
    add(
        ReadinessDimension.CHALLENGE,
        challenge_state,
        "AI severity does not set readiness; completion and configured human review are inspected",
    )
    for dimension in ReadinessDimension:
        if dimension not in dimensions:
            add(dimension, DimensionState.UNKNOWN, "No evidence-target policy configured; unknown")
    results = tuple(
        DimensionResult.model_validate(
            {**dimensions[d].model_dump(), "required": d in policy.required_dimensions}
        )
        for d in ReadinessDimension
    )
    blocking = tuple(
        f"{d.dimension.value}: {d.explanation}"
        for d in results
        if d.required and d.state in {DimensionState.UNKNOWN, DimensionState.INSUFFICIENT}
    )
    review_gaps = tuple(
        f"{d.dimension.value}: {d.explanation}"
        for d in results
        if d.required and d.state == DimensionState.PARTIAL
    )
    concerns = tuple(
        f"{d.dimension.value}: {d.state.value}"
        for d in results
        if not d.required
        and d.state not in {DimensionState.SUFFICIENT, DimensionState.NOT_APPLICABLE}
    )
    readiness_state = (
        ReadinessState.NOT_READY
        if blocking
        else (ReadinessState.NEEDS_REVIEW if review_gaps else ReadinessState.READY)
    )
    freshness_ids = tuple(
        q.evidence_id
        for k in inputs.knowledge
        for q in k.quality
        if q.freshness.state != Freshness.CURRENT
    )
    return ReadinessResult(
        dimensions=results,
        blocking_gaps=blocking,
        non_blocking_concerns=review_gaps + concerns,
        unresolved_contradictions=tuple(unresolved_contradictions),
        unresolved_high_risk_assumptions=tuple(unresolved_risks),
        freshness_concerns=freshness_ids,
        challenge_concerns=tuple(challenge_concerns),
        state=readiness_state,
        explanation=f"{readiness_state.value}: explicit knowledge dimensions only; "
        "readiness does not select delivery or rank a portfolio",
    )


class DeliveryReadinessAssessment(DomainModel):
    id: UUID
    inputs: ReadinessInput
    policy: DeliveryReadinessPolicy
    policy_version: Text
    assessed_at: AwareDatetime
    result: ReadinessResult
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "DeliveryReadinessAssessment":
        self.inputs.require_time(self.assessed_at)
        if self.policy_version != self.policy.version or self.result != evaluate_readiness(
            self.inputs, self.policy
        ):
            raise ValueError("readiness result must reconstruct from retained inputs and policy")
        require_decision_audit(
            self.event,
            self.id,
            self.inputs.hypothesis.id,
            EventType.DELIVERY_READINESS_ASSESSED,
            self.assessed_at,
        )
        return self


def assess_delivery_readiness(
    inputs: ReadinessInput,
    *,
    policy: DeliveryReadinessPolicy,
    actor: Actor,
    at: datetime,
    assessment_id: UUID,
    event_id: UUID,
) -> DeliveryReadinessAssessment:
    inputs = ReadinessInput.model_validate(inputs)
    policy = DeliveryReadinessPolicy.model_validate(policy)
    inputs.require_time(at)
    return DeliveryReadinessAssessment(
        id=assessment_id,
        inputs=inputs,
        policy=policy,
        policy_version=policy.version,
        assessed_at=at,
        result=evaluate_readiness(inputs, policy),
        event=decision_audit(
            event_id,
            assessment_id,
            inputs.hypothesis.id,
            EventType.DELIVERY_READINESS_ASSESSED,
            actor,
            at,
        ),
    )
