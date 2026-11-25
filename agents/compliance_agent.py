"""Compliance agent: evidence-based findings and deterministic summaries.

A status is NEVER decided by the LLM. Rules:
  COMPLIANT             evidence present (and, for consents/authorisations, a
                        reference number and a validity date not yet expired)
  PARTIALLY_COMPLIANT   evidence present but reference number or validity missing
  NON_COMPLIANT         only when the documents EXPLICITLY state absence/expiry,
                        and the requirement firmly applies
  INSUFFICIENT_EVIDENCE nothing, or 'not provided' (never treated as a violation)
"""
import json

from agents.llm_utils import AI_UNAVAILABLE_MESSAGE, invoke_llm
from regulation_engine.amendment_checker import check_amendment_status
from workflows.state import (APPLICABLE, COMPLIANT, EV_EXPLICIT_NEGATIVE,
                             EV_NONE, EV_NOT_PROVIDED, EV_PRESENT, EV_DISCLAIMER,
                             INSUFFICIENT_EVIDENCE, NON_COMPLIANT,
                             NOT_APPLICABLE, PARTIALLY_COMPLIANT,
                             RISK_ORDER, STATUS_LABELS)

VALIDITY_TOPICS = {"consent_to_establish", "consent_to_operate", "hazardous_waste_authorisation"}
# A Consent to Establish is a one-off order and normally has no expiry in the document.
NO_EXPIRY_TOPICS = {"consent_to_establish"}


def _risk(status, criticality):
    if status == NON_COMPLIANT:
        return "High"
    if status == COMPLIANT:
        return "Low"
    return "Medium" if criticality == "high" else "Low"


def assess_requirement(entry, applicability, merged_topics):
    topic = entry["evidence_topic"]
    ev = merged_topics.get(topic, {"status": EV_NONE, "evidence": [], "details": {}})
    status_ev, details = ev["status"], ev.get("details", {})
    firm = applicability["status"] == APPLICABLE
    missing, notes = [], []

    if status_ev == EV_PRESENT:
        expired = details.get("expired")
        if expired and topic in VALIDITY_TOPICS and topic not in NO_EXPIRY_TOPICS:
            status = NON_COMPLIANT
            explanation = (f"The document shows this record was valid until {details['valid_until']}, "
                           "which is before the assessment date.")
        elif topic in VALIDITY_TOPICS:
            if not details.get("reference_number"):
                missing.append("Order / reference number")
            if topic not in NO_EXPIRY_TOPICS and not details.get("valid_until"):
                missing.append("Validity (expiry) date")
            status = PARTIALLY_COMPLIANT if missing else COMPLIANT
            explanation = ("The document indicates this record exists" +
                           ("; " + ", ".join(missing).lower() + " could not be found in it." if missing
                            else " with a reference number" + (" and a validity date that has not passed." if details.get("valid_until") else ".")))
        elif details.get("missing_fields"):
            missing.extend(details["missing_fields"])
            status = PARTIALLY_COMPLIANT
            explanation = ("The document appears to contain a record for this requirement, but "
                           "the following supporting details could not be found: " +
                           ", ".join(missing) + ".")
        else:
            status = COMPLIANT
            explanation = "The document indicates this requirement has been addressed."
    elif status_ev == EV_EXPLICIT_NEGATIVE:
        status = NON_COMPLIANT
        explanation = "The document explicitly states the record is absent, refused, lapsed or not held."
    elif status_ev == EV_NOT_PROVIDED:
        status = INSUFFICIENT_EVIDENCE
        explanation = ("The document lists this item as not provided/specified. This is a gap in evidence, "
                       "not proof of a violation.")
        missing.append(entry["evidence_description"])
    elif status_ev == EV_DISCLAIMER:
        status = INSUFFICIENT_EVIDENCE
        explanation = ("The document identifies this material as a sample, unverified, or not an official/valid record. "
                       "It is not treated as documentary evidence or proof of a violation.")
        missing.append(entry["evidence_description"])
    else:
        status = INSUFFICIENT_EVIDENCE
        explanation = "No evidence for this requirement was found in the submitted documents."
        missing.append(entry["evidence_description"])

    if status == NON_COMPLIANT and not firm:
        status = INSUFFICIENT_EVIDENCE
        notes.append("The documents point to a gap, but applicability is not firmly established (" +
                     applicability["status"].replace("_", " ").lower() + "), so no non-compliance is asserted.")
        explanation += " " + notes[-1]
    if applicability["status"] != APPLICABLE:
        notes.append(applicability["reason"])
    if ev.get("conflicting"):
        notes.append("Documents contain conflicting statements; the strongest evidence was used. Review manually.")

    amend = check_amendment_status(entry)
    return {
        "requirement_id": entry["id"], "title": entry["title"], "instrument": entry["instrument"],
        "citation": entry["citation"], "status": status, "status_label": STATUS_LABELS[status],
        "risk_level": _risk(status, entry["criticality"]), "criticality": entry["criticality"],
        "applicability": applicability["status"], "explanation": explanation, "notes": notes,
        "evidence": ev.get("evidence", [])[:5], "evidence_details": details,
        "evidence_class": status_ev, "missing_information": missing,
        "what_to_show": entry["evidence_description"],
        "references": entry["sources"], "verification": entry["verification"], "amendment_check": amend,
        "summary": entry["summary"],
    }


