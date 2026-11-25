# EcoGuard AI

Environmental compliance screening for Indian SMEs.
**React** (frontend) + **FastAPI** (backend) + local SQLite or PostgreSQL + your existing Python agents. No Streamlit.

Workflow: Business Profile -> Document Upload -> Document Analysis -> Regulatory Retrieval -> Compliance Assessment -> Recommendations -> Results -> PDF Report.

> EcoGuard AI is a **screening aid, not legal advice**. See "Honest limitations" below.

---

## 1. Requirements (Windows)

| Tool | Version | Check in PowerShell |
|---|---|---|
| Python | 3.10 or newer (3.13 works) | `python --version` |
| Node.js | 18 or newer (includes npm) | `node --version` ; `npm --version` |
| VS Code | any | |

## 2. First-time setup (PowerShell, from the project folder)

Open the extracted `EcoGuard_AI` folder in VS Code, then **Terminal > New Terminal**.

```powershell
# 1) Backend: create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# If you see "running scripts is disabled", run this once and retry:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 2) Install backend dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 3) Create your private settings file
copy .env.example .env
# (optional) open .env and paste your OPENROUTER_API_KEY - see section 4

# 4) Frontend dependencies
cd frontend
copy .env.example .env
# Configure the OIDC values in .env before signing in.
npm install
cd ..
```

## 3. Run the application (two terminals)

