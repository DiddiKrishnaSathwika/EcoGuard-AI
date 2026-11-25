"""Shared constants and the workflow state definition."""
from typing import Any, Dict, List, Optional, TypedDict

# Finding statuses
COMPLIANT = "COMPLIANT"
PARTIALLY_COMPLIANT = "PARTIALLY_COMPLIANT"
NON_COMPLIANT = "NON_COMPLIANT"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

STATUS_LABELS = {
    COMPLIANT: "Compliant",
    PARTIALLY_COMPLIANT: "Partially compliant",
    NON_COMPLIANT: "Non-compliant",
    INSUFFICIENT_EVIDENCE: "Insufficient evidence",
}

# Applicability statuses
APPLICABLE = "APPLICABLE"
CONDITIONALLY_APPLICABLE = "CONDITIONALLY_APPLICABLE"
NEEDS_INFORMATION = "NEEDS_INFORMATION"
NOT_APPLICABLE = "NOT_APPLICABLE"

# Evidence classes for one topic found in documents
EV_PRESENT = "present"
EV_NOT_PROVIDED = "not_provided"
EV_EXPLICIT_NEGATIVE = "explicit_negative"
EV_MENTIONED = "mentioned"
EV_DISCLAIMER = "disclaimer"
EV_NONE = "none"

RISK_ORDER = {"High": 3, "Medium": 2, "Low": 1, "Undetermined": 0}

STANDARD_LIMITATIONS = [
    "This is a screening aid, not legal advice or an official compliance determination.",
    "Missing documents are reported as insufficient evidence, never as proof of a violation.",
    "Regulatory summaries come from a limited curated knowledge base; see regulatory coverage.",
    "Amendment status of the cited provisions has not been independently verified.",
    "Confirm every requirement with the official text and your State Pollution Control Board.",
]


class AssessmentState(TypedDict, total=False):
    profile: Dict[str, Any]
    documents: List[Dict[str, Any]]
    assessment_date: str
    use_ai: bool
    document_facts: Dict[str, Any]
    retrieved: List[Dict[str, Any]]
    applicability: List[Dict[str, Any]]
    findings: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    overall: Dict[str, Any]
    ai: Dict[str, Any]
    ethics_review: Dict[str, Any]
    result: Optional[Dict[str, Any]]
    trace: List[str]
