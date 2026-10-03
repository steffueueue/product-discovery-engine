"""Underlying origins, conservative connected families, and retained relationships."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import model_validator

from .audit import Actor, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel, ReferenceIds, Text
from .evidence import Evidence
from .validation_methods import ValidationMethod


class OriginKind(StrEnum):
    DATASET = "dataset"
    EXPERIMENT = "experiment"
    RESEARCH_STUDY = "research_study"
    INTERVIEW_STUDY = "interview_study"
    TICKET_CORPUS = "ticket_corpus"
    SURVEY = "survey"
    SOURCE_ARTIFACT = "source_artifact"


class EvidenceOrigin(DomainModel):
    id: UUID
    kind: OriginKind
    family_key: Text
    source_reference: Text
    method: ValidationMethod


class OriginRelationship(DomainModel):
    evidence_id: UUID
    origins: tuple[EvidenceOrigin, ...]
    rationale: Text
    event: AuditEvent

    @model_validator(mode="after")
    def validate_relationship(self) -> "OriginRelationship":
        if not self.origins or len({o.id for o in self.origins}) != len(self.origins):
            raise ValueError("origins must be present and unique")
        if (
            self.event.event_type != EventType.EVIDENCE_ORIGIN_LINKED
            or self.event.target != AuditTarget(kind=ObjectKind.EVIDENCE, id=self.evidence_id)
            or self.event.metadata.related_ids != tuple(o.id for o in self.origins)
            or self.event.metadata.reason != self.rationale
        ):
            raise ValueError("origin relationship and audit must agree")
        return self


def link_origins(
    evidence: Evidence,
    origins: tuple[EvidenceOrigin, ...],
    *,
    rationale: str,
    actor: Actor,
    at: datetime,
    event_id: UUID,
) -> OriginRelationship:
    if (
        at.tzinfo is None
        or at.utcoffset() is None
        or at.astimezone(UTC).date() < evidence.collected_on
    ):
        raise ValueError("origin linkage needs an aware time after collection")
    return OriginRelationship(
        evidence_id=evidence.id,
        origins=origins,
        rationale=rationale,
        event=AuditEvent(
            id=event_id,
            actor=actor,
            occurred_at=at,
            event_type=EventType.EVIDENCE_ORIGIN_LINKED,
            target=AuditTarget(kind=ObjectKind.EVIDENCE, id=evidence.id),
            metadata=AuditMetadata(related_ids=tuple(o.id for o in origins), reason=rationale),
        ),
    )


class SourceGroup(DomainModel):
    evidence_ids: ReferenceIds
    origin_ids: ReferenceIds
    family_keys: tuple[Text, ...]
    methods: tuple[ValidationMethod, ...]
    traceable: bool


def group_sources(
    evidence: tuple[Evidence, ...], relationships: tuple[OriginRelationship, ...]
) -> tuple[SourceGroup, ...]:
    """Shared families OR overlapping provenance merge transitively, even across reports.

    Unmapped items remain visible but cannot certify independent confirmation.
    Source owner and source type never make the same reference independent.
    """
    ids = {e.id for e in evidence}
    if len(ids) != len(evidence):
        raise ValueError("duplicate evidence IDs")
    if len({r.evidence_id for r in relationships}) != len(relationships):
        raise ValueError("one retained origin mapping per evidence snapshot is required")
    origins_by_id: dict[UUID, EvidenceOrigin] = {}
    for origin_relation in relationships:
        for origin in origin_relation.origins:
            if origin.id in origins_by_id and origins_by_id[origin.id] != origin:
                raise ValueError("conflicting origin snapshots")
            origins_by_id[origin.id] = origin
    by_id = {r.evidence_id: r for r in relationships}
    components: list[tuple[set[str], list[Evidence]]] = []
    for item in evidence:
        tokens = {
            "source:" + s.reference
            for s in item.provenance.sources
            if s.source_type != "ai_summary"
        }
        relation = by_id.get(item.id)
        if relation:
            tokens.update("family:" + o.family_key for o in relation.origins)
            tokens.update("source:" + o.source_reference for o in relation.origins)
        members = [item]
        remaining = []
        for old_tokens, old_members in components:
            if tokens & old_tokens:
                tokens |= old_tokens
                members.extend(old_members)
            else:
                remaining.append((old_tokens, old_members))
        # Enlarged tokens can bridge a previously skipped component.
        changed = True
        while changed:
            changed = False
            for old_tokens, old_members in remaining[:]:
                if tokens & old_tokens:
                    tokens |= old_tokens
                    members.extend(old_members)
                    remaining.remove((old_tokens, old_members))
                    changed = True
        components = [*remaining, (tokens, members)]
    result = []
    for _, members in components:
        mapped = [by_id[e.id] for e in members if e.id in by_id]
        origins = {o.id: o for r in mapped for o in r.origins}
        result.append(
            SourceGroup(
                evidence_ids=tuple(sorted((e.id for e in members), key=str)),
                origin_ids=tuple(sorted(origins, key=str)),
                family_keys=tuple(sorted({o.family_key for o in origins.values()})),
                methods=tuple(sorted({o.method for o in origins.values()}, key=str)),
                traceable=len(mapped) == len(members),
            )
        )
    return tuple(sorted(result, key=lambda g: str(g.evidence_ids[0])))