**Terminal 1 - backend** (project root, venv active):
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn api.main:app --reload --port 8000
```
Check: http://127.0.0.1:8000/api/health should show `{"status":"ok"...}`. Interactive API docs: http://127.0.0.1:8000/docs

**Terminal 2 - frontend**:
```powershell
cd frontend
npm run dev
```
Open **http://localhost:5173**

### Optional: single-process mode
```powershell
cd frontend ; npm run build ; cd ..
uvicorn api.main:app --port 8000
```
Then open http://127.0.0.1:8000 (FastAPI serves the built React app).

### Optional: persistent PostgreSQL on Neon

Local development remains on SQLite when `DATABASE_URL` is blank. For production, configure `DATABASE_URL` as a private environment variable using Neon's pooled PostgreSQL connection string with SSL enabled. Configure it only on the backend, never in the frontend.

### Authentication and business isolation

The API uses provider-agnostic OIDC access-token validation. Configure the backend values `OIDC_ISSUER`, `OIDC_AUDIENCE`, and `OIDC_JWKS_URL`, and set the React public SPA values in `frontend/.env`: `VITE_OIDC_AUTHORITY`, `VITE_OIDC_CLIENT_ID`, and `VITE_OIDC_AUDIENCE`. The issuer and JWKS URLs must use HTTPS. Register the configured redirect URI with the identity provider and issue access tokens for the configured API audience. The React app uses authorization-code flow with PKCE and keeps the access token in memory; password storage and password-reset policy remain the identity provider's responsibility. Private API routes remain unavailable until OIDC is configured.

Set `AUTH_ADMIN_SUBJECTS` on the backend to a comma-separated list of trusted OIDC `sub` values allowed to refresh registered sources or run the evaluation suite. No admin subjects are enabled by default.

Each newly created business profile gets a tenant and an owner membership derived from the verified issuer and subject. Profile, document, assessment, dashboard, and report queries are scoped to those memberships, and documents must belong to the profile being assessed. Existing records receive a nullable tenant ID and remain inaccessible until an operator explicitly maps them; no ownership is inferred or assigned automatically. Run `python -m alembic upgrade head` before deploying the PostgreSQL schema migration. Local SQLite initialization adds the nullable column without rewriting existing records.

### Persistent files on Vercel

Local development keeps reports and retrieved-source cache JSON under the project directory. For Vercel, create and connect a **private Vercel Blob store**, then set the backend environment variable `FILE_STORAGE_BACKEND=vercel_blob`. The Blob SDK uses Vercel's `BLOB_STORE_ID` and OIDC credentials supplied by the connected store; do not expose these values to the frontend. A `BLOB_READ_WRITE_TOKEN` is only needed for non-Vercel environments that cannot use OIDC.

Keep `FILE_STORAGE_BACKEND=local` for local development. Vercel deployments must use `vercel_blob`; Blob failures do not fall back to the function filesystem. Reports continue to be generated and returned by the existing PDF endpoint, while a private archived copy is stored in Blob. Retrieved website content remains classified as unverified. Existing local report/cache files are not copied automatically; cached sources can be refreshed through the existing API.

Uploaded PDF originals are not retained by the application; extracted text and analysis are stored in the database. Vercel Functions limit request bodies to approximately 4.5 MB, which is lower than the app's default 15 MB upload limit. Larger uploads need a separate direct-to-Blob upload flow. Keep `USE_VECTOR_DB=false` on Vercel; optional Chroma persistence is local-only, while BM25 remains the default retriever.

Run the schema migration explicitly before starting the production app:

```powershell
python -m alembic upgrade head
```

To copy local data, back up the SQLite file and stop the app first. The migration script opens the source read-only, requires an empty PostgreSQL target, and defaults to a dry run:

```powershell
python -m scripts.migrate_sqlite_to_postgres --sqlite-path .\data\ecoguard.db
python -m scripts.migrate_sqlite_to_postgres --sqlite-path .\data\ecoguard.db --apply
```

The app does not run PostgreSQL schema migrations during FastAPI import. The SQLite copy helper is for legacy data only and is unsafe for authenticated tenant data; dry-run counts and target checks do not replace tenant/membership migration or explicit ownership mapping.

**Tenant-data migration warning:** `scripts/migrate_sqlite_to_postgres.py` copies only business profiles, documents, and assessments. It does not migrate tenants or memberships or map ownership. Do not use its `--apply` option for authenticated tenant data until tenant/membership migration and explicit ownership mapping are implemented and reviewed.

## 4. OpenRouter API key (optional)

The app works **without** a key: document evidence extraction, applicability, compliance findings, recommendations, PDF reports and the evaluation suite are rule based.
An OpenRouter key enables optional AI analysis of uploaded documents and, when selected for an assessment, an AI-generated narrative and regulatory explanations. AI output is clearly labeled and cannot change deterministic statuses or risk levels.

1. Create an OpenRouter API key.
2. Put it in `.env`: `OPENROUTER_API_KEY=your_key`
3. Optionally select a model with `OPENROUTER_MODEL`; the default is `openai/gpt-4.1-mini`.
4. Restart the backend. The Dashboard banner disappears when the key is configured.

Run `python scripts/openrouter_connectivity.py` from the project root to make a real request to the configured model.

Without a key or when OpenRouter is unavailable, rule-based assessments, findings and PDF reports continue to work.

## 5. Using the app

1. **Business Profile** - company, industry, state, wastewater / air emissions / hazardous waste details. Saved to the configured database.
2. **Documents** - upload text-based PDFs. Invalid, empty, encrypted or non-PDF files are rejected with a message. The optional GreenLeaf sample is not included in public distributions unless it has been confirmed synthetic or redacted and cleared for redistribution.
3. **Regulations** - ranked relevant provisions, curated knowledge base, registered sources, and coverage limits.
4. **Assessment & Results** - run an assessment; see overall result, findings with evidence, recommendations, regulations, and workflow trace.
5. **Reports** - download the PDF report for any assessment.
6. **AI Evaluation** - runs `evaluation/test_cases.json` and shows real, computed results.

## 6. How findings are decided

| Status | Rule |
|---|---|
| Compliant | Evidence found; for consents/authorisations also a reference number and a validity date that has not passed |
| Partially compliant | Evidence found but reference number or validity date missing |
| Non-compliant | Only when documents **explicitly** state absence/refusal/expiry (or a validity date has passed) **and** the requirement firmly applies |
| Insufficient evidence | Nothing found, or the document says "not provided". **Missing documents are never a violation** |

Statuses come from the rule engine, never from an LLM. The integrity reviewer (`agents/ethics_agent.py`) blocks compliant-without-evidence and non-compliant-without-explicit-evidence, and suppresses generated text with unsupported citations or assurance language.

## 7. Project layout

```
api/                FastAPI app (main.py), SQLite/PostgreSQL layer (database.py), services.py
agents/             document_agent, regulation_agent (yours, kept) + compliance, recommendation,
                    ethics, fact_extractor, llm_utils (new)
