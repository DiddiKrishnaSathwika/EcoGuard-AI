"""Deterministic evidence extraction from document text.

Everything here is rule based and traceable to a page/line of the document.
It is the evidence base for compliance findings (the LLM is never the sole
source of a status)."""
import re
from datetime import date, datetime

from workflows.state import (EV_EXPLICIT_NEGATIVE, EV_MENTIONED, EV_NONE,
                             EV_NOT_PROVIDED, EV_PRESENT, EV_DISCLAIMER)

TOPICS = {
    "consent_to_establish": [r"consent\s+to\s+establish", r"\bCTE\b"],
    "consent_to_operate": [r"consent\s+to\s+operate", r"\bCTO\b", r"consent\s+(order|certificate)"],
    "hazardous_waste_authorisation": [r"hazardous\s+(and\s+other\s+)?waste\s+authori[sz]ation", r"\bauthori[sz]ation\s+(under|no|number)", r"\bform[\s-]*2\b"],
    "hazardous_waste_records": [r"\bform[\s-]*3\b", r"hazardous\s+waste\s+(record|log|register)s?"],
    "annual_return_form4": [r"\bform[\s-]*4\b", r"annual\s+return"],
    "manifest_form10": [r"\bform[\s-]*10\b", r"\bmanifest"],
    "wastewater_treatment": [r"\b(ETP|STP)\b", r"effluent\s+treatment", r"wastewater\s+treatment", r"sewage\s+treatment"],
    "wastewater_disposal": [r"wastewater\s+disposal", r"effluent\s+disposal|discharge\s+(point|method)"],
    "air_pollution_control": [r"air\s+pollution\s+control", r"\b(scrubber|bag\s*filter|cyclone|stack)\b"],
    "waste_disposal_records": [r"waste\s+disposal\s+(record|receipt)s?", r"disposal\s+receipts?"],
    "water_testing": [r"water\s+test", r"effluent\s+(test|analysis)"],
    "air_monitoring": [r"air\s+emission\s+monitoring", r"stack\s+monitoring"],
}
TOPIC_LABELS = {
    "consent_to_establish": "Consent to Establish", "consent_to_operate": "Consent to Operate",
    "hazardous_waste_authorisation": "Hazardous waste authorisation", "hazardous_waste_records": "Hazardous waste records (Form 3)",
    "annual_return_form4": "Annual return (Form 4)", "manifest_form10": "Manifest (Form 10)",
    "wastewater_treatment": "Wastewater treatment", "wastewater_disposal": "Wastewater disposal",
    "air_pollution_control": "Air pollution control equipment", "waste_disposal_records": "Waste disposal records",
    "water_testing": "Water testing reports", "air_monitoring": "Air emission monitoring",
}

NOT_PROVIDED = re.compile(r"\b(not\s+(provided|specified|available|submitted|reported|mentioned|attached|furnished|stated)|n/?a|nil|none|unavailable|missing|to\s+be\s+provided)\b", re.I)
EXPLICIT_NEG = re.compile(r"\b(not\s+(obtained|held|valid)|does\s+not\s+(have|hold)|do\s+not\s+(have|hold|possess)|has\s+not\s+(obtained|applied)|have\s+not\s+(obtained|applied)|no\s+valid|without\s+(a\s+)?(valid\s+)?(consent|authori[sz]ation)|refused|rejected|revoked|suspended|cancell?ed|lapsed|expired)\b", re.I)
POSITIVE = re.compile(r"\b(granted|issued|valid|obtained|renewed|held|in\s+force|certificate|order\s+no|ref(erence)?\s*(no|number)|authori[sz]ation\s+(no|number)|consent\s+no|filed|submitted\s+on|acknowledg)", re.I)
DISCLAIMER = re.compile(
    r"\b(?:not\s+(?:an?\s+)?official\s+(?:form|document|record)|demo(?:nstration)?\s+only|"
    r"not\s+a\s+valid\s+(?:permit|authori[sz]ation|manifest|form|record|document)|"
    r"not\s+verified|unverified|fictional|sample\s+(?:only|data|document)|"
    r"for\s+(?:illustration|testing|demonstration)\s+only)\b", re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_PAT = (r"(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\.?,?\s+\d{4}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})")
VALID_PAT = re.compile(r"(valid\s*(?:up\s*)?(?:to|till|until|upto)|expir(?:y|es|ing)(?:\s+on|\s+date)?|validity(?:\s+(?:up\s*to|till|until))?)\s*[:\-]?\s*" + DATE_PAT, re.I)
NUMBER_PAT = re.compile(r"(?:no\.?|number|ref(?:erence)?\.?|order|certificate|id)\s*[:#\-]?\s*([A-Z0-9][A-Za-z0-9/\-._]{3,})", re.I)
PAGE_PAT = re.compile(r"^---\s*Page\s+(\d+)\s*---$")


def parse_date(text):
    text = text.strip().rstrip(".")
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    try:
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
        m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$", text)
        if m:
            return date(int(m[3]), int(m[2]), int(m[1]))  # Indian day-first convention
        m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})$", text)
        if m and m[2][:3].lower() in MONTHS:
            return date(int(m[3]), MONTHS[m[2][:3].lower()], int(m[1]))
        m = re.match(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})$", text)
        if m and m[1][:3].lower() in MONTHS:
            return date(int(m[3]), MONTHS[m[1][:3].lower()], int(m[2]))
    except ValueError:
        return None
    return None


