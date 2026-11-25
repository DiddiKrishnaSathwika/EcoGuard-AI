"""Recommendation agent: prioritised actions derived from findings (rule based)."""
from regulation_engine.knowledge_base import get_entry
from workflows.state import (COMPLIANT, INSUFFICIENT_EVIDENCE, NEEDS_INFORMATION,
                             NON_COMPLIANT, PARTIALLY_COMPLIANT, RISK_ORDER)

PRIORITY = {1: ("P1 - Immediate", "Immediately"), 2: ("P2 - High", "Within about 30 days (suggested)"),
            3: ("P3 - Medium", "Within about 90 days (suggested)")}


def _priority(finding):
    if finding["status"] == NON_COMPLIANT:
        return 1
    if finding["status"] in (INSUFFICIENT_EVIDENCE, PARTIALLY_COMPLIANT) and finding["criticality"] == "high":
        return 2
    return 3


def generate_recommendations(findings, applicability_list):
    recs = []
    for f in findings:
        if f["status"] == COMPLIANT:
            continue
        entry = get_entry(f["requirement_id"])
        p = _priority(f)
        if f["status"] == NON_COMPLIANT:
            why = (f"{f['explanation']} Operating without a valid {f['title'].lower()} may expose the business to "
                   "regulatory action; confirm consequences with the State Board.")
            title = f"Resolve: {f['title']}"
        elif f["status"] == PARTIALLY_COMPLIANT:
            why = f"{f['explanation']} Complete records make the evidence reliable at inspection."
            title = f"Complete records: {f['title']}"
        else:
            why = (f"{f['explanation']} Providing the evidence lets the assessment confirm or rule out a gap "
                   f"under {f['instrument']}, {f['citation']}.")
            title = f"Provide evidence: {f['title']}"
        actions = [entry["corrective_action"]]
        if f["missing_information"]:
            actions.append("Provide: " + "; ".join(f["missing_information"]) + ".")
        recs.append({"id": f"REC-{f['requirement_id']}", "priority": p, "priority_label": PRIORITY[p][0],
                     "suggested_timeframe": PRIORITY[p][1], "title": title, "why": why, "actions": actions,
                     "related_requirement": f["requirement_id"], "risk_level": f["risk_level"],
                     "references": [f"{f['instrument']}, {f['citation']}"]})
    seen = set()
    for a in applicability_list:
        if a["discrepancy"]:
            recs.append({"id": f"REC-DISC-{a['requirement_id']}", "priority": 2, "priority_label": PRIORITY[2][0],
                         "suggested_timeframe": PRIORITY[2][1], "title": "Reconcile business profile with documents",
                         "why": a["discrepancy"], "actions": ["Update the business profile or correct the document."],
                         "related_requirement": a["requirement_id"], "risk_level": "Medium", "references": []})
        if a["status"] == NEEDS_INFORMATION:
            key = a["reason"]
            if key not in seen:
                seen.add(key)
                recs.append({"id": f"REC-INFO-{a['requirement_id']}", "priority": 3, "priority_label": PRIORITY[3][0],
                             "suggested_timeframe": PRIORITY[3][1], "title": "Clarify an 'Unknown' declaration",
                             "why": a["reason"], "actions": ["Determine the answer and update the business profile, then re-run the assessment."],
                             "related_requirement": a["requirement_id"], "risk_level": "Low", "references": []})
    if findings:
        recs.append({"id": "REC-STATE", "priority": 3, "priority_label": PRIORITY[3][0],
                     "suggested_timeframe": PRIORITY[3][1], "title": "Confirm state-specific requirements",
                     "why": "State rules, consent categories and industry-specific standards are not part of this tool's knowledge base.",
                     "actions": ["Ask your State Pollution Control Board which additional requirements apply to your unit."],
                     "related_requirement": None, "risk_level": "Low", "references": []})
    recs.sort(key=lambda r: (r["priority"], -RISK_ORDER[r["risk_level"]], r["id"]))
    return recs
