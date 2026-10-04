"""Explicit stage graph; candidacy requires the separate audited discovery gate operation."""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


class HypothesisStatus(StrEnum):
    NEW = "new"
    STRUCTURED = "structured"
    NEEDS_EVIDENCE = "needs_evidence"
    READY_TO_VALIDATE = "ready_to_validate"
    VALIDATING = "validating"
    EVIDENCE_UPDATED = "evidence_updated"
    CANDIDATE_FOR_DELIVERY_PRIORITIZATION = "candidate_for_delivery_prioritization"
    SELECTED_FOR_DELIVERY = "selected_for_delivery"
    PARKED = "parked"
    REJECTED = "rejected"
    MERGED = "merged"
    IMPLEMENTED = "implemented"
    MEASURING_OUTCOME = "measuring_outcome"
    CLOSED = "closed"


S = HypothesisStatus
ALLOWED_TRANSITIONS: Mapping[HypothesisStatus, frozenset[HypothesisStatus]] = MappingProxyType(
    {
        S.NEW: frozenset({S.STRUCTURED, S.PARKED, S.REJECTED, S.MERGED}),
        S.STRUCTURED: frozenset(
            {S.NEEDS_EVIDENCE, S.READY_TO_VALIDATE, S.PARKED, S.REJECTED, S.MERGED}
        ),
        S.NEEDS_EVIDENCE: frozenset({S.READY_TO_VALIDATE, S.PARKED, S.REJECTED, S.MERGED}),
        S.READY_TO_VALIDATE: frozenset({S.VALIDATING, S.NEEDS_EVIDENCE, S.PARKED, S.REJECTED}),
        S.VALIDATING: frozenset({S.EVIDENCE_UPDATED, S.PARKED}),
        S.EVIDENCE_UPDATED: frozenset(
            {
                S.NEEDS_EVIDENCE,
                S.READY_TO_VALIDATE,
                S.CANDIDATE_FOR_DELIVERY_PRIORITIZATION,
                S.PARKED,
                S.REJECTED,
                S.MERGED,
            }
        ),
        S.CANDIDATE_FOR_DELIVERY_PRIORITIZATION: frozenset(
            {S.SELECTED_FOR_DELIVERY, S.NEEDS_EVIDENCE, S.PARKED, S.REJECTED}
        ),
        S.SELECTED_FOR_DELIVERY: frozenset({S.IMPLEMENTED, S.PARKED}),
        S.PARKED: frozenset({S.STRUCTURED, S.NEEDS_EVIDENCE, S.REJECTED, S.MERGED}),
        S.REJECTED: frozenset(),
        S.MERGED: frozenset(),
        S.IMPLEMENTED: frozenset({S.MEASURING_OUTCOME}),
        S.MEASURING_OUTCOME: frozenset({S.CLOSED}),
        S.CLOSED: frozenset(),
    }
)


class InvalidTransition(ValueError):
    """A lifecycle transition is not permitted by the domain graph."""


def require_transition(current: HypothesisStatus, target: HypothesisStatus) -> None:
    if not isinstance(current, HypothesisStatus) or not isinstance(target, HypothesisStatus):
        raise InvalidTransition("lifecycle states must be HypothesisStatus values")
    if target == HypothesisStatus.CANDIDATE_FOR_DELIVERY_PRIORITIZATION:
        raise InvalidTransition("invalid hypothesis transition: candidacy requires Discovery Gate")
    if target == HypothesisStatus.SELECTED_FOR_DELIVERY:
        raise InvalidTransition(
            "invalid hypothesis transition: selection requires Delivery Selection"
        )
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(f"invalid hypothesis transition: {current.value} -> {target.value}")