def _lines(text):
    page, out = 1, []
    for raw in (text or "").splitlines():
        s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", raw)
        s = re.sub(r"^[^\w(\[]+", "", s.strip()).strip()
        if not s:
            continue
        pm = PAGE_PAT.match(s)
        if pm:
            page = int(pm.group(1))
            continue
        out.append((page, s))
    return out


def _classify(line, nxt=""):
    """Classify one evidence line. `nxt` is the following line (table layouts)."""
    probe = line
    # "Label" alone on a line with value on the next line
    label_only = len(line) < 50 and (":" not in line or line.endswith(":"))
    if label_only and nxt:
        probe = line + " " + nxt
    if EXPLICIT_NEG.search(probe):
        return EV_EXPLICIT_NEGATIVE
    if NOT_PROVIDED.search(probe):
        return EV_NOT_PROVIDED
    if POSITIVE.search(probe) or VALID_PAT.search(probe) or NUMBER_PAT.search(probe):
        return EV_PRESENT
    return EV_MENTIONED


DOCUMENT_TOPICS = {
    "hazardous_waste_authorisation", "hazardous_waste_records",
    "annual_return_form4", "manifest_form10",
}


def _field_value(context, labels):
    match = re.search(
        r"\b(?:%s)\b\s*[:#\-]\s*([^\n|;]+)" % labels, context, re.I)
    if not match:
        return None
    value = match.group(1).strip(" .,-")
    return value if value and not NOT_PROVIDED.fullmatch(value) else None


def _document_evidence(topic, line, context, assessment_date):
    """Require document-specific cues and extracted record details for form evidence."""
    probe = context
    if DISCLAIMER.search(probe):
        return EV_DISCLAIMER, {}
    if EXPLICIT_NEG.search(line):
        return EV_EXPLICIT_NEGATIVE, {}
    if NOT_PROVIDED.search(line):
        return EV_NOT_PROVIDED, {}

    date_match = re.search(DATE_PAT, probe, re.I)
    quantity_match = re.search(
        r"\b(?:quantity|qty|amount|generated|managed|dispatched)?\s*[:#\-]?\s*"
        r"([\d,]+(?:\.\d+)?\s*(?:kg|kgs|kilograms?|tonnes?|tons?|mt|litres?|liters?|kl|kld|m3|l))\b",
        probe, re.I)
    date_value = date_match.group(0) if date_match else None
    quantity_value = quantity_match.group(1).strip() if quantity_match else None
    waste_type = _field_value(probe, r"waste\s*(?:type|description)|description\s+of\s+waste")
    details = {}

    if topic == "hazardous_waste_authorisation":
        number_match = NUMBER_PAT.search(probe)
        reference = number_match.group(1) if number_match and re.search(r"\d", number_match.group(1)) else None
        validity_match = VALID_PAT.search(probe)
        valid_until = parse_date(validity_match.group(2)) if validity_match else None
        issue_cue = re.search(r"\b(granted|issued|approved|authori[sz]ed)\b", probe, re.I)
        if not (reference or valid_until) or not (issue_cue or reference and valid_until):
            return EV_MENTIONED, {}
        if reference:
            details["reference_number"] = reference
        if valid_until:
            details["valid_until"] = valid_until.isoformat()
            details["expired"] = valid_until < assessment_date
        details["missing_fields"] = [
            label for key, label in (("reference_number", "authorization number"),
                                     ("valid_until", "validity date"))
            if key not in details
        ]
        return EV_PRESENT, details

    if topic == "hazardous_waste_records":
        record_cue = re.search(r"\b(register|record|log|entries)\b", probe, re.I)
        form_reference = re.search(r"\bform[\s-]*3\b", probe, re.I)
        record_details = {
            "date": date_value,
            "quantity": quantity_value,
            "waste_type": waste_type,
        }
        populated_fields = sum(bool(value) for value in record_details.values())
        if not (record_cue and populated_fields or form_reference and populated_fields >= 2):
            return EV_MENTIONED, {}
        details.update({k: v for k, v in record_details.items() if v})
        details["missing_fields"] = [k.replace("_", " ") for k, v in record_details.items() if not v]
        return EV_PRESENT, details

    if topic == "annual_return_form4":
        submitted = bool(re.search(r"\b(filed|submitted|acknowledged|acknowledgement|acknowledgment)\b", probe, re.I))
        period = _field_value(probe, r"reporting\s+period|financial\s+year|period")
        if not period:
            fy_match = re.search(r"\bFY\s*\d{4}(?:\s*[-/]\s*\d{2,4})?\b", probe, re.I)
            period = fy_match.group(0) if fy_match else None
        acknowledgement = _field_value(probe, r"ack(?:nowledg(?:e)?ment)?(?:\s+(?:no|number|id|receipt))?")
        submitted_on = date_value if submitted else None
        if not submitted or not (period or acknowledgement or submitted_on):
            return EV_MENTIONED, {}
        details = {"reporting_period": period, "acknowledgement": acknowledgement,
                   "submitted_on": submitted_on, "submission_confirmed": submitted}
        details["missing_fields"] = [
            label for key, label in (("reporting_period", "reporting period"),
                                     ("acknowledgement", "filing acknowledgement"))
            if not details[key]
        ]
        return EV_PRESENT, details

    manifest_number = _field_value(probe, r"manifest\s*(?:no|number|#)|manifest\s+reference")
    sender = _field_value(probe, r"sender|generator|consignor")
    receiver = _field_value(probe, r"receiver|recipient|consignee|destination")
    record_details = {
        "manifest_number": manifest_number,
        "date": date_value,
        "sender": sender,
        "receiver": receiver,
        "waste_type": waste_type,
        "quantity": quantity_value,
    }
    manifest_cue = re.search(r"\b(manifest|form[\s-]*10)\b", probe, re.I)
    has_record_identity = bool(manifest_number or sender and receiver)
    has_record_data = any(record_details[k] for k in ("date", "waste_type", "quantity"))
    if not manifest_cue or not has_record_identity or not has_record_data:
        return EV_MENTIONED, {}
    details.update({k: v for k, v in record_details.items() if v})
    details["missing_fields"] = [k.replace("_", " ") for k, v in record_details.items() if not v]
    return EV_PRESENT, details


