"""Explicit drafting context and closed reference set, retaining discovery history."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .audit import Actor, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .claims import Claim, ClaimKind
from .common import DomainModel, Text, Unknown
from .delivery_selection import DeliverySelection, require_human
from .hypotheses import Hypothesis


class ReferenceKind(StrEnum):
    HYPOTHESIS = "hypothesis"
    SELECTION = "selection"
    CLAIM = "claim"
    EVIDENCE = "evidence"
    ASSUMPTION = "assumption"
    VALIDATION_RESULT = "validation_result"
    STRATEGY = "strategy"
    READINESS = "readiness"
    GATE = "gate"
    CHALLENGE = "challenge"
    HUMAN_DECISION = "human_decision"
    CONSTRAINT = "constraint"
    SYSTEM_FACT = "system_fact"
    SOURCE_ARTIFACT = "source_artifact"


class SpecReference(DomainModel):
    kind: ReferenceKind
    id: Text
    version: Annotated[int, Field(ge=1, strict=True)] | None = None
    field: Text | None = None


class ContextFact(DomainModel):
    """Explicit human supplied delivery decision, constraint or system/artifact fact."""

    id: UUID
    kind: ReferenceKind
    hypothesis_id: UUID
    statement: Text
    source_artifact: Text
    recorded_by: Actor
    recorded_at: AwareDatetime
    rationale: Text

    @model_validator(mode="after")
    def validate_fact(self) -> "ContextFact":
        require_human(self.recorded_by)
        if self.kind not in {
            ReferenceKind.HUMAN_DECISION,
            ReferenceKind.CONSTRAINT,
            ReferenceKind.SYSTEM_FACT,
            ReferenceKind.SOURCE_ARTIFACT,
        }:
            raise ValueError("explicit context must be a human decision, constraint or system fact")
        return self

    @property
    def reference(self) -> SpecReference:
        return SpecReference(kind=self.kind, id=str(self.id))


class ContextSource(DomainModel):
    reference: SpecReference
    statement: Text | Unknown


class DeliverySpecContext(DomainModel):
    id: UUID
    hypothesis: Hypothesis
    selection: DeliverySelection
    accepted_claims: tuple[Claim, ...] = ()
    delivery_facts: tuple[ContextFact, ...] = ()
    assembled_by: Actor
    assembled_at: AwareDatetime
    event: AuditEvent

    @model_validator(mode="after")
    def validate_context(self) -> "DeliverySpecContext":
        require_human(self.assembled_by)
        if self.hypothesis != self.selection.after:
            raise ValueError(
                "draft context requires exact selected hypothesis/version and selection"
            )
        if self.assembled_at < self.selection.selected_at:
            raise ValueError("context cannot precede selection")
        claims = self.accepted_claims
        if len({c.id for c in claims}) != len(claims):
            raise ValueError("duplicate accepted claims")
        for claim in claims:
            if (
                claim.id not in self.hypothesis.links.claim_ids
                or not set(claim.evidence_ids) <= set(self.hypothesis.links.evidence_ids)
                or (
                    claim.assumption_id is not None
                    and claim.assumption_id not in self.hypothesis.links.assumption_ids
                )
            ):
                raise ValueError(
                    "accepted claim must belong to this hypothesis and supplied evidence"
                )
        if len({f.id for f in self.delivery_facts}) != len(self.delivery_facts):
            raise ValueError("duplicate delivery context facts")
        for fact in self.delivery_facts:
            if fact.hypothesis_id != self.hypothesis.id or fact.recorded_at > self.assembled_at:
                raise ValueError("delivery context fact belongs to another hypothesis or future")
        if self.event != AuditEvent(
            id=self.event.id,
            actor=self.assembled_by,
            occurred_at=self.assembled_at,
            event_type=EventType.DELIVERY_CONTEXT_RECORDED,
            target=AuditTarget(kind=ObjectKind.DELIVERY_CONTEXT, id=self.id),
            metadata=AuditMetadata(
                related_ids=(self.hypothesis.id, self.selection.id)
                + tuple(f.id for f in self.delivery_facts),
                reason="Explicit allowed drafting context; human assertions retained",
            ),
        ):
            raise ValueError("context audit must retain accountable input facts")
        return self

    def sources(self) -> tuple[ContextSource, ...]:
        h = self.hypothesis
        sources = [
            ContextSource(
                reference=SpecReference(
                    kind=ReferenceKind.HYPOTHESIS, id=str(h.id), version=h.version, field=name
                ),
                statement=value if value is not None else Unknown(reason="No solution selected"),
            )
            for name in (
                "title",
                "problem_statement",
                "target_segment",
                "desired_outcome",
                "solution_hypothesis",
            )
            if (value := getattr(h.content, name)) is not None or name == "solution_hypothesis"
        ]
        sources.append(
            ContextSource(
                reference=SpecReference(kind=ReferenceKind.SELECTION, id=str(self.selection.id)),
                statement=self.selection.rationale,
            )
        )
        sources.extend(
            ContextSource(reference=f.reference, statement=f.statement) for f in self.delivery_facts
        )
        sources.extend(
            ContextSource(
                reference=SpecReference(kind=ReferenceKind.CLAIM, id=str(c.id)),
                statement=c.statement
                if c.kind in {ClaimKind.FACT, ClaimKind.EVIDENCE}
                else Unknown(reason=f"Claim remains {c.kind.value}: {c.statement}"),
            )
            for c in self.accepted_claims
        )
        readiness = self.selection.candidacy.gate.readiness
        if readiness is not None:
            inputs = readiness.inputs
            sources.extend(
                ContextSource(
                    reference=SpecReference(kind=ReferenceKind.EVIDENCE, id=str(e.id)),
                    statement=e.statement,
                )
                for k in inputs.knowledge
                for e in k.evidence
            )
            sources.extend(
                ContextSource(
                    reference=SpecReference(kind=ReferenceKind.ASSUMPTION, id=str(a.assumption.id)),
                    statement=Unknown(
                        reason=f"{a.assumption.validation_state.value}: {a.assumption.statement}"
                    ),
                )
                for a in inputs.assumptions
            )
            sources.extend(
                ContextSource(
                    reference=SpecReference(kind=ReferenceKind.VALIDATION_RESULT, id=str(v.id)),
                    statement=v.interpretation,
                )
                for v in inputs.validation_results
            )
            sources.append(
                ContextSource(
                    reference=SpecReference(kind=ReferenceKind.READINESS, id=str(readiness.id)),
                    statement=readiness.result.state.value,
                )
            )
            if inputs.strategy_context is not None:
                strategy = inputs.strategy_context
                sources.append(
                    ContextSource(
                        reference=SpecReference(
                            kind=ReferenceKind.STRATEGY,
                            id=str(strategy.reference.id),
                            version=strategy.reference.version,
                        ),
                        statement=strategy.objective,
                    )
                )
            if inputs.challenge is not None:
                sources.append(
                    ContextSource(
                        reference=SpecReference(
                            kind=ReferenceKind.CHALLENGE,
                            id=str(inputs.challenge.completion.record_id),
                        ),
                        statement=Unknown(
                            reason="Retained human Challenge Mode disposition is context"
                        ),
                    )
                )
        sources.append(
            ContextSource(
                reference=SpecReference(
                    kind=ReferenceKind.GATE, id=str(self.selection.candidacy.gate.id)
                ),
                statement=self.selection.candidacy.gate.result.state.value,
            )
        )
        return tuple(sources)
