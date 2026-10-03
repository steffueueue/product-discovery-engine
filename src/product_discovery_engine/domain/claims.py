"""Knowledge categories never implicitly promote interpretation into fact."""

from enum import StrEnum
from uuid import UUID

from pydantic import model_validator

from .common import DomainModel, Provenance, ReferenceIds, Text


class ClaimKind(StrEnum):
    FACT = "fact"
    EVIDENCE = "evidence"
    ASSUMPTION = "assumption"
    INFERENCE = "inference"
    UNKNOWN = "unknown"


class Claim(DomainModel):
    id: UUID
    kind: ClaimKind
    statement: Text
    provenance: Provenance | None
    evidence_ids: ReferenceIds = ()
    assumption_id: UUID | None = None

    @model_validator(mode="after")
    def validate_knowledge(self) -> "Claim":
        if self.kind != ClaimKind.UNKNOWN and self.provenance is None:
            raise ValueError("known claims require provenance")
        if self.kind == ClaimKind.EVIDENCE and not self.evidence_ids:
            raise ValueError("evidence claims require evidence references")
        if self.kind == ClaimKind.ASSUMPTION and self.assumption_id is None:
            raise ValueError("assumption claims require an assumption reference")
        if self.kind != ClaimKind.ASSUMPTION and self.assumption_id is not None:
            raise ValueError("assumption reference requires assumption category")
        if self.kind == ClaimKind.UNKNOWN and self.evidence_ids:
            raise ValueError("unknown claims cannot assert evidence")
        return self
