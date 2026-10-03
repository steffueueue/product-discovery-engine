"""Original input text is immutable and preserved exactly as supplied."""

from uuid import UUID

from pydantic import AwareDatetime, StrictStr, field_validator

from .common import DomainModel, Owner, SourceReference


class Submission(DomainModel):
    id: UUID
    original_text: StrictStr
    source: SourceReference
    submitter: Owner | None
    created_at: AwareDatetime

    @field_validator("original_text")
    @classmethod
    def require_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("original text cannot be blank")
        return value
