
import re
from datetime import datetime, timezone


def parse_regulation_text(
    text,
    source_name,
    source_url
):

    if not text or not text.strip():
        return {
            "status": "INSUFFICIENT_CONTENT",
            "source": source_name,
            "url": source_url,
            "sections": [],
            "content": ""
        }

    # Split text into paragraphs
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n+", text)
        if paragraph.strip()
    ]

    # Identify possible legal sections and rules
    sections = []

    patterns = [
        r"\bSection\s+\d+[A-Za-z]?\b",
        r"\bRule\s+\d+[A-Za-z]?\b",
        r"\bRegulation\s+\d+[A-Za-z]?\b",
        r"\bSchedule\s+[IVXLCDM\d]+\b"
    ]

    for paragraph in paragraphs:

        for pattern in patterns:

            matches = re.findall(
                pattern,
                paragraph,
                flags=re.IGNORECASE
            )

            for match in matches:

                sections.append({
                    "reference": match,
                    "text": paragraph
                })

    return {
        "status": "CONTENT_EXTRACTED",
        "source": source_name,
        "url": source_url,
        "retrieved_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "total_paragraphs": len(paragraphs),
        "sections": sections,
        "content": "\n".join(paragraphs)
    }
