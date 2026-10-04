"""Accountable supplied delivery reality; authorization never executes implementation."""

from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .audit import Actor, AuditEvent, EventType, ObjectKind
from .common import DomainModel, Owner, Provenance, ReferenceIds, Text
from .delivery_gate import ImplementationAuthorization
from .delivery_selection import require_human
from .outcome_audit import check_event
from .spec_content import Version
from .spec_items import SpecItemType


class ImplementationStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeviationKind(StrEnum):
    OMITTED = "requirement_omitted"
    CHANGED = "requirement_changed"
    REDUCED = "scope_reduced"
    ADDITIONAL = "additional_behavior"
    INTERFACE_CHANGED = "interface_changed"


class ImplementationDeviation(DomainModel):
    id: UUID
    kind: DeviationKind
    spec_item_id: UUID | None
    description: Text
    rationale: Text

    @model_validator(mode="after")
    def reference_boundary(self) -> "ImplementationDeviation":
        if (self.kind == DeviationKind.ADDITIONAL) != (self.spec_item_id is None):
            raise ValueError("only additional behavior has no original spec item")
        return self


DELIVERY_ITEM_TYPES = frozenset(
    {
        SpecItemType.SCOPE,
        SpecItemType.FUNCTIONAL_REQUIREMENT,
        SpecItemType.BUSINESS_RULE,
        SpecItemType.ACCEPTANCE_CRITERION,
        SpecItemType.QUALITY_REQUIREMENT,
        SpecItemType.INTERFACE,
        SpecItemType.DATA_REQUIREMENT,
        SpecItemType.ANALYTICS,
    }
)


