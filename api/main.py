"""EcoGuard AI - FastAPI backend.

Run:  uvicorn api.main:app --reload --port 8000
Docs: http://127.0.0.1:8000/docs
"""
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from agents.llm_utils import llm_status
from api.auth import get_current_user, require_platform_admin
from api import database as db
from api.services import ServiceError, process_upload, run_and_store_assessment
from config import (APP_DESCRIPTION, APP_NAME, BASE_DIR, CORS_ORIGINS, DATABASE_URL, MAX_UPLOAD_MB,
                    AUTH_ADMIN_SUBJECTS, USE_VECTOR_DB)
from evaluation.evaluate import run_evaluation
from rag.retriever import retrieve_regulations
from regulation_engine.applicability_checker import check_applicability
from regulation_engine.knowledge_base import load_knowledge_base, source_status
from agents.fact_extractor import TOPIC_LABELS, merge_document_facts, extract_facts
from utils.report_generator import generate_report_pdf
from utils.storage import put_bytes
from utils.validators import (INDUSTRIES, STATES, YES_NO, ValidationFailure,
                              validate_assessment_request, validate_business_profile)

app = FastAPI(title=f"{APP_NAME} API", description=APP_DESCRIPTION, version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])
if not DATABASE_URL:
    db.init_db()


def current_tenant_ids(user=Depends(get_current_user)):
    return db.get_tenant_ids(user["issuer"], user["subject"])


@app.exception_handler(ValidationFailure)
async def _validation_handler(request, exc):
    return JSONResponse(status_code=422, content={"detail": "Validation failed", "errors": exc.errors})


@app.exception_handler(ServiceError)
async def _service_handler(request, exc):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


def _need(value, what):
    if value is None:
        raise HTTPException(status_code=404, detail=f"{what} not found.")
    return value


# ---------------- system ----------------
@app.get("/api/health")
def health():
    return {"status": "ok", "app": APP_NAME}


@app.get("/api/status")
def status():
    return {"llm": llm_status(), "vector_db_enabled": USE_VECTOR_DB, "max_upload_mb": MAX_UPLOAD_MB,
            "knowledge_base": {k: v for k, v in load_knowledge_base().items() if k != "entries"} |
                              {"entries": len(load_knowledge_base()["entries"])}}


@app.get("/api/meta/options")
def options():
    return {"industries": INDUSTRIES, "states": STATES, "yes_no": YES_NO}


@app.get("/api/session")
def session(user=Depends(get_current_user)):
    return {"is_platform_admin": user["subject"] in AUTH_ADMIN_SUBJECTS}


# ---------------- dashboard ----------------
@app.get("/api/dashboard")
def dashboard(tenant_ids: list[int] = Depends(current_tenant_ids)):
    stats = db.dashboard_stats(tenant_ids=tenant_ids)
    profiles = db.list_profiles(tenant_ids=tenant_ids)
    stats["latest_profile"] = profiles[0] if profiles else None
    latest = stats["latest"]
    if latest:
        res = latest["result"]
        stats["latest_summary"] = {"overall": res["overall"], "company": res["profile"]["company"],
                                   "top_findings": [{"title": f["title"], "status": f["status"], "status_label": f["status_label"],
                                                     "risk_level": f["risk_level"]} for f in res["findings"][:5]]}
        stats["latest"] = {k: v for k, v in latest.items() if k != "result"}
    return stats


# ---------------- business profiles ----------------
@app.get("/api/profiles")
def list_profiles(tenant_ids: list[int] = Depends(current_tenant_ids)):
    return db.list_profiles(tenant_ids=tenant_ids)


@app.post("/api/profiles", status_code=201)
def create_profile(payload: dict, user=Depends(get_current_user)):
    return db.create_profile_for_user(
        validate_business_profile(payload),
        user["issuer"],
        user["subject"],
    )


@app.get("/api/profiles/{profile_id}")
def get_profile(profile_id: int, tenant_ids: list[int] = Depends(current_tenant_ids)):
    return _need(db.get_profile(profile_id, tenant_ids=tenant_ids), "Business profile")


@app.put("/api/profiles/{profile_id}")
def update_profile(profile_id: int, payload: dict, tenant_ids: list[int] = Depends(current_tenant_ids)):
    _need(db.get_profile(profile_id, tenant_ids=tenant_ids), "Business profile")
    return db.update_profile(
        profile_id,
        validate_business_profile(payload),
        tenant_ids=tenant_ids,
    )


@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: int, tenant_ids: list[int] = Depends(current_tenant_ids)):
    if not db.delete_profile(profile_id, tenant_ids=tenant_ids):
        raise HTTPException(404, "Business profile not found.")
    return {"deleted": True}


# ---------------- documents ----------------
@app.post("/api/documents/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    profile_id: int | None = Form(None),
    use_ai: bool = Form(False),
    tenant_ids: list[int] = Depends(current_tenant_ids),
):
    if profile_id is None:
        raise HTTPException(422, "A business profile is required for document uploads.")
    content = await file.read()
    return process_upload(
        file.filename or "",
        content,
        profile_id,
        use_ai,
        tenant_ids=tenant_ids,
    )