def extract_topics(text, assessment_date=None):
    assessment_date = assessment_date or date.today()
    lines = _lines(text)
    topics = {}
    for topic, patterns in TOPICS.items():
        regs = [re.compile(p, re.I) for p in patterns]
        other_document_regs = [
            re.compile(pattern, re.I)
            for other_topic, other_patterns in TOPICS.items()
            if other_topic in DOCUMENT_TOPICS and other_topic != topic
            for pattern in other_patterns
        ]
        hits = []
        for i, (page, line) in enumerate(lines):
            if any(r.search(line) for r in regs):
                nxt = lines[i + 1][1] if i + 1 < len(lines) else ""
                if topic in DOCUMENT_TOPICS:
                    start = i
                    while (start > 0 and i - start < 6 and lines[start - 1][0] == page
                           and not any(r.search(lines[start - 1][1]) for r in other_document_regs)):
                        start -= 1
                    end = i + 1
                    while (end < len(lines) and end - i < 7 and lines[end][0] == page
                           and not any(r.search(lines[end][1]) for r in other_document_regs)):
                        end += 1
                    context = "\n".join(item[1] for item in lines[start:end])
                    hit_class, hit_details = _document_evidence(
                        topic, line, context, assessment_date)
                else:
                    context = line + " " + nxt
                    hit_class, hit_details = _classify(line, nxt), {}
                hits.append({"page": page, "line": line, "class": hit_class,
                             "_ctx": context, "_details": hit_details})
        if not hits:
            topics[topic] = {"status": EV_NONE, "evidence": [], "details": {}}
            continue
        classes = [h["class"] for h in hits]
        for status in (EV_PRESENT, EV_EXPLICIT_NEGATIVE, EV_NOT_PROVIDED,
                       EV_DISCLAIMER, EV_MENTIONED):
            if status in classes:
                break
        details = {}
        if status == EV_PRESENT:
            if topic in DOCUMENT_TOPICS:
                details = next((h["_details"] for h in hits
                                if h["class"] == EV_PRESENT and h["_details"]), {})
            for h in hits:
                if h["class"] != EV_PRESENT:
                    continue
                if topic in DOCUMENT_TOPICS:
                    continue
                vm = VALID_PAT.search(h["_ctx"])
                if vm and "valid_until" not in details:
                    d = parse_date(vm.group(2))
                    if d:
                        details["valid_until"] = d.isoformat()
                nm = NUMBER_PAT.search(h["line"])
                if nm and "reference_number" not in details and re.search(r"\d", nm.group(1)):
                    details["reference_number"] = nm.group(1)
            if details.get("valid_until"):
                details["expired"] = date.fromisoformat(details["valid_until"]) < assessment_date
        topics[topic] = {
            "status": status,
            "evidence": [{"page": h["page"], "line": h["line"], "class": h["class"]} for h in hits[:6]],
            "details": details,
            "conflicting": len(set(classes) - {EV_MENTIONED}) > 1,
        }
    return topics


