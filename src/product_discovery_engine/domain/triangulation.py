"""Structural triangulation preserves both directions and never certifies truth."""

from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from .common import DomainModel, ReferenceIds, Text
from .evidence import Evidence, EvidenceDirection
from .evidence_assessment import EvidenceScope
from .evidence_origins import OriginRelationship, SourceGroup, group_sources
from .evidence_policy import TriangulationPolicy
from .validation_methods import ValidationMethod


class TriangulationCategory(StrEnum):
    NO_EVIDENCE = "no_evidence"
    UNRESOLVED_ORIGINS = "unresolved_origins"
    SINGLE_SOURCE = "single_source"
    MULTIPLE_SOURCES = "multiple_sources"
    TRIANGULATED = "triangulated"
    MIXED_UNRESOLVED = "mixed_unresolved"


class TriangulationAssessment(DomainModel):
    scope: EvidenceScope
    relevant_evidence_ids: ReferenceIds
    relevant_item_count: Annotated[int, Field(ge=0, strict=True)]
    independent_source_group_count: Annotated[int, Field(ge=0, strict=True)]
    source_groups: tuple[SourceGroup, ...]
    methods: tuple[ValidationMethod, ...]
    independent_method_diversity: Annotated[int, Field(ge=0, strict=True)]
    supporting_groups: tuple[SourceGroup, ...]
    contradicting_groups: tuple[SourceGroup, ...]
    invalidated_evidence_ids: ReferenceIds
    category: TriangulationCategory
    explanation: Text
    policy_version: Text
    policy: TriangulationPolicy

    @model_validator(mode="after")
    def validate_structure(self) -> "TriangulationAssessment":
        active_ids = set(self.relevant_evidence_ids) - set(self.invalidated_evidence_ids)
        group_ids = [id for g in self.source_groups for id in g.evidence_ids]
        independent = tuple(g for g in self.source_groups if g.traceable)
        if (
            self.relevant_item_count != len(self.relevant_evidence_ids)
            or not set(self.invalidated_evidence_ids) <= set(self.relevant_evidence_ids)
            or len(group_ids) != len(set(group_ids))
            or set(group_ids) != active_ids
            or self.independent_source_group_count != len(independent)
            or self.independent_method_diversity != _independent_method_count(independent)
            or self.methods != tuple(sorted({m for g in independent for m in g.methods}, key=str))
            or self.policy_version != self.policy.version
        ):
            raise ValueError(
                "triangulation counts and methods must match retained groups and policy"
            )
        if any(
            g not in self.source_groups for g in self.supporting_groups + self.contradicting_groups
        ) or set(self.supporting_groups + self.contradicting_groups) != set(self.source_groups):
            raise ValueError("triangulation must expose both evidence directions for every group")
        expected = _category(
            active_ids=bool(active_ids),
            mixed=bool(self.supporting_groups and self.contradicting_groups),
            groups=self.source_groups,
            independent_count=len(independent),
            diversity=self.independent_method_diversity,
            policy=self.policy,
        )
        if self.category != expected:
            raise ValueError("triangulation category must follow deterministic policy")
        return self


def _independent_method_count(groups: tuple[SourceGroup, ...]) -> int:
    """Maximum matching: each distinct method must come from a distinct source group."""
    matched: dict[ValidationMethod, int] = {}

    def assign(index: int, visited: set[ValidationMethod]) -> bool:
        for method in groups[index].methods:
            if method in visited:
                continue
            visited.add(method)
            if method not in matched or assign(matched[method], visited):
                matched[method] = index
                return True
        return False

    for index in range(len(groups)):
        assign(index, set())
    return len(matched)


def _category(
    *,
    active_ids: bool,
    mixed: bool,
    groups: tuple[SourceGroup, ...],
    independent_count: int,
    diversity: int,
    policy: TriangulationPolicy,
) -> TriangulationCategory:
    if not active_ids:
        return TriangulationCategory.NO_EVIDENCE
    if mixed:
        return TriangulationCategory.MIXED_UNRESOLVED
    if any(not g.traceable for g in groups):
        return TriangulationCategory.UNRESOLVED_ORIGINS
    if independent_count <= 1:
        return TriangulationCategory.SINGLE_SOURCE
    if (
        independent_count >= policy.minimum_independent_groups
        and diversity >= policy.minimum_distinct_methods
    ):
        return TriangulationCategory.TRIANGULATED
    return TriangulationCategory.MULTIPLE_SOURCES


def triangulate(
    scope: EvidenceScope,
    evidence: tuple[Evidence, ...],
    relationships: tuple[OriginRelationship, ...],
    *,
    policy: TriangulationPolicy,
) -> TriangulationAssessment:
    if len({e.id for e in evidence}) != len(evidence):
        raise ValueError("duplicate evidence IDs cannot inflate triangulation")
    relevant = tuple(e for e in evidence if scope.matches(e))
    active = tuple(e for e in relevant if e.invalidated_on is None)
    groups = group_sources(active, relationships)
    supports = {e.id for e in active if e.direction == EvidenceDirection.SUPPORTS}
    contradicts = {e.id for e in active if e.direction == EvidenceDirection.CONTRADICTS}
    supporting = tuple(g for g in groups if supports.intersection(g.evidence_ids))
    contradicting = tuple(g for g in groups if contradicts.intersection(g.evidence_ids))
    independent = tuple(g for g in groups if g.traceable)
    diversity = _independent_method_count(independent)
    methods = tuple(sorted({m for g in independent for m in g.methods}, key=str))
    category = _category(
        active_ids=bool(active),
        mixed=bool(supports and contradicts),
        groups=groups,
        independent_count=len(independent),
        diversity=diversity,
        policy=policy,
    )
    return TriangulationAssessment(
        scope=scope,
        relevant_evidence_ids=tuple(e.id for e in relevant),
        relevant_item_count=len(relevant),
        independent_source_group_count=len(independent),
        source_groups=groups,
        methods=methods,
        independent_method_diversity=diversity,
        supporting_groups=supporting,
        contradicting_groups=contradicting,
        invalidated_evidence_ids=tuple(e.id for e in relevant if e.invalidated_on is not None),
        category=category,
        policy_version=policy.version,
        policy=policy,
        explanation=(
            f"{category.value}: {len(relevant)} items, {len(independent)} traceable independent "
            f"groups, {diversity} methods matched to separate groups. Both directions retained. "
            "Invalidated items remain visible but cannot confirm. Structural diversity is not "
            "evidence quality, prevalence, causal proof, or a decision to pursue."
        ),
    )
