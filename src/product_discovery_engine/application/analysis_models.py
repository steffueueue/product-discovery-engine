"""Review proposals, never authoritative evidence or lifecycle mutations."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from product_discovery_engine.domain.assumptions import AssumptionCategory, Importance, Uncertainty
from product_discovery_engine.domain.claims import ClaimKind
from product_discovery_engine.domain.common import Text


class AnalysisModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")


class IntakeClassification(StrEnum):
    OBSERVATION = "observation"
    PROBLEM = "problem"
    OPPORTUNITY = "opportunity"
    FEATURE_REQUEST = "feature_request"
    SOLUTION_IDEA = "solution_idea"
    HYPOTHESIS = "hypothesis"
    CUSTOMER_REQUEST = "customer_request"
    BUSINESS_REQUEST = "business_request"
    RESEARCH_FINDING = "research_finding"
    ANALYTICS_SIGNAL = "analytics_signal"
    TECHNICAL_SIGNAL = "technical_signal"
    OTHER = "other"


class Interpretation(AnalysisModel):
    status: Literal["hypothesis", "unknown"]
    statement: Text


class SourceCitation(AnalysisModel):
    source_id: Text
    quote: Text


class ClaimProposal(AnalysisModel):
    id: Text
    kind: ClaimKind
    statement: Text
    citations: tuple[SourceCitation, ...]
    rationale: Text
    agent_generated: Literal[True]


class AssumptionProposal(AnalysisModel):
    id: Text
    statement: Text
    category: AssumptionCategory
    rationale: Text
    importance: Importance
    uncertainty: Uncertainty
    decision_relevance: Text
    citations: tuple[SourceCitation, ...]
    agent_generated: Literal[True]


class StrategicFit(AnalysisModel):
    status: Literal["preliminary", "insufficient_strategy_context"]
    objective_ids: tuple[Text, ...]
    potential_alignment: tuple[Text, ...]
    potential_conflicts: tuple[Text, ...]
    explanation: Text


class RiskiestAssumption(AnalysisModel):
    assumption_id: Text
    decision_impact: Importance
    unresolved_uncertainty: Uncertainty
    rationale: Text


class ValidationMethod(StrEnum):
    CUSTOMER_INTERVIEW = "customer_interview"
    CONTEXTUAL_INQUIRY = "contextual_inquiry"
    SURVEY = "survey"
    SUPPORT_TICKET_ANALYSIS = "support_ticket_analysis"
    BEHAVIORAL_ANALYTICS = "behavioral_analytics"
    FUNNEL_ANALYSIS = "funnel_analysis"
    COHORT_ANALYSIS = "cohort_analysis"
    PROTOTYPE_TEST = "prototype_test"
    USABILITY_TEST = "usability_test"
    FAKE_DOOR_TEST = "fake_door_test"
    CONCIERGE_TEST = "concierge_test"
    WIZARD_OF_OZ_TEST = "wizard_of_oz_test"
    TECHNICAL_SPIKE = "technical_spike"
    ARCHITECTURE_SPIKE = "architecture_spike"
    MARKET_RESEARCH = "market_research"
    BUSINESS_CASE_ANALYSIS = "business_case_analysis"
    AB_TEST = "ab_test"
    CONTROLLED_EXPERIMENT = "controlled_experiment"


class ValidationRecommendation(AnalysisModel):
    method: ValidationMethod
    target_assumption_id: Text
    rationale: Text
    required_input: tuple[Text, ...]
    success_signal: Text
    failure_signal: Text
    relative_cost: Literal["low", "medium", "high"]
    relative_speed: Literal["fast", "medium", "slow"]
    cheaper_alternatives_considered: Text


class ContradictorySignal(AnalysisModel):
    claim_ids: tuple[Text, ...]
    competing_explanations: tuple[Text, ...]
    explanation: Text


class DiscoveryAnalysis(AnalysisModel):
    intake_classification: IntakeClassification
    normalized_problem: Interpretation
    target_segment: Interpretation
    desired_outcome: Interpretation
    solution_hypothesis: Interpretation
    expected_behavior_change: Interpretation
    facts: tuple[ClaimProposal, ...]
    evidence: tuple[ClaimProposal, ...]
    assumptions: tuple[AssumptionProposal, ...]
    inferences: tuple[ClaimProposal, ...]
    unknowns: tuple[ClaimProposal, ...]
    contradictory_signals: tuple[ContradictorySignal, ...]
    strategic_fit: StrategicFit
    riskiest_assumption: RiskiestAssumption | None
    validation_recommendation: ValidationRecommendation | None
    reasoning_summary: Text

    @model_validator(mode="after")
    def validate_references(self) -> "DiscoveryAnalysis":
        claims = self.facts + self.evidence + self.inferences + self.unknowns
        ids = [c.id for c in claims] + [a.id for a in self.assumptions]
        if len(ids) != len(set(ids)):
            raise ValueError("proposal IDs must be unique")
        for group, kind in (
            (self.facts, ClaimKind.FACT),
            (self.evidence, ClaimKind.EVIDENCE),
            (self.inferences, ClaimKind.INFERENCE),
            (self.unknowns, ClaimKind.UNKNOWN),
        ):
            if any(c.kind != kind for c in group):
                raise ValueError("claim category must agree with its group")
        assumption_ids = {a.id for a in self.assumptions}
        if self.assumptions and self.riskiest_assumption is None:
            raise ValueError("assumptions require a riskiest recommendation")
        if self.riskiest_assumption is not None:
            if self.riskiest_assumption.assumption_id not in assumption_ids:
                raise ValueError("riskiest assumption must reference a supplied assumption")
            if self.validation_recommendation is None or (
                self.validation_recommendation.target_assumption_id
                != self.riskiest_assumption.assumption_id
            ):
                raise ValueError("validation must target the riskiest assumption")
        elif self.validation_recommendation is not None:
            raise ValueError("validation requires a target assumption")
        for signal in self.contradictory_signals:
            if not signal.claim_ids or not set(signal.claim_ids) <= set(ids):
                raise ValueError("contradictions must reference supplied claims")
            if len(signal.competing_explanations) < 2:
                raise ValueError("preserve at least two competing explanations")
        return self
