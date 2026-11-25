"""Checks applied to one assessment result."""
from regulation_engine.knowledge_base import get_entry
from workflows.state import COMPLIANT, EV_EXPLICIT_NEGATIVE, NON_COMPLIANT


def status_checks(case, result):
    """Expected requirement statuses (APPLICABILITY:NOT_APPLICABLE or finding status)."""
    out = []
    findings = {f["requirement_id"]: f for f in result["findings"]}
    app = {a["requirement_id"]: a for a in result["applicability"]}
    for rid, expected in case["expected"].items():
        if expected == "NOT_APPLICABLE":
            actual = app[rid]["status"]
        elif expected == "NEEDS_INFORMATION":
            actual = app[rid]["status"]
        else:
            actual = findings[rid]["status"] if rid in findings else app[rid]["status"]
        out.append({"check": f"status:{rid}", "expected": expected, "actual": actual, "passed": expected == actual})
    return out


def integrity_checks(result):
    findings = result["findings"]
    return [
        {"check": "compliant_requires_evidence", "passed": all(f["evidence"] for f in findings if f["status"] == COMPLIANT),
         "expected": "every compliant finding has evidence", "actual": ""},
        {"check": "non_compliant_requires_explicit_evidence",
         "passed": all(f["evidence_class"] == EV_EXPLICIT_NEGATIVE or f["evidence_details"].get("expired")
                       for f in findings if f["status"] == NON_COMPLIANT),
         "expected": "non-compliance only from explicit statements", "actual": ""},
        {"check": "citations_exist_in_knowledge_base", "passed": all(get_entry(f["requirement_id"]) for f in findings),
         "expected": "all cited requirements exist", "actual": ""},
        {"check": "ethics_review_passed", "passed": result["ethics_review"]["passed"], "expected": "passed", "actual": ""},
    ]
