
import logging

from agents.fact_extractor import extract_facts, TOPIC_LABELS
from agents.llm_utils import AI_UNAVAILABLE_MESSAGE, invoke_llm

logger = logging.getLogger(__name__)

def analyze_document(document_text, filename="Uploaded Document"):

    if not document_text or not document_text.strip():
        raise ValueError("The uploaded document contains no readable text.")

    prompt = f"""
You are the Document Analysis Agent of EcoGuard AI.

Your task is to examine environmental documents submitted
by Small and Medium Enterprises in India.

DOCUMENT NAME:
{filename}

DOCUMENT CONTENT:
{document_text}

Analyze the document and provide the following sections:

1. DOCUMENT IDENTIFICATION
Identify the document type and its apparent purpose.
Do not assume it is an official permit or certificate.

2. BUSINESS INFORMATION
Extract the business name, location, industry and other
available details.

3. ENVIRONMENTAL INFORMATION
Identify information relating to:
- Water consumption and wastewater
- Air emissions
- Solid waste
- Hazardous waste
- Pollution control measures

4. IMPORTANT DOCUMENT DETAILS
Identify dates, permit numbers, issuing authorities
and validity periods if explicitly mentioned.

5. MISSING INFORMATION
List relevant information that is not available
in the submitted document.

6. PRELIMINARY OBSERVATIONS
Summarize potential areas requiring further review.

IMPORTANT ETHICAL RULES:
- Never invent facts or document details.
- Never assume missing documents prove a violation.
- Do not declare a business compliant or non-compliant
  based only on this document.
- Clearly distinguish extracted facts from assumptions.
- Mention uncertainty wherever evidence is insufficient.
- Do not invent environmental regulations.

Use clear headings and concise explanations.
"""

    response = invoke_llm(prompt, temperature=0.1, cache_result=True)
    if not response["ok"]:
        raise RuntimeError(AI_UNAVAILABLE_MESSAGE)
    return response["text"]


def analyze_document_full(document_text, filename="Uploaded Document", use_ai=True, assessment_date=None):
    """Deterministic fact extraction (always) + optional OpenRouter analysis.

    The AI analysis is clearly separated from extracted facts."""
    facts = extract_facts(document_text, assessment_date)
    found = {k: v["status"] for k, v in facts["topics"].items() if v["status"] != "none"}
    result = {
        "facts": facts,
        "topics_found": {TOPIC_LABELS[k]: v for k, v in found.items()},
        "ai_analysis": None,
        "ai_status": "not_requested",
        "ai_error": None,
    }
    if use_ai:
        out = _ai_document_analysis(document_text, filename)
        result["ai_analysis"] = out["text"] if out["ok"] else None
        result["ai_status"] = "completed" if out["ok"] else "unavailable"
        result["ai_error"] = out["error"]
    return result


def _ai_document_analysis(document_text, filename):
    # Reuse the original prompt through analyze_document, but never raise.
    from agents.llm_utils import llm_status
    status = llm_status()
    if not status["available"]:
        return invoke_llm("")  # returns the descriptive error
    try:
        return {"ok": True, "text": analyze_document(document_text[:60000], filename), "error": None}
    except Exception as error:
        if str(error) != AI_UNAVAILABLE_MESSAGE:
            logger.warning("OpenRouter document analysis failed (type=%s)", type(error).__name__)
        return {"ok": False, "text": "", "error": AI_UNAVAILABLE_MESSAGE}
