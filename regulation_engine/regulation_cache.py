
from datetime import datetime, timezone

from regulation_engine.live_retriever import (
    retrieve_source_by_id
)

from regulation_engine.regulation_parser import (
    parse_regulation_text
)

from regulation_engine.source_validator import (
    validate_regulation_source
)
from utils.storage import put_json


def process_and_cache_source(source_id):

    retrieved = retrieve_source_by_id(source_id)

    if retrieved["retrieval_status"] != "HTTP_SUCCESS":
        return {
            "success": False,
            "message": "Source retrieval failed.",
            "error": retrieved["error"]
        }

    if not retrieved["content"].strip():
        return {
            "success": False,
            "message": "No extractable text was found."
        }

    # Validate the source and retrieved content
    validation = validate_regulation_source(
        source_url=retrieved.get(
            "final_url",
            retrieved["url"]
        ),
        content=retrieved["content"],
        source_title=retrieved.get("page_title")
    )

    # Parse retrieved text
    parsed = parse_regulation_text(
        text=retrieved["content"],
        source_name=retrieved["authority"],
        source_url=retrieved["url"]
    )

    cache_record = {
        "source_id": source_id,
        "authority": retrieved["authority"],
        "source_url": retrieved.get(
            "final_url",
            retrieved["url"]
        ),
        "page_title": retrieved.get("page_title"),
        "retrieved_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "retrieval_status": retrieved["retrieval_status"],
        "validation": validation,
        "content_classification": (
            "UNVERIFIED_WEBSITE_CONTENT"
        ),
        "parsed_data": parsed
    }

    cache_file = put_json(
        f"data/cached_regulations/{source_id}.json",
        cache_record,
    )

    return {
        "success": True,
        "message": "Source retrieved, validated and cached.",
        "cache_file": str(cache_file),
        "validation_status": validation["status"],
        "verified_as_current_law": validation[
            "verified_as_current_law"
        ],
        "paragraphs": parsed["total_paragraphs"],
        "sections_found": len(parsed["sections"])
    }
