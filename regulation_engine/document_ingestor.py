
import re
from datetime import datetime, timezone
from pathlib import Path

from utils.pdf_reader import extract_pdf_text

from regulation_engine.regulation_parser import (
    parse_regulation_text
)

from regulation_engine.source_validator import (
    validate_regulation_source
)
from utils.storage import put_json


def ingest_regulation_pdf(
    pdf_path,
    document_id,
    document_title,
    authority,
    source_url,
    effective_date="Not provided"
):

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        return {
            "success": False,
            "message": "PDF file does not exist."
        }

    if pdf_path.suffix.lower() != ".pdf":
        return {
            "success": False,
            "message": "Only PDF documents are accepted."
        }

    # Extract PDF text
    extracted = extract_pdf_text(pdf_path)

    if not extracted["success"]:
        return {
            "success": False,
            "message": extracted["error"]
        }

    # Preliminary source validation
    validation = validate_regulation_source(
        source_url=source_url,
        content=extracted["full_text"],
        source_title=document_title
    )

    # Parse extracted text
    parsed = parse_regulation_text(
        text=extracted["full_text"],
        source_name=authority,
        source_url=source_url
    )

    # Sanitize document ID for filename
    safe_id = re.sub(
        r"[^A-Za-z0-9_-]",
        "_",
        document_id
    )

    if not safe_id:
        return {
            "success": False,
            "message": "Invalid document ID."
        }

    # Prepare document record
    record = {
        "document_id": safe_id,
        "document_title": document_title,
        "authority": authority,
        "source_url": source_url,
        "effective_date": effective_date,
        "original_filename": pdf_path.name,
        "retrieved_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "total_pages": extracted["total_pages"],
        "validation": validation,
        "verification_status": "PENDING_MANUAL_VERIFICATION",
        "verified_as_current_law": False,
        "parsed_data": parsed
    }

    # Save document metadata and extracted text
    output_file = put_json(
        f"data/cached_regulations/{safe_id}.json",
        record,
    )

    return {
        "success": True,
        "message": "PDF extracted and cached successfully.",
        "cache_file": str(output_file),
        "pages": extracted["total_pages"],
        "paragraphs": parsed["total_paragraphs"],
        "sections_found": len(parsed["sections"]),
        "validation_status": validation["status"],
        "verification_status": record[
            "verification_status"
        ]
    }
