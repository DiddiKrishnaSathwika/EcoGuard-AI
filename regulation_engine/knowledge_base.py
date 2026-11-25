"""Curated regulatory knowledge base + status of registry sources / cache."""
import json
import logging
from datetime import datetime, timezone

from config import KNOWLEDGE_BASE_FILE
from regulation_engine.source_registry import get_all_sources, validate_sources
from utils.storage import get_json

_cache = {}
logger = logging.getLogger(__name__)


def load_knowledge_base():
    mtime = KNOWLEDGE_BASE_FILE.stat().st_mtime if KNOWLEDGE_BASE_FILE.exists() else None
    if _cache.get("mtime") != mtime or "kb" not in _cache:
        if mtime is None:
            raise FileNotFoundError(f"Regulatory knowledge base not found: {KNOWLEDGE_BASE_FILE}")
        _cache["kb"] = json.loads(KNOWLEDGE_BASE_FILE.read_text(encoding="utf-8"))
        _cache["mtime"] = mtime
    return _cache["kb"]


def get_entries():
    return load_knowledge_base()["entries"]


def get_entry(entry_id):
    return next((e for e in get_entries() if e["id"] == entry_id), None)


def kb_reference_labels():
    """Every Section/Rule label the KB legitimately cites (used by the ethics check)."""
    import re
    labels = set()
    for e in get_entries():
        for m in re.finditer(r"(Section|Rule)\s+(\d+[A-Za-z]?)", e["citation"]):
            labels.add(f"{m.group(1)} {m.group(2)}".lower())
    return labels


def source_status():
    """Registry sources merged with their persistent cache status."""
    validation = validate_sources()
    out = []
    for s in get_all_sources():
        item = dict(s)
        cache_key = f"data/cached_regulations/{s['source_id']}.json"
        try:
            rec = get_json(cache_key)
            item["cached"] = rec is not None
            if rec is not None:
                item["retrieved_at"] = rec.get("retrieved_at")
                item["validation_status"] = rec.get("validation", {}).get("status")
                item["content_classification"] = rec.get("content_classification", "UNVERIFIED_WEBSITE_CONTENT")
                item["verified_as_current_law"] = rec.get("validation", {}).get("verified_as_current_law", False)
                item["note"] = ("Cached website content. It is NOT treated as law and is not used for findings.")
            else:
                item["note"] = "Not retrieved yet."
        except Exception:
            logger.exception("Could not read persistent regulation cache %s", cache_key)
            item["cached"] = False
            item["note"] = "Persistent cache could not be checked."
        out.append(item)
    return {"sources": out, "registry_validation": validation,
            "checked_at": datetime.now(timezone.utc).isoformat()}
