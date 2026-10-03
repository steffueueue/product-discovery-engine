from datetime import UTC, datetime
from uuid import UUID

import pytest

from product_discovery_engine.domain.audit import Actor, ActorKind
from product_discovery_engine.domain.common import Owner, Provenance, SourceReference, SourceType
from product_discovery_engine.domain.hypotheses import (
    Hypothesis,
    HypothesisContent,
    HypothesisLinks,
)


@pytest.fixture
def owner() -> Owner:
    return Owner(id=UUID(int=1), display_name="Product owner")


@pytest.fixture
def actor(owner: Owner) -> Actor:
    return Actor(kind=ActorKind.HUMAN, id="user-1", owner=owner)


@pytest.fixture
def source(owner: Owner) -> SourceReference:
    return SourceReference(source_type=SourceType.INTERVIEW, reference="interview:42", owner=owner)


@pytest.fixture
def provenance(source: SourceReference) -> Provenance:
    return Provenance(sources=(source,))


@pytest.fixture
def hypothesis(owner: Owner) -> Hypothesis:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    return Hypothesis(
        id=UUID(int=10),
        content=HypothesisContent(
            title="Improve onboarding",
            owner=owner,
            problem_statement="Users cannot find setup instructions",
            target_segment="New users",
            desired_outcome="Users complete setup unaided",
        ),
        links=HypothesisLinks(submission_ids=(UUID(int=2),)),
        created_at=at,
        updated_at=at,
    )