class ImplementationRecord(DomainModel):
    id: UUID
    authorization: ImplementationAuthorization
    owner: Owner
    status: ImplementationStatus
    version: Version = 1
    recorded_by: Actor
    recorded_at: AwareDatetime
    summary: Text
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    delivered_scope: tuple[Text, ...] = ()
    delivered_item_ids: ReferenceIds = ()
    omitted_scope: tuple[Text, ...] = ()
    deviations: tuple[ImplementationDeviation, ...] = ()
    artifact_references: tuple[Text, ...] = ()
    release_references: tuple[Text, ...] = ()
    limitations: tuple[Text, ...] = ()
    previous: "ImplementationRecord | None" = None
    events: tuple[AuditEvent, ...]

    @property
    def hypothesis_id(self) -> UUID:
        return self.authorization.hypothesis_id

    @property
    def selection_id(self) -> UUID:
        return self.authorization.selection_id

    @property
    def spec_id(self) -> UUID:
        return self.authorization.spec_id

    @property
    def spec_version(self) -> int:
        return self.authorization.spec_version

    @model_validator(mode="after")
    def reconstruct(self) -> "ImplementationRecord":
        require_human(self.recorded_by)
        if self.recorded_at < self.authorization.authorized_at:
            raise ValueError("implementation cannot precede authorization")
        if self.status in {ImplementationStatus.PLANNED, ImplementationStatus.IN_PROGRESS}:
            if self.recorded_at >= self.authorization.gate.expires_at:
                raise ValueError("implementation start requires non-stale authorization")
        if self.previous is None:
            if self.version != 1 or self.status not in {
                ImplementationStatus.PLANNED,
                ImplementationStatus.IN_PROGRESS,
            }:
                raise ValueError("initial implementation must be explicitly planned or started")
        else:
            before = self.previous
            edges = {
                ImplementationStatus.PLANNED: {
                    ImplementationStatus.IN_PROGRESS,
                    ImplementationStatus.CANCELLED,
                },
                ImplementationStatus.IN_PROGRESS: {
                    ImplementationStatus.COMPLETED,
                    ImplementationStatus.CANCELLED,
                },
            }
            if (
                self.id != before.id
                or self.authorization != before.authorization
                or self.owner != before.owner
                or self.version != before.version + 1
                or self.recorded_at < before.recorded_at
                or self.status not in edges.get(before.status, set())
            ):
                raise ValueError(
                    "implementation history requires exact consecutive bound snapshots"
                )
            if before.started_at is not None and self.started_at != before.started_at:
                raise ValueError("implementation start history cannot be rewritten")
            if (
                self.status == ImplementationStatus.CANCELLED
                and self.started_at != before.started_at
            ):
                raise ValueError("cancellation cannot invent an unrecorded implementation start")
        if self.status == ImplementationStatus.PLANNED and self.started_at is not None:
            raise ValueError("planned implementation has not started")
        if self.status in {ImplementationStatus.IN_PROGRESS, ImplementationStatus.COMPLETED}:
            if self.started_at is None or not (
                self.authorization.authorized_at <= self.started_at <= self.recorded_at
            ):
                raise ValueError("started implementation requires an explicit valid start time")
            if (
                self.status == ImplementationStatus.IN_PROGRESS
                and self.started_at != self.recorded_at
            ):
                raise ValueError("start snapshot records the actual start time")
        if (self.status == ImplementationStatus.COMPLETED) != (self.completed_at is not None):
            raise ValueError("only completed delivery has a completion timestamp")
        if self.status == ImplementationStatus.COMPLETED:
            if self.completed_at != self.recorded_at or not self.delivered_scope:
                raise ValueError("completion requires accountable actual delivered scope and time")
        elif any(
            (
                self.delivered_scope,
                self.delivered_item_ids,
                self.omitted_scope,
                self.deviations,
                self.artifact_references,
                self.release_references,
            )
        ):
            raise ValueError("completion evidence cannot be claimed on unfinished implementation")
        item_ids = {i.id for i in self.authorization.current.spec.items}
        if not set(self.delivered_item_ids) <= item_ids:
            raise ValueError("delivered items must belong to the exact authorized spec")
        if len({d.id for d in self.deviations}) != len(self.deviations):
            raise ValueError("deviation IDs must be unique")
        for deviation in self.deviations:
            if deviation.spec_item_id is not None and deviation.spec_item_id not in item_ids:
                raise ValueError("deviation targets a different specification")
            if deviation.kind == DeviationKind.OMITTED:
                if deviation.spec_item_id in self.delivered_item_ids or not self.omitted_scope:
                    raise ValueError(
                        "omissions require explicit omitted scope and cannot be delivered"
                    )
            elif deviation.spec_item_id is not None:
                if deviation.spec_item_id not in self.delivered_item_ids:
                    raise ValueError("changed/reduced items must identify actual delivered items")
        if self.status == ImplementationStatus.COMPLETED:
            required = {
                i.id for i in self.authorization.current.spec.items if i.kind in DELIVERY_ITEM_TYPES
            }
            omitted = {d.spec_item_id for d in self.deviations if d.kind == DeviationKind.OMITTED}
            if not required <= set(self.delivered_item_ids) | omitted:
                raise ValueError("completion must account structurally for every delivery item")
        kind = {
            ImplementationStatus.PLANNED: EventType.IMPLEMENTATION_PLANNED,
            ImplementationStatus.IN_PROGRESS: EventType.IMPLEMENTATION_STARTED,
            ImplementationStatus.COMPLETED: EventType.IMPLEMENTATION_COMPLETED,
            ImplementationStatus.CANCELLED: EventType.IMPLEMENTATION_CANCELLED,
        }[self.status]
        kinds = (kind,) + (EventType.IMPLEMENTATION_DEVIATION_RECORDED,) * len(self.deviations)
        related = (self.authorization.id, self.hypothesis_id, self.selection_id, self.spec_id)
        if len(self.events) != len(kinds) or len({e.id for e in self.events}) != len(self.events):
            raise ValueError("implementation requires distinct operation/deviation audits")
        for index, (event, event_kind) in enumerate(zip(self.events, kinds, strict=True)):
            check_event(
                event,
                event_kind,
                ObjectKind.IMPLEMENTATION,
                self.id,
                self.recorded_by,
                self.recorded_at,
                related if index == 0 else (self.deviations[index - 1].id, self.spec_id),
                self.summary if index == 0 else self.deviations[index - 1].rationale,
                self.version,
            )
        return self


class ReleaseObservation(DomainModel):
    """An externally supplied release fact, never implied by completion."""

    id: UUID
    implementation: ImplementationRecord
    environment: Text
    audience: Text
    released_at: AwareDatetime
    rollout_scope: Text
    version_reference: Text
    provenance: Provenance
    observed_by: Actor
    recorded_at: AwareDatetime
    limitations: tuple[Text, ...] = ()
    event: AuditEvent

    @model_validator(mode="after")
    def reconstruct(self) -> "ReleaseObservation":
        if self.implementation.status != ImplementationStatus.COMPLETED:
            raise ValueError("release observation requires completed implementation")
        assert self.implementation.started_at is not None
        if not self.implementation.started_at <= self.released_at <= self.recorded_at:
            raise ValueError("release observation must preserve external chronology")
        check_event(
            self.event,
            EventType.RELEASE_OBSERVED,
            ObjectKind.RELEASE_OBSERVATION,
            self.id,
            self.observed_by,
            self.recorded_at,
            (self.implementation.id,),
            self.rollout_scope,
        )
        return self
