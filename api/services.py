"""Business logic used by the API (framework independent, unit-testable)."""
from datetime import date

from agents.document_agent import analyze_document_full
from api import database as db
from config import MAX_UPLOAD_MB
from rag.document_loader import load_pdf_bytes
from workflows.graph import run_assessment


class ServiceError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def process_upload(filename, content, profile_id=None, use_ai=False, tenant_ids=None):
    if profile_id is not None and not db.get_profile(profile_id, tenant_ids=tenant_ids):
        raise ServiceError("Business profile not found.", 404)
    loaded = load_pdf_bytes(content, filename, MAX_UPLOAD_MB)
    if not loaded["success"]:
        # invalid/empty PDFs are rejected with a clear message and are not stored
        raise ServiceError(loaded["error"], 422)
    analysis = analyze_document_full(loaded["full_text"], filename, use_ai=use_ai)
    analysis["facts"].pop("air_sources_raw", None)
    return db.save_document(
        profile_id,
        filename,
        loaded["total_pages"],
        loaded["full_text"],
        None,
        analysis,
        tenant_ids=tenant_ids,
    )


def run_and_store_assessment(
    profile_id,
    document_ids,
    use_ai=False,
    assessment_date=None,
    tenant_ids=None,
):
    profile = db.get_profile(profile_id, tenant_ids=tenant_ids)
    if not profile:
        raise ServiceError("Business profile not found.", 404)
    docs = []
    for did in document_ids:
        d = db.get_document(did, with_text=True, tenant_ids=tenant_ids)
        if not d or d["profile_id"] != profile_id:
            raise ServiceError("Document not found for this business.", 404)
        docs.append({"id": d["id"], "filename": d["filename"], "pages": d["pages"], "text": d["text"] or ""})
    clean = {k: v for k, v in profile.items() if k not in ("created_at", "updated_at")}
    result = run_assessment(clean, docs, assessment_date or date.today(), use_ai)
    return db.save_assessment(profile_id, result, tenant_ids=tenant_ids)
