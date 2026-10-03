"""Constrained methods shared by review proposals and validation activities."""

from enum import StrEnum


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
