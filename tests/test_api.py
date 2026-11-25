"""HTTP-level tests. Require: pip install -r requirements-dev.txt"""
import unittest
from pathlib import Path
from unittest.mock import patch

import tests.conftest  # noqa: F401

try:
    from fastapi.testclient import TestClient
    from api.main import app
    from api.auth import get_current_user, require_platform_admin
    AVAILABLE = True
except Exception:  # fastapi/httpx not installed
    AVAILABLE = False

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample_documents" / "GreenLeaf_Environmental_Operations_Record.pdf"
PROFILE = {"company": "API Test Co", "industry": "Food Processing", "state": "Telangana",
           "wastewater": "Yes", "air_emissions": "Yes", "hazardous_waste": "No"}


@unittest.skipUnless(AVAILABLE, "fastapi / httpx not installed")
class ApiTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[get_current_user] = lambda: {
            "issuer": "https://issuer.example/",
            "subject": "api-test-user",
        }
        app.dependency_overrides[require_platform_admin] = lambda: {
            "issuer": "https://issuer.example/",
            "subject": "api-admin-user",
        }
        self.c = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_health_status_options(self):
        self.assertEqual(self.c.get("/api/health").json()["status"], "ok")
        self.assertIn("llm", self.c.get("/api/status").json())
        self.assertIn("Telangana", self.c.get("/api/meta/options").json()["states"])

    def test_profile_validation_errors(self):
        r = self.c.post("/api/profiles", json={**PROFILE, "company": ""})
        self.assertEqual(r.status_code, 422)
        self.assertIn("company", r.json()["errors"])

    def test_sensitive_api_routes_require_authentication(self):
        overrides = app.dependency_overrides.copy()
        app.dependency_overrides.clear()
        try:
            self.assertEqual(self.c.get("/api/profiles").status_code, 401)
            self.assertEqual(self.c.get("/api/documents/1").status_code, 401)
            self.assertEqual(self.c.get("/api/assessments").status_code, 401)
            self.assertEqual(self.c.get("/api/dashboard").status_code, 401)
        finally:
            app.dependency_overrides.update(overrides)

    def test_platform_admin_operations_reject_non_admin_users(self):
        admin_override = app.dependency_overrides.pop(require_platform_admin)
        try:
            response = self.c.post("/api/evaluation/run")
            self.assertEqual(response.status_code, 403)
            response = self.c.post("/api/regulations/sources/UNKNOWN/refresh")
            self.assertEqual(response.status_code, 403)
        finally:
            app.dependency_overrides[require_platform_admin] = admin_override

    def test_profiles_documents_and_assessments_are_tenant_scoped(self):
        profile_response = self.c.post("/api/profiles", json=PROFILE)
        self.assertEqual(profile_response.status_code, 201)
        profile_id = profile_response.json()["id"]
        with open(SAMPLE, "rb") as source:
            upload_response = self.c.post(
                "/api/documents/upload",
                files={"file": ("tenant.pdf", source, "application/pdf")},
                data={"profile_id": str(profile_id)},
            )
        self.assertEqual(upload_response.status_code, 201)
        document_id = upload_response.json()["id"]
        assessment_response = self.c.post(
            "/api/assessments",
            json={"profile_id": profile_id, "document_ids": [document_id]},
        )
        self.assertEqual(assessment_response.status_code, 201)
        assessment_id = assessment_response.json()["id"]

        app.dependency_overrides[get_current_user] = lambda: {
            "issuer": "https://issuer.example/",
            "subject": "different-user",
        }
        self.assertEqual(self.c.get(f"/api/profiles/{profile_id}").status_code, 404)
        self.assertEqual(self.c.get(f"/api/documents/{document_id}").status_code, 404)
        self.assertEqual(self.c.get(f"/api/assessments/{assessment_id}").status_code, 404)
        self.assertEqual(
            self.c.get(f"/api/assessments/{assessment_id}/report.pdf").status_code,
            404,
        )
        self.assertEqual(self.c.get("/api/profiles").json(), [])
        self.assertEqual(
            self.c.post(
                "/api/assessments",
                json={"profile_id": profile_id, "document_ids": [document_id]},
            ).status_code,
            404,
        )

    def test_complete_workflow(self):
        pid = self.c.post("/api/profiles", json=PROFILE).json()["id"]
        with open(SAMPLE, "rb") as fh:
            up = self.c.post("/api/documents/upload", files={"file": ("s.pdf", fh, "application/pdf")}, data={"profile_id": str(pid)})
        self.assertEqual(up.status_code, 201)
        did = up.json()["id"]
        a = self.c.post("/api/assessments", json={"profile_id": pid, "document_ids": [did]})
        self.assertEqual(a.status_code, 201)
        aid = a.json()["id"]
        self.assertEqual(a.json()["result"]["overall"]["counts"]["NON_COMPLIANT"], 0)
        with patch("api.main.put_bytes") as persist_report:
            pdf = self.c.get(f"/api/assessments/{aid}/report.pdf")
        persist_report.assert_called_once()
        self.assertEqual(persist_report.call_args.args[0], f"reports/EcoGuard_Report_{aid}.pdf")
        self.assertEqual(persist_report.call_args.kwargs["content_type"], "application/pdf")
        self.assertEqual(pdf.headers["content-type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertEqual(self.c.get("/api/dashboard").status_code, 200)
        self.assertEqual(self.c.post("/api/evaluation/run").json()["metrics"]["cases"], 10)

    def test_bad_uploads(self):
        r = self.c.post("/api/documents/upload", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
        self.assertEqual(r.status_code, 422)
        r = self.c.post("/api/documents/upload", files={"file": ("x.txt", b"hi", "text/plain")})
        self.assertEqual(r.status_code, 422)

    def test_not_found(self):
        self.assertEqual(self.c.get("/api/assessments/999999").status_code, 404)
        self.assertEqual(self.c.post("/api/assessments", json={"profile_id": 999999}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
