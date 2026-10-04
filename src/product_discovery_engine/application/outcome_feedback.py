"""Focused offline orchestration; authoritative rules remain in immutable domain records."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from product_discovery_engine.domain.audit import (
    Actor,
    AuditEvent,
    AuditMetadata,
    AuditTarget,
    EventType,
    ObjectKind,
)
from product_discovery_engine.domain.common import Owner, Provenance, SourceReference
from product_discovery_engine.domain.delivery_context import ReferenceKind, SpecReference
from product_discovery_engine.domain.delivery_gate import (
    DeliveryGateInput,
    DeliveryGateState,
    ImplementationAuthorization,
    evaluate_delivery_conditions,
)
from product_discovery_engine.domain.evidence import (
    Evidence,
    EvidenceDirection,
    PostImplementationProvenance,
)
from product_discovery_engine.domain.evidence_assessment import (
    EvidenceQualityAssessment,
    EvidenceScope,
)
from product_discovery_engine.domain.hypotheses import Hypothesis
from product_discovery_engine.domain.hypothesis_changes import link_evidence
from product_discovery_engine.domain.implementation import (
    ImplementationDeviation,
    ImplementationRecord,
    ImplementationStatus,
    ReleaseObservation,
)
from product_discovery_engine.domain.lifecycle import HypothesisStatus
from product_discovery_engine.domain.outcome_audit import outcome_event
from product_discovery_engine.domain.outcome_causality import (
    CausalInterpretation,
    CausalState,
    StudyDesign,
)
from product_discovery_engine.domain.outcome_evaluation import (
    OutcomeAssessment,
    OutcomeMetricEvaluation,
    assessment_disposition,
    compare_target,
)
from product_discovery_engine.domain.outcome_feedback import (
    OutcomeEvidenceFeedback,
    outcome_methodology,
)
from product_discovery_engine.domain.outcome_lifecycle import OutcomeLifecycleChange
from product_discovery_engine.domain.outcome_measurement import (
    BaselineObservation,
    MeasurementWindow,
    OutcomeMeasurementPlan,
    OutcomeMetricDefinition,
    OutcomeObservation,
)
from product_discovery_engine.domain.outcome_policy import OutcomeMeasurementPolicy
from product_discovery_engine.domain.outcome_review import (
    FollowUpAction,
    FollowUpLearning,
    OutcomeReview,
)
from product_discovery_engine.domain.spec_completeness_policy import SpecCompletenessPolicy


class OutcomeFeedbackService:
    """Caller supplies complete current snapshots; retain every returned record and audit."""

    def __init__(self, policy: OutcomeMeasurementPolicy) -> None:
        self.policy = OutcomeMeasurementPolicy.model_validate(policy)

    def _check_start(
        self,
        authorization: ImplementationAuthorization,
        current: DeliveryGateInput,
        policy: SpecCompletenessPolicy,
        at: datetime,
    ) -> ImplementationAuthorization:
        authorization = ImplementationAuthorization.model_validate(authorization)
        current = DeliveryGateInput.model_validate(current)
        policy = SpecCompletenessPolicy.model_validate(policy)
        if current != authorization.current or policy != authorization.policy:
            raise ValueError(
                "implementation must bind exact current authorized input packet and policy"
            )
        if not authorization.authorized_at <= at < authorization.gate.expires_at:
            raise ValueError("implementation start requires non-stale authorization")
        if evaluate_delivery_conditions(current, policy, at).state != DeliveryGateState.PASSED:
            raise ValueError("implementation start requires still-valid authorized specification")
        return authorization

    def plan_implementation(
        self,
        authorization: ImplementationAuthorization,
        current: DeliveryGateInput,
        *,
        spec_policy: SpecCompletenessPolicy,
        owner: Owner,
        actor: Actor,
        at: datetime,
        summary: str,
    ) -> ImplementationRecord:
        authorization = self._check_start(authorization, current, spec_policy, at)
        record_id = uuid4()
        return ImplementationRecord(
            id=record_id,
            authorization=authorization,
            owner=owner,
            status=ImplementationStatus.PLANNED,
            recorded_by=actor,
            recorded_at=at,
            summary=summary,
            events=(
                outcome_event(
                    EventType.IMPLEMENTATION_PLANNED,
                    ObjectKind.IMPLEMENTATION,
                    record_id,
                    actor,
                    at,
                    uuid4(),
                    (
                        authorization.id,
                        authorization.hypothesis_id,
                        authorization.selection_id,
                        authorization.spec_id,
                    ),
                    summary,
                    1,
                ),
            ),
        )

    def start_implementation(
        self,
        authorization: ImplementationAuthorization,
        current: DeliveryGateInput,
        *,
        spec_policy: SpecCompletenessPolicy,
        owner: Owner,
        actor: Actor,
        at: datetime,
        summary: str,
        planned: ImplementationRecord | None = None,
    ) -> ImplementationRecord:
        authorization = self._check_start(authorization, current, spec_policy, at)
        planned = ImplementationRecord.model_validate(planned) if planned else None
        if planned and planned.authorization != authorization:
            raise ValueError("planned implementation belongs to a different authorization")
        record_id, version = (planned.id, planned.version + 1) if planned else (uuid4(), 1)
        return ImplementationRecord(
            id=record_id,
            authorization=authorization,
            owner=owner,
            status=ImplementationStatus.IN_PROGRESS,
            version=version,
            recorded_by=actor,
            recorded_at=at,
            summary=summary,
            started_at=at,
            previous=planned,
            events=(
                outcome_event(
                    EventType.IMPLEMENTATION_STARTED,
                    ObjectKind.IMPLEMENTATION,
                    record_id,
                    actor,
                    at,
                    uuid4(),
                    (
                        authorization.id,
                        authorization.hypothesis_id,
                        authorization.selection_id,
                        authorization.spec_id,
                    ),
                    summary,
                    version,
                ),
            ),
        )

    def complete_implementation(
        self,
        record: ImplementationRecord,
        *,
        actor: Actor,
        at: datetime,
        summary: str,
        delivered_scope: tuple[str, ...],
        delivered_item_ids: tuple[UUID, ...],
        deviations: tuple[ImplementationDeviation, ...] = (),
        omitted_scope: tuple[str, ...] = (),
        artifact_references: tuple[str, ...] = (),
        release_references: tuple[str, ...] = (),
        limitations: tuple[str, ...] = (),
    ) -> ImplementationRecord:
        record = ImplementationRecord.model_validate(record)
        version = record.version + 1
        related = (
            record.authorization.id,
            record.hypothesis_id,
            record.selection_id,
            record.spec_id,
        )
        events: tuple[AuditEvent, ...] = (
            outcome_event(
                EventType.IMPLEMENTATION_COMPLETED,
                ObjectKind.IMPLEMENTATION,
                record.id,
                actor,
                at,
                uuid4(),
                related,
                summary,
                version,
            ),
        )
        events += tuple(
            outcome_event(
                EventType.IMPLEMENTATION_DEVIATION_RECORDED,
                ObjectKind.IMPLEMENTATION,
                record.id,
                actor,
                at,
                uuid4(),
                (d.id, record.spec_id),
                d.rationale,
                version,
            )
            for d in deviations
        )
        return ImplementationRecord.model_validate(
            {
                **record.model_dump(),
                "previous": record,
                "version": version,
                "status": ImplementationStatus.COMPLETED,
                "recorded_by": actor,
                "recorded_at": at,
                "completed_at": at,
                "summary": summary,
                "delivered_scope": delivered_scope,
                "delivered_item_ids": delivered_item_ids,
                "deviations": deviations,
                "omitted_scope": omitted_scope,
                "artifact_references": artifact_references,
                "release_references": release_references,
                "limitations": limitations,
                "events": events,
            }
        )

    def cancel_implementation(
        self,
        record: ImplementationRecord,
        *,
        actor: Actor,
        at: datetime,
        reason: str,
    ) -> ImplementationRecord:
        record = ImplementationRecord.model_validate(record)
        version = record.version + 1
        return ImplementationRecord.model_validate(
            {
                **record.model_dump(),
                "previous": record,
                "version": version,
                "status": ImplementationStatus.CANCELLED,
                "recorded_by": actor,
                "recorded_at": at,
                "summary": reason,
                "events": (
                    outcome_event(
                        EventType.IMPLEMENTATION_CANCELLED,
                        ObjectKind.IMPLEMENTATION,
                        record.id,
                        actor,
                        at,
                        uuid4(),
                        (
                            record.authorization.id,
                            record.hypothesis_id,
                            record.selection_id,
                            record.spec_id,
                        ),
                        reason,
                        version,
                    ),
                ),
            }
        )

    def record_release(
        self,
        record: ImplementationRecord,
        *,
        environment: str,
        audience: str,
        released_at: datetime,
        rollout_scope: str,
        version_reference: str,
        provenance: Provenance,
        actor: Actor,
        at: datetime,
        limitations: tuple[str, ...] = (),
    ) -> ReleaseObservation:
        record_id = uuid4()
        return ReleaseObservation(
            id=record_id,
            implementation=record,
            environment=environment,
            audience=audience,
            released_at=released_at,
            rollout_scope=rollout_scope,
            version_reference=version_reference,
            provenance=provenance,
            observed_by=actor,
            recorded_at=at,
            limitations=limitations,
            event=outcome_event(
                EventType.RELEASE_OBSERVED,
                ObjectKind.RELEASE_OBSERVATION,
                record_id,
                actor,
                at,
                uuid4(),
                (record.id,),
                rollout_scope,
            ),
        )

    def _transition(
        self,
        hypothesis: Hypothesis,
        record: ImplementationRecord,
        target: HypothesisStatus,
        kind: EventType,
        related: tuple[UUID, ...],
        *,
        actor: Actor,
        at: datetime,
        rationale: str,
        plan: OutcomeMeasurementPlan | None = None,
        review: OutcomeReview | None = None,
    ) -> OutcomeLifecycleChange:
        hypothesis = Hypothesis.model_validate(hypothesis)
        after = Hypothesis.model_validate(
            {
                **hypothesis.model_dump(),
                "status": target,
                "version": hypothesis.version + 1,
                "updated_at": at,
            }
        )
        event = AuditEvent(
            id=uuid4(),
            actor=actor,
            occurred_at=at,
            event_type=kind,
            target=AuditTarget(kind=ObjectKind.HYPOTHESIS, id=hypothesis.id),
            metadata=AuditMetadata(
                previous_version=hypothesis.version,
                resulting_version=after.version,
                previous_status=hypothesis.status.value,
                resulting_status=target.value,
                changed_fields=("status",),
                related_ids=related,
                reason=rationale,
            ),
        )
        return OutcomeLifecycleChange(
            before=hypothesis,
            after=after,
            implementation=record,
            plan=plan,
            review=review,
            policy=self.policy,
            rationale=rationale,
            event=event,
        )

    def mark_implemented(
        self,
        hypothesis: Hypothesis,
        record: ImplementationRecord,
        *,
        actor: Actor,
        at: datetime,
        rationale: str,
    ) -> OutcomeLifecycleChange:
        return self._transition(
            hypothesis,
            record,
            HypothesisStatus.IMPLEMENTED,
            EventType.HYPOTHESIS_IMPLEMENTED,
            (record.id,),
            actor=actor,
            at=at,
            rationale=rationale,
        )

    def baseline(
        self,
        implementation_id: UUID,
        metric_id: UUID,
        *,
        value: float | str | None,
        period: MeasurementWindow,
        population: str,
        source: SourceReference,
        methodology: str,
        provenance: Provenance,
        actor: Actor,
        at: datetime,
        unknown_reason: str | None = None,
        limitations: tuple[str, ...] = (),
    ) -> BaselineObservation:
        record_id = uuid4()
        return BaselineObservation(
            id=record_id,
            implementation_id=implementation_id,
            metric_id=metric_id,
            value=value,
            unknown_reason=unknown_reason,
            period=period,
            population=population,
            source=source,
            collected_at=at,
            methodology=methodology,
            limitations=limitations,
            provenance=provenance,
            recorded_by=actor,
            event=outcome_event(
                EventType.OUTCOME_BASELINE_RECORDED,
                ObjectKind.OUTCOME_BASELINE,
                record_id,
                actor,
                at,
                uuid4(),
                (implementation_id, metric_id),
                methodology,
            ),
        )

    def _plan_events(
        self,
        plan_id: UUID,
        record: ImplementationRecord,
        hypothesis: Hypothesis,
        metrics: tuple[OutcomeMetricDefinition, ...],
        actor: Actor,
        at: datetime,
        reason: str,
        version: int,
        previous: OutcomeMeasurementPlan | None,
    ) -> tuple[AuditEvent, ...]:
        events: tuple[AuditEvent, ...] = (
            outcome_event(
                EventType.OUTCOME_PLAN_REVISED if previous else EventType.OUTCOME_PLAN_CREATED,
                ObjectKind.OUTCOME_PLAN,
                plan_id,
                actor,
                at,
                uuid4(),
                (record.id, hypothesis.id),
                reason,
                version,
            ),
        )
        old = {m.id: m for m in previous.metrics} if previous else {}
        for metric in metrics:
            if metric.id not in old and metric.target is not None:
                events += (
                    outcome_event(
                        EventType.OUTCOME_TARGET_RECORDED,
                        ObjectKind.OUTCOME_PLAN,
                        plan_id,
                        actor,
                        at,
                        uuid4(),
                        (metric.id,),
                        metric.target.definition,
                        version,
                    ),
                )
            elif metric.id in old and metric.target != old[metric.id].target:
                events += (
                    outcome_event(
                        EventType.OUTCOME_TARGET_REVISED,
                        ObjectKind.OUTCOME_PLAN,
                        plan_id,
                        actor,
                        at,
                        uuid4(),
                        (metric.id,),
                        reason,
                        version,
                    ),
                )
        return events

    def create_plan(
        self,
        hypothesis: Hypothesis,
        record: ImplementationRecord,
        *,
        metrics: tuple[OutcomeMetricDefinition, ...],
        baselines: tuple[BaselineObservation, ...],
        window: MeasurementWindow,
        observation_source: str,
        analysis_method: str,
        owner: Owner,
        actor: Actor,
        at: datetime,
        reason: str,
        confounders: tuple[str, ...] = (),
        interpretation_risks: tuple[str, ...] = (),
        releases: tuple[ReleaseObservation, ...] = (),
    ) -> OutcomeMeasurementPlan:
        plan_id = uuid4()
        return OutcomeMeasurementPlan(
            id=plan_id,
            hypothesis=hypothesis,
            implementation=record,
            desired_outcome_reference=SpecReference(
                kind=ReferenceKind.HYPOTHESIS,
                id=str(hypothesis.id),
                version=hypothesis.version,
                field="desired_outcome",
            ),
            desired_outcome=hypothesis.content.desired_outcome,
            metrics=metrics,
            baselines=baselines,
            releases=releases,
            window=window,
            observation_source=observation_source,
            analysis_method=analysis_method,
            owner=owner,
            confounders=confounders,
            interpretation_risks=interpretation_risks,
            created_at=at,
            recorded_at=at,
            recorded_by=actor,
            reason=reason,
            post_hoc=at >= min(m.outcome_period.start for m in metrics) if metrics else False,
            events=self._plan_events(
                plan_id, record, hypothesis, metrics, actor, at, reason, 1, None
            ),
        )

    def revise_plan(
        self,
        plan: OutcomeMeasurementPlan,
        *,
        metrics: tuple[OutcomeMetricDefinition, ...],
        baselines: tuple[BaselineObservation, ...],
        actor: Actor,
        at: datetime,
        reason: str,
        observations: tuple[OutcomeObservation, ...] = (),
        releases: tuple[ReleaseObservation, ...] | None = None,
    ) -> OutcomeMeasurementPlan:
        plan = OutcomeMeasurementPlan.model_validate(plan)
        if any(o.plan != plan or o.collected_at > at for o in observations):
            raise ValueError("revision observations must belong to the supplied current plan")
        earliest = min(m.outcome_period.start for m in plan.metrics + metrics)
        return OutcomeMeasurementPlan.model_validate(
            {
                **plan.model_dump(),
                "previous": plan,
                "version": plan.version + 1,
                "metrics": metrics,
                "baselines": baselines,
                "releases": plan.releases if releases is None else releases,
                "recorded_by": actor,
                "recorded_at": at,
                "reason": reason,
                "post_hoc": plan.post_hoc or at >= earliest,
                "events": self._plan_events(
                    plan.id,
                    plan.implementation,
                    plan.hypothesis,
                    metrics,
                    actor,
                    at,
                    reason,
                    plan.version + 1,
                    plan,
                ),
            }
        )

    def begin_measurement(
        self,
        hypothesis: Hypothesis,
        record: ImplementationRecord,
        plan: OutcomeMeasurementPlan,
        *,
        actor: Actor,
        at: datetime,
        rationale: str,
    ) -> OutcomeLifecycleChange:
        return self._transition(
            hypothesis,
            record,
            HypothesisStatus.MEASURING_OUTCOME,
            EventType.HYPOTHESIS_MEASURING_OUTCOME,
            (record.id, plan.id),
            actor=actor,
            at=at,
            rationale=rationale,
            plan=plan,
        )

    def observe(
        self,
        plan: OutcomeMeasurementPlan,
        metric_id: UUID,
        *,
        value: float | str | None,
        period: MeasurementWindow,
        population: str,
        source: SourceReference,
        methodology: str,
        provenance: Provenance,
        actor: Actor,
        at: datetime,
        unknown_reason: str | None = None,
        limitations: tuple[str, ...] = (),
    ) -> OutcomeObservation:
        record_id = uuid4()
        return OutcomeObservation(
            id=record_id,
            plan=plan,
            implementation_id=plan.implementation.id,
            metric_id=metric_id,
            value=value,
            unknown_reason=unknown_reason,
            period=period,
            population=population,
            source=source,
            collected_at=at,
            methodology=methodology,
            limitations=limitations,
            provenance=provenance,
            recorded_by=actor,
            event=outcome_event(
                EventType.OUTCOME_OBSERVED,
                ObjectKind.OUTCOME_OBSERVATION,
                record_id,
                actor,
                at,
                uuid4(),
                (plan.id, plan.implementation.id, metric_id),
                methodology,
                plan.version,
            ),
        )

    def evaluate(
        self,
        plan: OutcomeMeasurementPlan,
        metric_id: UUID,
        observations: tuple[OutcomeObservation, ...],
        *,
        actor: Actor,
        at: datetime,
    ) -> OutcomeMetricEvaluation:
        plan = OutcomeMeasurementPlan.model_validate(plan)
        observations = tuple(OutcomeObservation.model_validate(o) for o in observations)
        record_id = uuid4()
        return OutcomeMetricEvaluation(
            id=record_id,
            plan=plan,
            metric_id=metric_id,
            observations=observations,
            policy=self.policy,
            result=compare_target(plan, metric_id, observations, self.policy, at),
            evaluated_by=actor,
            evaluated_at=at,
            event=outcome_event(
                EventType.OUTCOME_EVALUATED,
                ObjectKind.OUTCOME_EVALUATION,
                record_id,
                actor,
                at,
                uuid4(),
                (plan.id, metric_id),
                self.policy.version,
                plan.version,
            ),
        )

    def assess(
        self,
        plan: OutcomeMeasurementPlan,
        evaluations: tuple[OutcomeMetricEvaluation, ...],
    ) -> OutcomeAssessment:
        return OutcomeAssessment(
            plan=plan,
            evaluations=evaluations,
            disposition=assessment_disposition(evaluations),
            limitations=tuple(
                dict.fromkeys(
                    x
                    for e in evaluations
                    for x in e.result.limitations + e.result.missing_information
                )
            ),
        )

    def interpret_causality(
        self,
        plan: OutcomeMeasurementPlan,
        scope: EvidenceScope,
        *,
        claim: str,
        state: CausalState,
        design: StudyDesign,
        design_basis: str,
        confounders: tuple[str, ...],
        limitations: tuple[str, ...],
        interpretation: str,
        actor: Actor,
        at: datetime,
        supporting: tuple[Evidence, ...] = (),
        contradicting: tuple[Evidence, ...] = (),
        quality: tuple[EvidenceQualityAssessment, ...] = (),
        assignment_notes: str | None = None,
        instrumentation_notes: str | None = None,
        exposure_population: str | None = None,
    ) -> CausalInterpretation:
        record_id = uuid4()
        return CausalInterpretation(
            id=record_id,
            plan=plan,
            scope=scope,
            claim=claim,
            state=state,
            design=design,
            design_basis=design_basis,
            confounders=confounders,
            limitations=limitations,
            interpretation=interpretation,
            reviewed_by=actor,
            reviewed_at=at,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            quality=quality,
            assignment_notes=assignment_notes,
            instrumentation_notes=instrumentation_notes,
            exposure_population=exposure_population,
            event=outcome_event(
                EventType.CAUSAL_INTERPRETATION_RECORDED,
                ObjectKind.CAUSAL_INTERPRETATION,
                record_id,
                actor,
                at,
                uuid4(),
                (plan.id, plan.implementation.id),
                interpretation,
            ),
        )

    def materialize_evidence(
        self,
        hypothesis: Hypothesis,
        observation: OutcomeObservation,
        prior_evidence: tuple[Evidence, ...],
        *,
        direction: EvidenceDirection,
        rationale: str,
        actor: Actor,
        at: datetime,
        causal_interpretation: CausalInterpretation | None = None,
    ) -> OutcomeEvidenceFeedback:
        observation = OutcomeObservation.model_validate(observation)
        metric = observation.plan.metric(observation.metric_id)
        record, scope = observation.plan.implementation, metric.feedback_scope
        evidence = Evidence(
            id=uuid4(),
            hypothesis_id=hypothesis.id,
            statement=(
                f"{metric.name}: observed {observation.value} {metric.unit}. "
                f"Human feedback: {rationale}"
            ),
            source=observation.source,
            collected_on=observation.collected_at.astimezone(UTC).date(),
            target=scope.target,
            target_claim_id=scope.claim_id,
            target_assumption_id=scope.assumption_id,
            population=scope.population,
            direction=direction,
            methodology_notes=outcome_methodology(observation),
            provenance=observation.provenance,
            outcome_provenance=PostImplementationProvenance(
                implementation_id=record.id,
                selection_id=record.selection_id,
                spec_id=record.spec_id,
                spec_version=record.spec_version,
                authorization_id=record.authorization.id,
                plan_id=observation.plan.id,
                plan_version=observation.plan.version,
                metric_id=metric.id,
                observation_id=observation.id,
            ),
        )
        change = link_evidence(hypothesis, evidence, actor=actor, at=at, event_id=uuid4())
        return OutcomeEvidenceFeedback(
            observation=observation,
            prior_evidence=prior_evidence,
            evidence=evidence,
            change=change,
            rationale=rationale,
            causal_interpretation=causal_interpretation,
            event=outcome_event(
                EventType.OUTCOME_EVIDENCE_ADDED,
                ObjectKind.EVIDENCE,
                evidence.id,
                actor,
                at,
                uuid4(),
                (record.id, observation.plan.id, observation.id),
                rationale,
            ),
        )

    def review(
        self,
        hypothesis: Hypothesis,
        assessment: OutcomeAssessment,
        *,
        causal_interpretations: tuple[CausalInterpretation, ...],
        evidence: tuple[Evidence, ...],
        actor: Actor,
        at: datetime,
        rationale: str,
        actions: tuple[FollowUpAction, ...],
        follow_up_learning: tuple[str, ...],
        unresolved_questions: tuple[str, ...],
        acknowledged_limitations: tuple[str, ...],
    ) -> OutcomeReview:
        record_id = uuid4()
        plan = assessment.plan
        return OutcomeReview(
            id=record_id,
            hypothesis=hypothesis,
            assessment=assessment,
            causal_interpretations=causal_interpretations,
            evidence=evidence,
            reviewer=actor,
            reviewed_at=at,
            rationale=rationale,
            actions=actions,
            follow_up_learning=follow_up_learning,
            unresolved_questions=unresolved_questions,
            acknowledged_limitations=acknowledged_limitations,
            event=outcome_event(
                EventType.OUTCOME_REVIEW_COMPLETED,
                ObjectKind.OUTCOME_REVIEW,
                record_id,
                actor,
                at,
                uuid4(),
                (hypothesis.id, plan.implementation.id, plan.id),
                rationale,
                plan.version,
            ),
        )

    def link_follow_up(
        self,
        review: OutcomeReview,
        follow_up: Hypothesis,
        outcome_evidence_ids: tuple[UUID, ...],
        *,
        actor: Actor,
        at: datetime,
        rationale: str,
    ) -> FollowUpLearning:
        record_id = uuid4()
        return FollowUpLearning(
            id=record_id,
            review=review,
            follow_up_hypothesis=follow_up,
            outcome_evidence_ids=outcome_evidence_ids,
            linked_by=actor,
            linked_at=at,
            rationale=rationale,
            event=outcome_event(
                EventType.FOLLOW_UP_LEARNING_LINKED,
                ObjectKind.FOLLOW_UP_LEARNING,
                record_id,
                actor,
                at,
                uuid4(),
                (review.id, follow_up.id) + outcome_evidence_ids,
                rationale,
            ),
        )

    def close(
        self,
        hypothesis: Hypothesis,
        record: ImplementationRecord,
        plan: OutcomeMeasurementPlan,
        review: OutcomeReview,
        *,
        actor: Actor,
        at: datetime,
        rationale: str,
    ) -> OutcomeLifecycleChange:
        return self._transition(
            hypothesis,
            record,
            HypothesisStatus.CLOSED,
            EventType.HYPOTHESIS_CLOSED,
            (record.id, plan.id, review.id),
            actor=actor,
            at=at,
            rationale=rationale,
            plan=plan,
            review=review,
        )
