from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from product_discovery_engine.domain.audit import Actor, AuditMetadata
from product_discovery_engine.domain.common import StrategyReference
from product_discovery_engine.domain.evidence import FreshnessPolicy
from product_discovery_engine.domain.hypotheses import Hypothesis, HypothesisContent
from product_discovery_engine.domain.hypothesis_changes import revise_hypothesis
from product_discovery_engine.domain.policies import DeferredPolicy


@pytest.mark.parametrize("value", [0, -1, True, "1", 1.5, 1.0])
@pytest.mark.parametrize(
    "kind", ["hypothesis", "strategy", "evidence_policy", "audit", "deferred_policy"]
)
def test_versions_are_positive_integer_counters(
    hypothesis: Hypothesis,
    kind: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        if kind == "hypothesis":
            Hypothesis.model_validate({**hypothesis.model_dump(), "version": value})
        elif kind == "strategy":
            StrategyReference.model_validate({"id": "strategy", "version": value})
        elif kind == "evidence_policy":
            FreshnessPolicy.model_validate(
                {"version": value, "review_after_days": 30, "stale_after_days": 90}
            )
        elif kind == "audit":
            AuditMetadata.model_validate({"resulting_version": value})
        else:
            DeferredPolicy.model_validate({"version": value, "reason": "Not configured"})


def test_strategy_revision_is_a_material_audited_change(
    hypothesis: Hypothesis, actor: Actor
) -> None:
    initial = StrategyReference(id="growth", version=1)
    content = HypothesisContent.model_validate(
        {**hypothesis.content.model_dump(), "strategy": initial}
    )
    first = revise_hypothesis(
        hypothesis,
        content,
        actor=actor,
        at=hypothesis.updated_at + timedelta(days=1),
        event_id=UUID(int=100),
    )
    next_strategy = StrategyReference(id="growth", version=2)
    next_content = HypothesisContent.model_validate(
        {**content.model_dump(), "strategy": next_strategy}
    )
    second = revise_hypothesis(
        first.after,
        next_content,
        actor=actor,
        at=first.after.updated_at + timedelta(days=1),
        event_id=UUID(int=101),
    )
    assert second.before == first.after
    assert second.after.version == 3
    assert first.after.content.strategy == initial
    assert second.after.content.strategy == next_strategy
    assert second.event.metadata.changed_fields == ("strategy",)