@app.get("/api/documents")
def list_documents(
    profile_id: int | None = Query(None),
    tenant_ids: list[int] = Depends(current_tenant_ids),
):
    return db.list_documents(profile_id, tenant_ids=tenant_ids)


@app.get("/api/documents/{document_id}")
def get_document(document_id: int, tenant_ids: list[int] = Depends(current_tenant_ids)):
    return _need(
        db.get_document(document_id, with_text=True, tenant_ids=tenant_ids),
        "Document",
    )


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: int, tenant_ids: list[int] = Depends(current_tenant_ids)):
    if not db.delete_document(document_id, tenant_ids=tenant_ids):
        raise HTTPException(404, "Document not found.")
    return {"deleted": True}


# ---------------- regulations ----------------
@app.get("/api/regulations")
def regulations():
    kb = load_knowledge_base()
    return {**{k: v for k, v in kb.items()}, "sources": source_status()}


@app.post("/api/regulations/retrieve")
def retrieve(payload: dict, tenant_ids: list[int] = Depends(current_tenant_ids)):
    pid = payload.get("profile_id")
    profile = _need(
        db.get_profile(pid, tenant_ids=tenant_ids)
        if isinstance(pid, int)
        else None,
        "Business profile",
    )
    docs = []
    for document_id in payload.get("document_ids", []):
        document = db.get_document(
            document_id,
            with_text=True,
            tenant_ids=tenant_ids,
        )
        if document is None or document["profile_id"] != pid:
            raise HTTPException(404, "Document not found for this business.")
        docs.append(document)
    merged = merge_document_facts([(d["filename"], extract_facts(d["text"] or "")) for d in docs])
    entries = load_knowledge_base()["entries"]
    labels = [TOPIC_LABELS[t] for t, v in merged["topics"].items() if v["status"] != "none"]
    retrieved = retrieve_regulations(profile, entries, labels, " ".join((d["text"] or "")[:800] for d in docs))
    applic = {a["requirement_id"]: a for a in check_applicability(profile, merged)}
    by_id = {e["id"]: e for e in entries}
    return {"method": retrieved["method"], "note": retrieved["note"],
            "results": [{**r, "entry": by_id[r["requirement_id"]], "applicability": applic[r["requirement_id"]]}
                        for r in retrieved["results"]],
            "coverage_limitations": load_knowledge_base()["coverage_limitations"]}


@app.post("/api/regulations/sources/{source_id}/refresh")
def refresh_source(source_id: str, _user=Depends(require_platform_admin)):
    from regulation_engine.regulation_cache import process_and_cache_source
    try:
        out = process_and_cache_source(source_id)
    except ValueError as error:
        raise HTTPException(404, str(error))
    except Exception as error:
        raise HTTPException(502, f"Could not retrieve the source: {error}")
    if not out.get("success"):
        raise HTTPException(502, f"{out.get('message')} {out.get('error') or ''}".strip())
    return out


# ---------------- assessments ----------------
@app.post("/api/assessments", status_code=201)
def create_assessment(payload: dict, tenant_ids: list[int] = Depends(current_tenant_ids)):
    req = validate_assessment_request(payload)
    return run_and_store_assessment(
        req["profile_id"],
        req["document_ids"],
        req["use_ai"],
        tenant_ids=tenant_ids,
    )


@app.get("/api/assessments")
def list_assessments(tenant_ids: list[int] = Depends(current_tenant_ids)):
    return db.list_assessments(tenant_ids=tenant_ids)


@app.get("/api/assessments/{assessment_id}")
def get_assessment(assessment_id: int, tenant_ids: list[int] = Depends(current_tenant_ids)):
    return _need(
        db.get_assessment(assessment_id, tenant_ids=tenant_ids),
        "Assessment",
    )


@app.delete("/api/assessments/{assessment_id}")
def delete_assessment(assessment_id: int, tenant_ids: list[int] = Depends(current_tenant_ids)):
    if not db.delete_assessment(assessment_id, tenant_ids=tenant_ids):
        raise HTTPException(404, "Assessment not found.")
    return {"deleted": True}


@app.get("/api/assessments/{assessment_id}/report.pdf")
def assessment_report(assessment_id: int, tenant_ids: list[int] = Depends(current_tenant_ids)):
    assessment = _need(
        db.get_assessment(assessment_id, tenant_ids=tenant_ids),
        "Assessment",
    )
    pdf = generate_report_pdf(assessment)
    put_bytes(
        f"reports/EcoGuard_Report_{assessment_id}.pdf",
        pdf,
        content_type="application/pdf",
    )
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="EcoGuard_Report_{assessment_id}.pdf"'})


# ---------------- evaluation ----------------
@app.post("/api/evaluation/run")
def evaluation_run(_user=Depends(require_platform_admin)):
    return run_evaluation()


# ---------------- optional: serve the built frontend (single-process mode) ----------------
_dist = BASE_DIR / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
