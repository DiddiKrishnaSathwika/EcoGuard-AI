"""Integrity review for evidence-based assessment findings."""
import re

from regulation_engine.knowledge_base import get_entry, kb_reference_labels
from workflows.state import COMPLIANT, EV_EXPLICIT_NEGATIVE, EV_PRESENT, NON_COMPLIANT

FORBIDDEN = [r"\bguarantee[sd]?\b", r"\blegally compliant\b", r"\bfully compliant\b", r"no (risk|penalt)", r"\bwill be penali[sz]ed\b"]
CITE = re.compile(r"\b(Section|Rule|Regulation|Schedule)\s+(\d+[A-Za-z]?)", re.I)


def _ai_text_problems(text, allowed):
    problems = []
    for match in CITE.finditer(text or ""):
        label = f"{match.group(1)} {match.group(2)}".lower()
        if label not in allowed:
            problems.append(f"AI text cites '{match.group(0)}', which is not in the verified knowledge base.")
    for pattern in FORBIDDEN:
        if re.search(pattern, text or "", re.I):
            problems.append(f"AI text contains disallowed assurance wording ({pattern}).")
    return problems


def review_assessment(result):
    issues, notes = [], []
    for f in result.get("findings", []):
        if not get_entry(f["requirement_id"]):
            issues.append(f"{f['requirement_id']}: unknown requirement (not in knowledge base).")
        if f["status"] == COMPLIANT and f.get("evidence_class") != EV_PRESENT:
            issues.append(f"{f['requirement_id']}: marked compliant without supporting evidence.")
        if f["status"] == NON_COMPLIANT and not (
                f.get("evidence_class") == EV_EXPLICIT_NEGATIVE or f.get("evidence_details", {}).get("expired")):
            issues.append(f"{f['requirement_id']}: non-compliance asserted without explicit evidence.")
    allowed = kb_reference_labels()
    ai = result.get("ai") or {}
    suppressed = False
    texts = [("narrative", ai.get("narrative") or "")] + [
        (item["instrument"], item["text"]) for item in ai.get("interpretations", [])
    ]
    for name, text in texts:
        problems = _ai_text_problems(text, allowed)
        if problems:
            suppressed = True
            notes.extend(f"[{name}] {problem}" for problem in problems)
    if suppressed:
        ai["narrative"], ai["interpretations"] = None, []
        ai["suppressed_reason"] = (
            "AI text was withheld because it contained citations or wording not supported "
            "by the verified knowledge base."
        )
    return {"passed": not issues, "issues": issues, "notes": notes,
            "ai_suppressed": suppressed,
            "checks": ["compliant requires evidence", "non-compliant requires explicit evidence",
                       "requirement exists in knowledge base", "AI text limited to verified references",
                       "no assurance wording in AI text"]}