def _labelled(lines, label_re):
    rx = re.compile(r"^(?:%s)\s*[:\-]?\s*(?P<v>.*)$" % label_re, re.I)
    for i, (_, line) in enumerate(lines):
        m = rx.match(line)
        if m:
            value = m.group('v').strip()
            if value:
                return value
            if i + 1 < len(lines):
                return lines[i + 1][1]
    return None


def extract_facts(text, assessment_date=None):
    """Return structured, evidence-linked facts from document text."""
    lines = _lines(text)
    facts = {
        "business_name": _labelled(lines, r"business\s+name|company\s+name|name\s+of\s+(the\s+)?(unit|company|industry)"),
        "location": _labelled(lines, r"location|address"),
        "industry": _labelled(lines, r"industry|nature\s+of\s+business"),
        "reporting_period": _labelled(lines, r"reporting\s+period|period"),
        "topics": extract_topics(text, assessment_date),
        "quantities": {}, "air_sources": [], "wastewater_reported": None, "hazardous_waste_reported": None,
    }
    for page, line in lines:
        low = line.lower()
        if "wastewater generated" in low or "effluent generated" in low:
            m = re.search(r"([\d,\.]+)\s*(litres?|liters?|kl|kld|m3|l)\b", low)
            facts["quantities"]["wastewater_generated"] = line
            if m:
                try:
                    facts["wastewater_reported"] = float(m.group(1).replace(",", "")) > 0
                except ValueError:
                    pass
        if "water consumption" in low:
            facts["quantities"]["water_consumption"] = line
        if re.search(r"diesel\s+generator|\bdg\s*set|boiler|furnace|incinerator", low) and not NOT_PROVIDED.search(low):
            facts["air_sources"].append({"page": page, "line": line})
        if "hazardous waste" in low and "authori" not in low and "record" not in low:
            if re.search(r"not\s+reported|\bnone\b|\bnil\b|no\s+hazardous", low):
                facts["hazardous_waste_reported"] = "none_or_not_reported"
            elif re.search(r"[\d,\.]+\s*(kg|tonnes?|tons?|mt|litres?)", low):
                facts["hazardous_waste_reported"] = "reported"
        for key, rx in (("organic_waste", r"organic\s+waste"), ("plastic_waste", r"plastic\s+(packaging\s+)?waste")):
            if re.search(rx, low) and key not in facts["quantities"]:
                facts["quantities"][key] = line
    facts["air_sources"] = facts["air_sources"][:5]
    return facts


def merge_document_facts(per_doc_facts):
    """Merge facts of several documents; best evidence wins per topic."""
    rank = {EV_PRESENT: 5, EV_EXPLICIT_NEGATIVE: 4, EV_NOT_PROVIDED: 3,
            EV_DISCLAIMER: 2, EV_MENTIONED: 1, EV_NONE: 0}
    merged = {"topics": {t: {"status": EV_NONE, "evidence": [], "details": {}, "sources": []} for t in TOPICS},
              "wastewater_reported": None, "hazardous_waste_reported": None, "air_sources": [], "quantities": {}}
    for doc_name, f in per_doc_facts:
        for t, info in f["topics"].items():
            cur = merged["topics"][t]
            if info["status"] == EV_NONE:
                continue
            cur["sources"].append(doc_name)
            for ev in info["evidence"]:
                cur["evidence"].append({**ev, "document": doc_name})
            better = rank[info["status"]] > rank[cur["status"]]
            if info["status"] == EV_PRESENT and cur["status"] == EV_PRESENT:
                current_expired = cur["details"].get("expired", False)
                incoming_expired = info["details"].get("expired", False)
                if current_expired != incoming_expired:
                    better = current_expired and not incoming_expired
                else:
                    better = len(info["details"].get("missing_fields", [])) < len(
                        cur["details"].get("missing_fields", []))
            if better:
                cur["status"], cur["details"] = info["status"], info["details"]
            classes = {e["class"] for e in cur["evidence"]} - {EV_MENTIONED}
            cur["conflicting"] = len(classes) > 1
        for key in ("wastewater_reported", "hazardous_waste_reported"):
            if f.get(key) and not merged[key]:
                merged[key] = f[key]
        merged["air_sources"] += [{**s, "document": doc_name} for s in f.get("air_sources", [])]
        for k, v in f.get("quantities", {}).items():
            merged["quantities"].setdefault(k, v)
    return merged
