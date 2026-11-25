
import json
from pathlib import Path

from config import DATA_DIR


REGISTRY_FILE = DATA_DIR / "source_registry.json"


def load_source_registry():

    if not REGISTRY_FILE.exists():
        raise FileNotFoundError(
            f"Source registry not found: {REGISTRY_FILE}"
        )

    with open(REGISTRY_FILE, "r", encoding="utf-8") as file:
        registry = json.load(file)

    if "sources" not in registry:
        raise ValueError(
            "Invalid registry: 'sources' field is missing."
        )

    return registry


def get_all_sources():

    registry = load_source_registry()

    return registry["sources"]


def get_source_by_id(source_id):

    sources = get_all_sources()

    for source in sources:
        if source["source_id"] == source_id:
            return source

    return None


def validate_sources():

    sources = get_all_sources()

    required_fields = [
        "source_id",
        "authority",
        "scope",
        "category",
        "url",
        "source_type",
        "ingestion_status"
    ]

    errors = []

    for source in sources:

        for field in required_fields:

            if not source.get(field):
                errors.append(
                    f"{source.get('source_id', 'Unknown')}: "
                    f"Missing {field}"
                )

        url = source.get("url", "")

        if not url.startswith("https://"):
            errors.append(
                f"{source.get('source_id', 'Unknown')}: "
                "Source URL must use HTTPS."
            )

    return {
        "valid": len(errors) == 0,
        "total_sources": len(sources),
        "errors": errors
    }