def assess_compliance(entries, applicability_list, merged_facts):
    app = {a["requirement_id"]: a for a in applicability_list}
    findings = []
    for e in entries:
        a = app[e["id"]]
        if a["status"] == NOT_APPLICABLE:
            continue
        findings.append(assess_requirement(e, a, merged_facts["topics"]))
    findings.sort(key=lambda f: (-RISK_ORDER[f["risk_level"]], f["requirement_id"]))
    return findings


def summarize_overall(findings, applicability_list):
    counts = {s: 0 for s in STATUS_LABELS}
    for f in findings:
        counts[f["status"]] += 1
    n = len(findings)
    risk = max((f["risk_level"] for f in findings), key=lambda r: RISK_ORDER[r]) if findings else "Undetermined"
    if not findings:
        key, label = "NO_APPLICABLE_REQUIREMENTS", "No applicable requirements assessed"
        text = ("None of the requirements in the knowledge base apply to the declared activities. "
                "This does not mean the business is exempt from other environmental laws.")
    elif counts[NON_COMPLIANT]:
        key, label = "NON_COMPLIANCE_INDICATED", "Non-compliance indicated"
        text = (f"{counts[NON_COMPLIANT]} of {n} assessed requirements are explicitly contradicted by the submitted documents. "
                "Corrective action is recommended.")
    elif counts[INSUFFICIENT_EVIDENCE] or counts[PARTIALLY_COMPLIANT]:
        key, label = "EVIDENCE_INCOMPLETE", "Evidence incomplete - review required"
        text = (f"{counts[COMPLIANT]} of {n} requirements are supported by evidence; "
                f"{counts[INSUFFICIENT_EVIDENCE] + counts[PARTIALLY_COMPLIANT]} need more evidence. "
                "Missing evidence is not treated as a violation.")
    else:
        key, label = "NO_GAPS_IN_SUBMITTED_EVIDENCE", "No gaps found in submitted evidence"
        text = (f"All {n} assessed requirements are supported by the submitted documents. "
                "This is not a legal compliance certificate and covers only the listed requirements.")
    return {"status": key, "label": label, "summary": text, "counts": counts,
            "total_assessed": n, "risk_level": risk,
            "not_applicable": sum(1 for a in applicability_list if a["status"] == NOT_APPLICABLE)}