rag/                text_splitter, vector_store, retriever (yours) + local_retriever (BM25), document_loader
regulation_engine/  your source registry/validator/parser/cache/live_retriever + knowledge_base,
                    applicability_checker, amendment_checker
workflows/          state.py, graph.py (LangGraph if installed, sequential fallback)
evaluation/         dataset, evaluators, evaluate, test_cases.json
utils/              pdf_reader, report_generator (ReportLab), validators
data/               source_registry.json, regulatory_knowledge_base.json; local-only cached_regulations/, sample_documents/
frontend/           React + Vite app
tests/              unit tests (+ HTTP tests that need requirements-dev.txt)
```

### Public repository and sample data

The curated source registry, regulatory knowledge base, and `evaluation/test_cases.json` are project data intended for review and publication (check third-party source terms before redistributing). Files under `data/sample_documents/`, including the GreenLeaf PDF and JSON, are excluded by default: their contents and redistribution rights have not been verified for public release. Keep uploaded documents, local databases, generated reports, and retrieved-source caches private as well.

## 8. Tests

```powershell
pip install -r requirements-dev.txt
pytest -v
python -m evaluation.evaluate
```
`tests/test_api.py` exercises the real HTTP API and needs `httpx` (in `requirements-dev.txt`).

## 9. Honest limitations

* **Regulatory coverage is small and curated.** The knowledge base has 8 requirements from three instruments: Water Act 1974 s.25, Air Act 1981 s.21, Hazardous and Other Wastes Rules 2016 (Rules 6 and 19 forms). Sections and subjects were confirmed against public sources on 2026-11-24, but summaries are paraphrases that were **not lawyer-reviewed**, and amendments were **not** checked.
* **Not covered:** state rules/standards and consent categories, industry-specific effluent/emission standards, DG-set norms, solid/plastic/e-waste/battery rules (EPR), environmental clearance, penalties.
* The Air Act requirement applies only inside a declared air pollution control area, so it is always shown as *conditionally applicable*, and an air consent gap is never asserted as non-compliance.
* A local `data/cached_regulations/CPCB_RULES.json` may contain scraped website content; it is unverified and is never used as law. It and files in `data/sample_documents/` are local data and are excluded from public repository uploads by default.
* Scanned (image-only) PDFs are not supported (no OCR).
* **AI Evaluation** uses 10 synthetic cases written with the project. They check that the assessment logic follows the rules above; they do **not** measure real-world legal accuracy or score OpenRouter-generated explanations.
* LangSmith: tracing works automatically for LLM calls when `LANGSMITH_TRACING=true` and a key are set; evaluation results are not uploaded to LangSmith.
* ChromaDB/Google Gemini embeddings are optional (`USE_VECTOR_DB=true`, `pip install -r requirements-optional.txt`) and require `GOOGLE_API_KEY`. The default retriever is local BM25. The vector path could not be exercised during development.

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| Browser shows "Cannot reach the EcoGuard backend" | Start the backend (Terminal 1); check http://127.0.0.1:8000/api/health |
| `ModuleNotFoundError: fastapi` | Activate the venv, then `pip install -r requirements.txt` |
| `ModuleNotFoundError: config` / `api` | Run `uvicorn` from the project root (the folder containing `config.py`) |
| Port 8000 or 5173 busy | `uvicorn api.main:app --port 8001` and set `target` in `frontend/vite.config.js`; or `npm run dev -- --port 5174` and add it to `CORS_ORIGINS` in `.env` |
| `npm install` fails | Use Node 18+; delete `frontend/node_modules` and retry |
| "No readable text found" | The PDF is a scan. Use a text-based PDF |
| AI options greyed out | No `OPENROUTER_API_KEY`, or OpenRouter is unavailable |
| `pip install` fails on chromadb | It is not needed; it is in `requirements-optional.txt` only |
| Reset all data | Stop the backend, delete `data/ecoguard.db` |

## 11. Security

Never commit or share `.env`. If an `OPENROUTER_API_KEY` was exposed (for example in a ZIP), revoke it in the OpenRouter dashboard and create a replacement. Rotate any optional provider credentials in that provider's console as well.
