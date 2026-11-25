
from urllib.parse import urlparse


OFFICIAL_DOMAINS = {
    "cpcb.nic.in",
    "cpcb.gov.in",
    "moef.gov.in",
    "indiacode.nic.in",
    "parivesh.nic.in"
}


def validate_regulation_source(
    source_url,
    content,
    source_title=None
):

    parsed_url = urlparse(source_url)
    domain = (parsed_url.hostname or "").lower()
    path = parsed_url.path.lower()

    official_domain = (
        domain in OFFICIAL_DOMAINS
        or any(
            domain.endswith("." + official)
            for official in OFFICIAL_DOMAINS
        )
    )

    has_content = bool(content and content.strip())

    # Only treat a directly linked PDF as a document candidate.
    is_pdf_document = path.endswith(".pdf")

    legal_keywords = [
        "environment protection act",
        "water act",
        "air act",
        "hazardous waste",
        "environmental standards",
        "consent to operate",
        "consent to establish"
    ]

    combined_text = (
        (source_title or "") + " " + (content or "")
    ).lower()

    has_legal_indicators = any(
        keyword in combined_text
        for keyword in legal_keywords
    )

    potential_regulation = (
        is_pdf_document and has_legal_indicators
    )

    if not official_domain:
        status = "UNVERIFIED_DOMAIN"

    elif not has_content:
        status = "NO_CONTENT"

    elif not is_pdf_document:
        status = "OFFICIAL_WEBSITE_CONTENT_NOT_VERIFIED_REGULATION"

    elif not has_legal_indicators:
        status = "DOCUMENT_REQUIRES_MANUAL_REVIEW"

    else:
        status = "POTENTIAL_REGULATION_REQUIRES_DOCUMENT_VERIFICATION"

    return {
        "status": status,
        "official_domain": official_domain,
        "has_content": has_content,
        "is_pdf_document": is_pdf_document,
        "potential_regulation_content": potential_regulation,
        "verified_as_current_law": False,
        "message": (
            "This is a preliminary screening result. "
            "Legal authenticity, applicability, amendments "
            "and current validity require separate verification."
        )
    }