def generate_ai_explanations(profile, findings, overall, entries, applicability_list):
    """Generate an optional narrative and per-instrument explanations in one request."""
    applicability = {
        item["requirement_id"]: item
        for item in applicability_list
        if item["status"] != NOT_APPLICABLE
    }
    findings_by_id = {item["requirement_id"]: item for item in findings}
    requirements_by_instrument = {}
    for entry in entries:
        if entry["id"] in applicability:
            requirements_by_instrument.setdefault(entry["instrument"], []).append({
                "requirement_id": entry["id"],
                "citation": entry["citation"],
                "title": entry["title"],
                "curated_summary": entry["summary"],
                "applicability": applicability[entry["id"]]["status"],
                "applicability_reason": applicability[entry["id"]]["reason"],
                "rule_engine_finding": {
                    key: findings_by_id.get(entry["id"], {}).get(key)
                    for key in ("status_label", "risk_level", "evidence_class", "explanation", "missing_information")
                },
            })

    instruments = list(requirements_by_instrument)
    instrument_schema = {"type": "string"}
    if instruments:
        instrument_schema["enum"] = instruments
    response_schema = {
        "type": "object",
        "properties": {
            "narrative": {"type": "string"},
            "interpretations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "instrument": instrument_schema,
                        "text": {"type": "string"},
                    },
                    "required": ["instrument", "text"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["narrative", "interpretations"],
        "additionalProperties": False,
    }
    source = {
        "business": {
            key: profile.get(key)
            for key in ("company", "industry", "state", "wastewater", "air_emissions", "hazardous_waste")
        },
        "overall_rule_engine_result": overall["label"],
        "deterministic_findings": [
            {
                "requirement_id": item["requirement_id"],
                "title": item["title"],
                "instrument": item["instrument"],
                "status": item["status_label"],
                "risk_level": item["risk_level"],
                "evidence_class": item["evidence_class"],
                "finding": item["explanation"],
                "missing_information": item["missing_information"],
            }
            for item in findings
        ],
        "curated_regulatory_material": requirements_by_instrument,
    }
    prompt = f"""Explain the following deterministic environmental screening assessment in concise plain language.
Return a short narrative and one explanation for each supplied regulatory instrument.
Use only the supplied business, curated regulatory material, and deterministic findings.
Do not introduce laws, requirements, dates, penalties, evidence, or facts that are not supplied.
Do not change, restate as different, or imply changes to any compliance status, evidence classification, or risk level.
Missing evidence is not proof of a violation. This is not legal advice or an official compliance determination.
Return only the JSON object matching the required schema.

ASSESSMENT CONTEXT:
{json.dumps(source, ensure_ascii=False)}
"""
    response = invoke_llm(
        prompt,
        temperature=0.1,
        response_schema=response_schema,
        cache_result=True,
    )
    if not response["ok"]:
        return response

    try:
        parsed = json.loads(response["text"])
        narrative = parsed["narrative"]
        raw_interpretations = parsed["interpretations"]
        if not isinstance(narrative, str) or not narrative.strip() or not isinstance(raw_interpretations, list):
            raise ValueError("Invalid structured OpenRouter response")
        interpretations_by_instrument = {}
        for item in raw_interpretations:
            instrument = item["instrument"]
            text = item["text"]
            if (
                instrument not in instruments
                or instrument in interpretations_by_instrument
                or not isinstance(text, str)
                or not text.strip()
            ):
                raise ValueError("Invalid structured OpenRouter response")
            interpretations_by_instrument[instrument] = text
        if set(interpretations_by_instrument) != set(instruments):
            raise ValueError("Incomplete structured OpenRouter response")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {"ok": False, "error": AI_UNAVAILABLE_MESSAGE}

    return {
        "ok": True,
        "narrative": narrative,
        "interpretations": [
            {
                "instrument": instrument,
                "status": "Analysis completed",
                "text": interpretations_by_instrument[instrument],
            }
            for instrument in instruments
        ],
        "error": None,
    }
