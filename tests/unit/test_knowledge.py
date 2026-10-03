from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from product_discovery_engine.domain.assumptions import (
    Assumption,
    AssumptionCategory,
    Importance,
    Uncertainty,
    ValidationState,
)
from product_discovery_engine.domain.claims import Claim, ClaimKind
from product_discovery_engine.domain.common import Owner, Provenance, SourceReference, Unknown
from product_discovery_engine.domain.submissions import Submission


def test_original_submission_preserves_whitespace_and_is_frozen(source: SourceReference) -> None:
    text = "  Original wording\nwith uncertainty.  "
    submission = Submission(
        id=UUID(int=2),
        original_text=text,
        source=source,
        submitter=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert submission.original_text == text
    with pytest.raises(ValidationError, match="frozen"):
        submission.original_text = "rewritten"  # type: ignore[misc]  # Exercise runtime immutability.
    assert Submission.model_validate_json(submission.model_dump_json()) == submission


@pytest.mark.parametrize("text", ["", "  \n "])
def test_blank_submission_rejected(text: str, source: SourceReference) -> None:
    with pytest.raises(ValidationError):
        Submission(
            id=UUID(int=2),
            original_text=text,
            source=source,
            submitter=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


@pytest.mark.parametrize("kind", list(ClaimKind))
def test_claim_categories(kind: ClaimKind, provenance: Provenance) -> None:
    claim = Claim(
        id=UUID(int=3),
        kind=kind,
        statement="Explicit knowledge",
        provenance=None if kind == ClaimKind.UNKNOWN else provenance,
        evidence_ids=(UUID(int=4),) if kind == ClaimKind.EVIDENCE else (),
        assumption_id=UUID(int=5) if kind == ClaimKind.ASSUMPTION else None,
    )
    assert claim.kind == kind


@pytest.mark.parametrize(
    "kind", [ClaimKind.FACT, ClaimKind.INFERENCE, ClaimKind.ASSUMPTION, ClaimKind.EVIDENCE]
)
def test_known_claim_requires_provenance(kind: ClaimKind) -> None:
    with pytest.raises(ValidationError, match="provenance"):
        Claim(id=UUID(int=3), kind=kind, statement="Unsupported assertion", provenance=None)


def test_claim_specific_references(provenance: Provenance) -> None:
    for kind in (ClaimKind.EVIDENCE, ClaimKind.ASSUMPTION):
        with pytest.raises(ValidationError, match="reference"):
            Claim(id=UUID(int=3), kind=kind, statement="Missing link", provenance=provenance)
    with pytest.raises(ValidationError):
        Claim(
            id=UUID(int=3),
            kind=ClaimKind.FACT,
            statement="Not an assumption",
            provenance=provenance,
            assumption_id=UUID(int=5),
        )
    with pytest.raises(ValidationError):
        Claim(
            id=UUID(int=3),
            kind=ClaimKind.UNKNOWN,
            statement="Not known",
            provenance=None,
            evidence_ids=(UUID(int=4),),
        )


def test_provenance_cannot_be_ai_summary_alone(source: SourceReference) -> None:
    with pytest.raises(ValidationError, match="underlying source"):
        Provenance(sources=(), ai_generated=True, interpretation_notes="AI summary")
    value = Provenance(sources=(source,), ai_generated=True, interpretation_notes="Summary")
    assert value.sources == (source,)
    with pytest.raises(ValidationError):
        value.sources[0].reference = "changed"  # type: ignore[misc]  # Exercise runtime immutability.


def test_owner_identity_and_unknown() -> None:
    with pytest.raises(ValidationError):
        Owner(id=UUID(int=1), display_name=" ")
    with pytest.raises(ValidationError):
        Unknown(reason="")
    assert Unknown(reason="Segment not researched").reason == "Segment not researched"


def test_assumption_is_qualitative_and_keeps_ai_origin(
    source: SourceReference, owner: Owner
) -> None:
    assumption = Assumption(
        id=UUID(int=5),
        statement="Users prefer guided setup",
        category=AssumptionCategory.USABILITY,
        importance=Importance.HIGH,
        uncertainty=Uncertainty.UNKNOWN,
        owner=owner,
        provenance=Provenance(sources=(source,), ai_generated=True),
    )
    assert assumption.ai_generated
    assert assumption.validation_state == ValidationState.UNTESTED
    assert assumption.evidence_ids == ()
    data = assumption.model_dump()
    data["uncertainty"] = 0.95
    with pytest.raises(ValidationError):
        Assumption.model_validate(data)


def test_naive_timestamp_and_extra_fields_rejected(source: SourceReference) -> None:
    data = {
        "id": UUID(int=2),
        "original_text": "Input",
        "source": source,
        "submitter": None,
        "created_at": datetime(2026, 1, 1),
    }
    with pytest.raises(ValidationError, match="timezone"):
        Submission.model_validate(data)
    data["created_at"] = datetime(2026, 1, 1, tzinfo=UTC)
    data["secret_field"] = "not accepted"
    with pytest.raises(ValidationError, match="extra"):
        Submission.model_validate(data)


def test_unknown_source_and_assumption_category_are_distinct_from_other() -> None:
    from product_discovery_engine.domain.common import SourceType

    source = SourceReference(source_type=SourceType.UNKNOWN, reference="submission:42")
    assumption = Assumption(
        id=UUID(int=5),
        statement="Unclassified assumption",
        category=AssumptionCategory.UNKNOWN,
        importance=Importance.UNKNOWN,
        uncertainty=Uncertainty.UNKNOWN,
        provenance=Provenance(sources=(source,)),
    )
    assert source.source_type != SourceType.OTHER
    assert assumption.category != AssumptionCategory.OTHER
    assert assumption.owner is None
    assert source.owner is None


@pytest.mark.parametrize("kind", ["claim", "assumption", "provenance"])
def test_duplicate_references_are_rejected(kind: str, provenance: Provenance) -> None:
    duplicates = (UUID(int=4), UUID(int=4))
    with pytest.raises(ValidationError, match="duplicate references"):
        if kind == "claim":
            Claim(
                id=UUID(int=3),
                kind=ClaimKind.EVIDENCE,
                statement="Repeated evidence",
                provenance=provenance,
                evidence_ids=duplicates,
            )
        elif kind == "assumption":
            Assumption(
                id=UUID(int=5),
                statement="Repeated evidence",
                category=AssumptionCategory.OTHER,
                importance=Importance.UNKNOWN,
                uncertainty=Uncertainty.UNKNOWN,
                provenance=provenance,
                evidence_ids=duplicates,
            )
        else:
            Provenance(sources=provenance.sources, submission_ids=duplicates)


def test_unknown_ai_origin_is_not_silently_classified_as_human(source: SourceReference) -> None:
    provenance = Provenance(sources=(source,))
    assumption = Assumption(
        id=UUID(int=5),
        statement="Origin not yet established",
        category=AssumptionCategory.UNKNOWN,
        importance=Importance.UNKNOWN,
        uncertainty=Uncertainty.UNKNOWN,
        provenance=provenance,
    )
    assert provenance.ai_generated is None
    assert assumption.ai_generated is None
    assert Assumption.model_validate_json(assumption.model_dump_json()).ai_generated is None


def test_explicit_non_ai_origin_is_preserved(source: SourceReference) -> None:
    assert Provenance(sources=(source,), ai_generated=False).ai_generated is False


@pytest.mark.parametrize("value", [0, 1, "false", "true"])
def test_ai_origin_is_a_boolean_or_unknown(source: SourceReference, value: object) -> None:
    with pytest.raises(ValidationError):
        Provenance.model_validate({"sources": (source,), "ai_generated": value})


def test_provenance_cannot_repeat_the_same_source(source: SourceReference) -> None:
    with pytest.raises(ValidationError, match="duplicate source"):
        Provenance(sources=(source, source))


@pytest.mark.parametrize("value", [b"original bytes", bytearray(b"original bytes"), 42, True])
def test_submission_requires_original_text_without_coercion(
    source: SourceReference,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        Submission.model_validate(
            {
                "id": UUID(int=2),
                "original_text": value,
                "source": source,
                "submitter": None,
                "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )


def test_submission_preserves_unicode_and_spacing_on_serialization(source: SourceReference) -> None:
    text = "  Café\tCafe\u0301\n用户\n  "
    original = Submission(
        id=UUID(int=2),
        original_text=text,
        source=source,
        submitter=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    restored = Submission.model_validate_json(original.model_dump_json())
    assert restored.original_text == text
    assert restored.original_text.encode("utf-8") == text.encode("utf-8")
