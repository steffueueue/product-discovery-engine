"""Deterministic material changes and the consistency of their audit history."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import model_validator

from .audit import Actor, AuditEvent, AuditMetadata, AuditTarget, EventType, ObjectKind
from .common import DomainModel
from .evidence import Evidence, EvidenceTarget
from .hypotheses import Hypothesis, HypothesisContent, HypothesisLinks
from .lifecycle import HypothesisStatus, require_transition


class HypothesisChange(DomainModel):
    """Snapshots and their audit record must describe the same version change."""

    before: Hypothesis | None
    after: Hypothesis
    event: AuditEvent

    @model_validator(mode="after")
    def validate_history(self) -> "HypothesisChange":
        metadata = self.event.metadata
        if self.event.target != AuditTarget(kind=ObjectKind.HYPOTHESIS, id=self.after.id):
            raise ValueError("audit target must identify the resulting hypothesis")
        if self.event.occurred_at != self.after.updated_at:
            raise ValueError("audit timestamp must match the resulting snapshot")
        if (metadata.resulting_version, metadata.resulting_status) != (
            self.after.version,
            self.after.status.value,
        ):
            raise ValueError("audit metadata must match the resulting snapshot")
        if self.before is None:
            if (
                self.event.event_type != EventType.OBJECT_CREATED
                or self.after.version != 1
                or self.after.status != HypothesisStatus.NEW
                or self.after.created_at != self.after.updated_at
                or metadata.previous_version is not None
                or metadata.previous_status is not None
                or metadata.changed_fields
            ):
                raise ValueError("creation must start a new history at version 1")
        else:
            if (
                self.event.event_type == EventType.OBJECT_CREATED
                or self.before.id != self.after.id
                or self.before.created_at != self.after.created_at
                or self.after.updated_at < self.before.updated_at
                or self.after.version != self.before.version + 1
                or metadata.previous_version != self.before.version
                or metadata.previous_status != self.before.status.value
            ):
                raise ValueError("audit and snapshots must preserve consecutive history")
            changed = _changed_fields(self.before, self.after)
            if not changed or (
                set(metadata.changed_fields) != set(changed)
                or len(metadata.changed_fields) != len(changed)
            ):
                raise ValueError("audit changed fields must describe material changes")
            if self.event.event_type == EventType.STATUS_CHANGED:
                if changed != ("status",):
                    raise ValueError("status events must only change status")
                require_transition(self.before.status, self.after.status)
            elif self.event.event_type == EventType.MATERIAL_FIELD_CHANGED:
                if any(field not in HypothesisContent.model_fields for field in changed):
                    raise ValueError("content revision events must only change content")
            elif self.event.event_type == EventType.EVIDENCE_ADDED:
                old_ids = self.before.links.evidence_ids
                new_ids = self.after.links.evidence_ids
                if (
                    changed != ("evidence_ids",)
                    or len(new_ids) != len(old_ids) + 1
                    or new_ids[:-1] != old_ids
                    or metadata.related_ids != new_ids[-1:]
                ):
                    raise ValueError("evidence events must identify the single added evidence")
            else:
                raise ValueError("unsupported hypothesis change event type")
        return self


def _changed_fields(before: Hypothesis, after: Hypothesis) -> tuple[str, ...]:
    content = tuple(
        name
        for name in HypothesisContent.model_fields
        if getattr(before.content, name) != getattr(after.content, name)
    )
    links = tuple(
        name
        for name in HypothesisLinks.model_fields
        if getattr(before.links, name) != getattr(after.links, name)
    )
    return content + links + (("status",) if before.status != after.status else ())


def _require_aware_time(at: datetime) -> None:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")


def _change(
    before: Hypothesis,
    *,
    actor: Actor,
    at: datetime,
    event_id: UUID,
    content: HypothesisContent,
    links: HypothesisLinks,
    status: HypothesisStatus,
    event_type: EventType,
    related_ids: tuple[UUID, ...] = (),
) -> HypothesisChange:
    _require_aware_time(at)
    if at < before.updated_at:
        raise ValueError("changes must not move time backwards")
    after = Hypothesis(
        id=before.id,
        content=content,
        links=links,
        status=status,
        version=before.version + 1,
        created_at=before.created_at,
        updated_at=at,
    )
    event = AuditEvent(
        id=event_id,
        actor=actor,
        occurred_at=at,
        event_type=event_type,
        target=AuditTarget(kind=ObjectKind.HYPOTHESIS, id=before.id),
        metadata=AuditMetadata(
            previous_version=before.version,
            resulting_version=after.version,
            previous_status=before.status.value,
            resulting_status=after.status.value,
            changed_fields=_changed_fields(before, after),
            related_ids=related_ids,
        ),
    )
    return HypothesisChange(before=before, after=after, event=event)


def create_hypothesis(
    *,
    id: UUID,
    content: HypothesisContent,
    links: HypothesisLinks,
    actor: Actor,
    at: datetime,
    event_id: UUID,
) -> HypothesisChange:
    hypothesis = Hypothesis(id=id, content=content, links=links, created_at=at, updated_at=at)
    event = AuditEvent(
        id=event_id,
        actor=actor,
        occurred_at=at,
        event_type=EventType.OBJECT_CREATED,
        target=AuditTarget(kind=ObjectKind.HYPOTHESIS, id=id),
        metadata=AuditMetadata(resulting_version=1, resulting_status=hypothesis.status.value),
    )
    return HypothesisChange(before=None, after=hypothesis, event=event)


def transition_hypothesis(
    hypothesis: Hypothesis,
    target: HypothesisStatus,
    *,
    actor: Actor,
    at: datetime,
    event_id: UUID,
) -> HypothesisChange:
    require_transition(hypothesis.status, target)
    return _change(
        hypothesis,
        actor=actor,
        at=at,
        event_id=event_id,
        content=hypothesis.content,
        links=hypothesis.links,
        status=target,
        event_type=EventType.STATUS_CHANGED,
    )


def revise_hypothesis(
    hypothesis: Hypothesis,
    content: HypothesisContent,
    *,
    actor: Actor,
    at: datetime,
    event_id: UUID,
) -> HypothesisChange:
    if content == hypothesis.content:
        raise ValueError("revision must change material content")
    return _change(
        hypothesis,
        actor=actor,
        at=at,
        event_id=event_id,
        content=content,
        links=hypothesis.links,
        status=hypothesis.status,
        event_type=EventType.MATERIAL_FIELD_CHANGED,
    )


def link_evidence(
    hypothesis: Hypothesis,
    evidence: Evidence,
    *,
    actor: Actor,
    at: datetime,
    event_id: UUID,
) -> HypothesisChange:
    _require_aware_time(at)
    if evidence.hypothesis_id != hypothesis.id:
        raise ValueError("evidence belongs to a different hypothesis")
    if evidence.id in hypothesis.links.evidence_ids:
        raise ValueError("evidence already linked")
    if (
        evidence.target == EvidenceTarget.ASSUMPTION
        and evidence.target_assumption_id not in hypothesis.links.assumption_ids
    ):
        raise ValueError("evidence target assumption must be linked to the hypothesis")
    as_of = at.astimezone(UTC).date()
    if evidence.collected_on > as_of:
        raise ValueError("cannot link evidence before collection")
    if any(
        value is not None and value > as_of
        for value in (evidence.reviewed_on, evidence.invalidated_on)
    ):
        raise ValueError("cannot link an evidence snapshot before its review/invalidation")
    links = HypothesisLinks.model_validate(
        {
            **hypothesis.links.model_dump(),
            "evidence_ids": (*hypothesis.links.evidence_ids, evidence.id),
        }
    )
    return _change(
        hypothesis,
        actor=actor,
        at=at,
        event_id=event_id,
        content=hypothesis.content,
        links=links,
        status=hypothesis.status,
        event_type=EventType.EVIDENCE_ADDED,
        related_ids=(evidence.id,),
    )
