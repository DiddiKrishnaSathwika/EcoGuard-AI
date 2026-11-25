import unittest
from datetime import date
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import patch

import tests.conftest  # noqa: F401
from agents.llm_utils import AI_UNAVAILABLE_MESSAGE
from api import database as db
from api.services import ServiceError, process_upload, run_and_store_assessment
from evaluation.evaluate import run_evaluation
from pypdf import PdfReader
from utils.pdf_reader import extract_pdf_text
from utils.report_generator import generate_report_pdf
from utils.validators import ValidationFailure, validate_assessment_request, validate_business_profile
from regulation_engine.knowledge_base import get_entries
from workflows.graph import run_assessment

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample_documents" / "GreenLeaf_Environmental_Operations_Record.pdf"
GOOD = {"company": " GreenLeaf  Foods ", "industry": "Food Processing", "state": "Telangana",
        "wastewater": "Yes", "air_emissions": "Yes", "hazardous_waste": "No", "wastewater_volume_lpd": "1200"}


class ValidatorTests(unittest.TestCase):
    def test_valid_profile_normalised(self):
        p = validate_business_profile(GOOD)
        self.assertEqual(p["company"], "GreenLeaf Foods")
        self.assertEqual(p["wastewater_volume_lpd"], 1200.0)

    def test_invalid_profiles(self):
        for bad in ({**GOOD, "company": " "}, {**GOOD, "state": "Atlantis"}, {**GOOD, "wastewater_volume_lpd": "abc"},
                    {**GOOD, "wastewater": "No"}, {**GOOD, "industry": None}, "not a dict"):
            with self.assertRaises(ValidationFailure):
                validate_business_profile(bad)

    def test_assessment_request(self):
        request = validate_assessment_request({"profile_id": 1, "use_ai": True})
        self.assertEqual(request, {"profile_id": 1, "document_ids": [], "use_ai": True})
        with self.assertRaises(ValidationFailure):
            validate_assessment_request({"profile_id": "1"})


class WorkflowTests(unittest.TestCase):
    def test_assessment_skips_openrouter_when_not_requested(self):
        with patch("agents.llm_utils.OPENROUTER_API_KEY", "test-key"), \
                patch("agents.llm_utils.requests.post") as post:
            result = run_assessment(validate_business_profile(GOOD), [], date(2026, 11, 24))

        self.assertFalse(result["ai"]["requested"])
        post.assert_not_called()

    def test_sample_pdf_end_to_end(self):
        text = extract_pdf_text(SAMPLE.read_bytes())["full_text"]
        res = run_assessment({**validate_business_profile(GOOD)}, [{"id": 1, "filename": "s.pdf", "text": text}], date(2026, 11, 24))
        self.assertEqual(res["overall"]["counts"]["NON_COMPLIANT"], 0)  # missing docs are not violations
        self.assertEqual(res["overall"]["counts"]["COMPLIANT"], 0)
        self.assertTrue(res["ethics_review"]["passed"])
        self.assertFalse(res["ai"]["requested"])

    def test_ai_response_does_not_change_deterministic_findings(self):
        profile = validate_business_profile(GOOD)
        documents = [{"id": 1, "filename": "sample.pdf", "text": "No permit information provided."}]
        before = run_assessment(profile, documents, date(2026, 11, 24))
        applicable_ids = {
            item["requirement_id"]
            for item in before["applicability"]
            if item["status"] != "NOT_APPLICABLE"
        }
        instruments = list(dict.fromkeys(
            entry["instrument"] for entry in get_entries() if entry["id"] in applicable_ids
        ))
        ai_response = {
            "narrative": "Review the evidence gaps shown in the deterministic findings.",
            "interpretations": [
                {"instrument": instrument, "text": "Confirm the relevant records and details."}
                for instrument in instruments
            ],
        }
        response = type("FakeResponse", (), {
            "status_code": 200,
            "json": lambda self: {"choices": [{"message": {"content": json.dumps(ai_response)}}]},
        })()
        with patch("agents.llm_utils.OPENROUTER_API_KEY", "test-key"), \
                patch("agents.llm_utils.requests.post", return_value=response):
            after = run_assessment(profile, documents, date(2026, 11, 24), use_ai=True)

        self.assertEqual(after["ai"]["narrative"], ai_response["narrative"])
        self.assertEqual(after["overall"], before["overall"])
        self.assertEqual(
            [(f["status"], f["risk_level"], f["evidence_class"]) for f in after["findings"]],
            [(f["status"], f["risk_level"], f["evidence_class"]) for f in before["findings"]],
        )
        report = generate_report_pdf({"id": 1, "result": after})
        report_text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(report)).pages)
        self.assertIn("AI-generated explanations", report_text)
        self.assertIn("not verified legal advice", report_text)

    def test_evaluation_suite(self):
        out = run_evaluation()
        failed = [c["id"] for c in out["cases"] if not c["passed"]]
        self.assertEqual(failed, [])
        self.assertEqual(out["metrics"]["checks"], out["metrics"]["checks_passed"])


class DatabaseAndServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_full_flow_and_report(self):
        profile = db.create_profile(validate_business_profile(GOOD))
        with patch("agents.llm_utils.OPENROUTER_API_KEY", None), \
                patch("agents.llm_utils.requests.post") as post:
            doc = process_upload("sample.pdf", SAMPLE.read_bytes(), profile["id"], use_ai=False)
            a = run_and_store_assessment(profile["id"], [doc["id"]], use_ai=True)
            pdf = generate_report_pdf(db.get_assessment(a["id"]))
            post.assert_not_called()

        self.assertEqual(doc["pages"], 2)
        self.assertEqual(doc["analysis"]["ai_status"], "not_requested")
        self.assertEqual(a["result"]["ai"]["errors"], [AI_UNAVAILABLE_MESSAGE])
        self.assertIsNone(a["result"]["ai"]["narrative"])
        self.assertTrue(pdf.startswith(b"%PDF"))
        report_text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
        self.assertIn("3. Findings", report_text)
        self.assertIn("6. Recommendations", report_text)
        self.assertNotIn("AI-generated explanations", report_text)
        self.assertGreater(db.dashboard_stats()["assessments_total"], 0)
        self.assertTrue(db.delete_assessment(a["id"]))

    def test_invalid_uploads_rejected(self):
        for name, content in (("a.txt", b"hi"), ("a.pdf", b""), ("a.pdf", b"not a pdf"), ("a.pdf", b"%PDF-1.4 garbage")):
            with self.assertRaises(ServiceError):
                process_upload(name, content)

    def test_unknown_profile(self):
        with self.assertRaises(ServiceError):
            run_and_store_assessment(99999, [])

    def test_assessment_without_documents(self):
        p = db.create_profile(validate_business_profile(GOOD))
        a = run_and_store_assessment(p["id"], [])
        self.assertEqual(a["result"]["overall"]["counts"]["COMPLIANT"], 0)
        self.assertIn("No documents", a["result"]["limitations"][0])


if __name__ == "__main__":
    unittest.main()
