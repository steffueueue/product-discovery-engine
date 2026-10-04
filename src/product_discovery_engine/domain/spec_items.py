"""Typed specification statements; epistemic origin is independent of human acceptance."""

import re
from enum import StrEnum
from uuid import UUID

from pydantic import model_validator

from .common import DomainModel, Text, Unknown
from .delivery_context import DeliverySpecContext, ReferenceKind, SpecReference


class SpecItemType(StrEnum):
    TITLE = "title"
    SUMMARY = "summary"
    PROBLEM = "problem"
    SEGMENT = "segment"
    OUTCOME = "outcome"
    SCOPE = "scope"
    NON_GOAL = "non_goal"
    SOLUTION = "solution"
    FUNCTIONAL_REQUIREMENT = "functional_requirement"
    BUSINESS_RULE = "business_rule"
    ACCEPTANCE_CRITERION = "acceptance_criterion"
    QUALITY_REQUIREMENT = "quality_requirement"
    INTERFACE = "interface"
    DATA_REQUIREMENT = "data_requirement"
    ANALYTICS = "analytics"
    DEPENDENCY = "dependency"
    CONSTRAINT = "constraint"
    RISK = "risk"
    OPEN_QUESTION = "open_question"


class ContentOrigin(StrEnum):
    SOURCE_BACKED = "source_backed"
    HUMAN_DECISION = "human_decision"
    AI_PROPOSAL = "ai_proposal"
    UNKNOWN = "unknown"


class SpecStatement(DomainModel):
    statement: Text | Unknown
    origin: ContentOrigin
    references: tuple[SpecReference, ...]

    @model_validator(mode="after")
    def validate_statement(self) -> "SpecStatement":
        if len(set(self.references)) != len(self.references):
            raise ValueError("duplicate spec item references")
        if (self.origin == ContentOrigin.UNKNOWN) != isinstance(self.statement, Unknown):
            raise ValueError("unknown content must remain explicitly Unknown")
        if self.origin in {ContentOrigin.SOURCE_BACKED, ContentOrigin.HUMAN_DECISION}:
            if not self.references:
                raise ValueError("source-backed/human decision statements require references")
        return self


class AcceptanceCriterion(DomainModel):
    given: SpecStatement
    when: SpecStatement
    then: SpecStatement


class SpecItem(SpecStatement):
    id: UUID
    kind: SpecItemType
    acceptance_criterion: AcceptanceCriterion | None = None

    @model_validator(mode="after")
    def validate_item(self) -> "SpecItem":
        if self.acceptance_criterion is not None:
            if self.kind != SpecItemType.ACCEPTANCE_CRITERION:
                raise ValueError("structured acceptance criterion requires criterion item type")
        return self

    def statements(self) -> tuple[SpecStatement, ...]:
        if self.acceptance_criterion is None:
            return (self,)
        criterion = self.acceptance_criterion
        return (self, criterion.given, criterion.when, criterion.then)


# Discovery observations cannot establish solution requirements. Conservative exact
# restatement is the offline grounding contract; paraphrases remain proposals/decisions.
SOLUTION_ITEMS = frozenset(
    {
        SpecItemType.SCOPE,
        SpecItemType.NON_GOAL,
        SpecItemType.SOLUTION,
        SpecItemType.FUNCTIONAL_REQUIREMENT,
        SpecItemType.BUSINESS_RULE,
        SpecItemType.ACCEPTANCE_CRITERION,
        SpecItemType.QUALITY_REQUIREMENT,
        SpecItemType.INTERFACE,
        SpecItemType.DATA_REQUIREMENT,
        SpecItemType.ANALYTICS,
        SpecItemType.DEPENDENCY,
        SpecItemType.CONSTRAINT,
    }
)


def validate_spec_items(context: DeliverySpecContext, items: tuple[SpecItem, ...]) -> None:
    if len({i.id for i in items}) != len(items):
        raise ValueError("spec items require unique IDs")
    sources = {s.reference: s.statement for s in context.sources()}
    for item in items:
        validate_statement(sources, item, item.kind)
        if item.acceptance_criterion is not None:
            for clause in (
                item.acceptance_criterion.given,
                item.acceptance_criterion.when,
                item.acceptance_criterion.then,
            ):
                validate_statement(sources, clause, SpecItemType.ACCEPTANCE_CRITERION)


def validate_statement(
    sources: dict[SpecReference, str | Unknown], item: SpecStatement, kind: SpecItemType
) -> None:
    if any(ref not in sources for ref in item.references):
        raise ValueError("invented or cross-hypothesis reference absent from drafting context")
    if item.origin == ContentOrigin.AI_PROPOSAL:
        wording = [item.statement] if isinstance(item.statement, str) else []
        # Conservative v1: concrete numbers/endpoints need exact source-backed or
        # explicit human-decision wording, not generated free text. This is not
        # a general natural-language truth/entailment classifier.
        if any(re.search(r"\d", value) for value in wording):
            raise ValueError(
                "numeric AI wording requires explicit sourced or human-decision content"
            )
        if kind in SOLUTION_ITEMS and any(
            re.search(r"(?:(?<!\w)/\w|\b(?:GET|POST|PUT|PATCH|DELETE)\b)", value)
            for value in wording
        ):
            raise ValueError("AI cannot fabricate interface endpoint details")
        if kind == SpecItemType.SOLUTION and not any(
            sources[r] == item.statement
            and (
                r.kind == ReferenceKind.HUMAN_DECISION
                or (r.kind == ReferenceKind.HYPOTHESIS and r.field == "solution_hypothesis")
            )
            for r in item.references
        ):
            raise ValueError("AI cannot fill an absent solution hypothesis")
    if item.origin == ContentOrigin.SOURCE_BACKED:
        if any(r.kind == ReferenceKind.HUMAN_DECISION for r in item.references):
            raise ValueError("human decisions must retain human-decision origin")
        if not any(sources[r] == item.statement for r in item.references):
            raise ValueError("source-backed statement must exactly preserve supplied source")
        if kind in SOLUTION_ITEMS and not any(
            sources[r] == item.statement
            and (
                r.kind
                in {
                    ReferenceKind.CONSTRAINT,
                    ReferenceKind.SYSTEM_FACT,
                    ReferenceKind.HUMAN_DECISION,
                }
                or (r.kind == ReferenceKind.HYPOTHESIS and r.field == "solution_hypothesis")
            )
            for r in item.references
        ):
            raise ValueError(
                "discovery evidence does not automatically become a solution requirement"
            )
    if item.origin == ContentOrigin.HUMAN_DECISION:
        if not any(
            r.kind == ReferenceKind.HUMAN_DECISION and sources[r] == item.statement
            for r in item.references
        ):
            raise ValueError("human requirement must preserve an explicit supplied human decision")
