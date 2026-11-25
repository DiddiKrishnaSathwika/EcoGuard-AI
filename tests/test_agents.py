import unittest
from datetime import date
from unittest.mock import patch

import requests
import tests.conftest  # noqa: F401  (sets up sys.path and a temp database)
from agents.compliance_agent import assess_compliance, generate_ai_explanations, summarize_overall
from agents.document_agent import analyze_document_full
from agents.ethics_agent import review_assessment
from agents.fact_extractor import extract_facts, merge_document_facts, parse_date
from agents.llm_utils import (AI_CONNECT_TIMEOUT_SECONDS, AI_REQUEST_TIMEOUT_SECONDS,
                              AI_RETRY_BASE_DELAY_SECONDS, AI_TEMPORARY_RETRIES,
                              AI_UNAVAILABLE_MESSAGE, invoke_llm)
from agents.recommendation_agent import generate_recommendations
from config import OPENROUTER_API_URL, OPENROUTER_MODEL
from regulation_engine.applicability_checker import check_applicability
from regulation_engine.knowledge_base import get_entries

TODAY = date(2026, 11, 24)
PROFILE = {"company": "T", "industry": "Food Processing", "state": "Telangana",
           "wastewater": "Yes", "air_emissions": "No", "hazardous_waste": "No"}
HAZARDOUS_PROFILE = {**PROFILE, "hazardous_waste": "Yes"}


def assess(text, profile=PROFILE):
    merged = merge_document_facts([("d.pdf", extract_facts("--- Page 1 ---\n" + text, TODAY))])
    app = check_applicability(profile, merged)
    return merged, app, assess_compliance(get_entries(), app, merged)


class FactExtractorTests(unittest.TestCase):
    def test_parse_date_formats(self):
        self.assertEqual(parse_date("31/03/2027"), date(2027, 3, 31))
        self.assertEqual(parse_date("2027-03-31"), date(2027, 3, 31))
        self.assertEqual(parse_date("30 June 2028"), date(2028, 6, 30))
        self.assertEqual(parse_date("June 30, 2028"), date(2028, 6, 30))
        self.assertIsNone(parse_date("31/31/2027"))

    def test_not_provided_detected(self):
        f = extract_facts("Consent to Operate: Not provided")
        self.assertEqual(f["topics"]["consent_to_operate"]["status"], "not_provided")

    def test_present_with_number_and_validity(self):
        f = extract_facts("Consent to Operate granted, Order No. TS/CTO/25/1, valid up to 31/03/2027", TODAY)
        d = f["topics"]["consent_to_operate"]
        self.assertEqual(d["status"], "present")
        self.assertEqual(d["details"]["valid_until"], "2027-03-31")
        self.assertFalse(d["details"]["expired"])

    def test_table_layout_label_then_value(self):
        f = extract_facts("Business Name\nGreenLeaf Unit\nLocation\nWarangal")
        self.assertEqual(f["business_name"], "GreenLeaf Unit")
        self.assertEqual(f["location"], "Warangal")

    def test_empty_text(self):
        f = extract_facts("")
        self.assertTrue(all(v["status"] == "none" for v in f["topics"].values()))

    def test_form_mentions_are_not_documentary_evidence(self):
        f = extract_facts(
            "The rules refer to Form 2, Form 3, Form 4 and Form 10 manifests.")
        for topic in ("hazardous_waste_authorisation", "hazardous_waste_records",
                      "annual_return_form4", "manifest_form10"):
            self.assertEqual(f["topics"][topic]["status"], "mentioned")

    def test_operational_hazardous_waste_data_is_not_a_register(self):
        f = extract_facts("Hazardous waste generated: 25 kg", TODAY)
        self.assertEqual(f["topics"]["hazardous_waste_records"]["status"], "none")

    def test_disclaimers_are_not_documentary_evidence(self):
        phrases = ("Form 2, not an official form",
                   "Form 3 register, demo only",
                   "Form 4, not verified",
                   "Form 10 manifest, not a valid permit")
        for text, topic in zip(phrases, ("hazardous_waste_authorisation",
                                         "hazardous_waste_records",
                                         "annual_return_form4", "manifest_form10")):
            with self.subTest(topic=topic):
                facts = extract_facts(text, TODAY)
                self.assertEqual(facts["topics"][topic]["status"], "disclaimer")

    def test_record_details_extracted_per_form(self):
        text = """Form 2 Hazardous Waste Authorisation
Authorisation No: TS/HW/2026/001
Granted by State Pollution Control Board
Valid up to: 31/03/2027
Hazardous Waste Register Form 3
Date: 15/10/2026
Waste type: used oil
Quantity: 25 kg
Annual Return Form 4
Reporting Period: FY 2025-26
Submitted on: 20/06/2026
Acknowledgement No: ACK/12345
Form 10 Hazardous Waste Manifest
Manifest No: MAN/2026/001
Date: 15/10/2026
Sender: GreenLeaf Foods
Receiver: Authorized Facility
Waste type: used oil
Quantity: 25 kg"""
        facts = extract_facts(text, TODAY)["topics"]
        for topic in ("hazardous_waste_authorisation", "hazardous_waste_records",
                      "annual_return_form4", "manifest_form10"):
            with self.subTest(topic=topic):
                self.assertEqual(facts[topic]["status"], "present")
                self.assertFalse(facts[topic]["details"].get("missing_fields"))

    def test_merge_prefers_more_complete_form_record(self):
        incomplete = extract_facts(
            "Form 10 Hazardous Waste Manifest\nManifest No: MAN/2026/001\nDate: 15/10/2026")
        complete = extract_facts(
            "Form 10 Hazardous Waste Manifest\nManifest No: MAN/2026/002\n"
            "Date: 15/10/2026\nSender: Generator\nReceiver: Facility\n"
            "Waste type: used oil\nQuantity: 25 kg")
        merged = merge_document_facts([("incomplete.pdf", incomplete),
                                       ("complete.pdf", complete)])
        details = merged["topics"]["manifest_form10"]["details"]
        self.assertEqual(details["manifest_number"], "MAN/2026/002")
        self.assertFalse(details["missing_fields"])


class ComplianceTests(unittest.TestCase):
    def status(self, findings, rid):
        return next(f["status"] for f in findings if f["requirement_id"] == rid)

    def test_missing_is_insufficient_not_violation(self):
        _, _, f = assess("Consent to Operate: Not provided")
        self.assertEqual(self.status(f, "WATER_S25_CTO"), "INSUFFICIENT_EVIDENCE")

    def test_valid_expired_partial(self):
        self.assertEqual(self.status(assess("Consent to Operate: No. AB/1234 valid up to 31/03/2027")[2], "WATER_S25_CTO"), "COMPLIANT")
        self.assertEqual(self.status(assess("Consent to Operate: No. AB/1234 valid up to 31/03/2025")[2], "WATER_S25_CTO"), "NON_COMPLIANT")
        self.assertEqual(self.status(assess("Consent to Operate granted, Order No. AB/1234")[2], "WATER_S25_CTO"), "PARTIALLY_COMPLIANT")

    def test_not_applicable_requirements_not_assessed(self):
        _, _, f = assess("nothing")
        self.assertFalse(any(x["requirement_id"].startswith("HWM") for x in f))

    def test_overall_and_recommendations(self):
        _, app, f = assess("Consent to Operate: not obtained")
        overall = summarize_overall(f, app)
        self.assertEqual(overall["status"], "NON_COMPLIANCE_INDICATED")
        recs = generate_recommendations(f, app)
        self.assertEqual(recs[0]["priority"], 1)
        self.assertTrue(all(r["why"] and r["actions"] for r in recs))

    def test_no_findings_overall(self):
        p = {**PROFILE, "wastewater": "No"}
        _, app, f = assess("x", p)
        self.assertEqual(summarize_overall(f, app)["status"], "NO_APPLICABLE_REQUIREMENTS")

    def test_form_mention_and_disclaimer_remain_insufficient(self):
        mention = "Form 10 is referenced in the rules; it is not an uploaded manifest."
        _, _, findings = assess(mention, HAZARDOUS_PROFILE)
        self.assertEqual(self.status(findings, "HWM_R19_MANIFEST"), "INSUFFICIENT_EVIDENCE")
        disclaimer = "Form 10 manifest - demo only; not a valid permit."
        _, _, findings = assess(disclaimer, HAZARDOUS_PROFILE)
        self.assertEqual(self.status(findings, "HWM_R19_MANIFEST"), "INSUFFICIENT_EVIDENCE")
        manifest = next(f for f in findings if f["requirement_id"] == "HWM_R19_MANIFEST")
        self.assertEqual(manifest["evidence_class"], "disclaimer")

    def test_explicit_missing_authorisation_still_requires_review_as_gap(self):
        _, _, findings = assess(
            "Hazardous waste authorisation: not obtained", HAZARDOUS_PROFILE)
        self.assertEqual(self.status(findings, "HWM_R6_AUTHORISATION"), "NON_COMPLIANT")

    def test_incomplete_record_is_partial_not_compliant(self):
        text = """Form 10 Hazardous Waste Manifest
Manifest No: MAN/2026/001
Date: 15/10/2026
Waste type: used oil"""
        _, _, findings = assess(text, HAZARDOUS_PROFILE)
        manifest = next(f for f in findings if f["requirement_id"] == "HWM_R19_MANIFEST")
        self.assertEqual(manifest["status"], "PARTIALLY_COMPLIANT")
        self.assertIn("sender", manifest["missing_information"])
        self.assertIn("receiver", manifest["missing_information"])

    def test_complete_manifest_record_is_compliant(self):
        text = """Form 10 Hazardous Waste Manifest
Manifest No: MAN/2026/001
Date: 15/10/2026
Sender: GreenLeaf Foods
Receiver: Authorized Facility
Waste type: used oil
Quantity: 25 kg"""
        _, _, findings = assess(text, HAZARDOUS_PROFILE)
        self.assertEqual(self.status(findings, "HWM_R19_MANIFEST"), "COMPLIANT")


class EthicsTests(unittest.TestCase):
    def base(self):
        _, app, f = assess("Consent to Operate: Not provided")
        return {"findings": f}

    def test_clean_result_passes(self):
        self.assertTrue(review_assessment(self.base())["passed"])

    def test_unsupported_compliant_is_flagged(self):
        r = self.base()
        r["findings"][0]["status"] = "COMPLIANT"
        self.assertFalse(review_assessment(r)["passed"])

    def test_unsupported_ai_text_is_suppressed_without_changing_findings(self):
        result = self.base()
        original_statuses = [
            (item["status"], item["risk_level"], item["evidence_class"])
            for item in result["findings"]
        ]
        result["ai"] = {
            "narrative": "Section 99 guarantees the business is legally compliant.",
            "interpretations": [
                {"instrument": "Unknown rule", "text": "No further review is needed."},
            ],
        }

        review = review_assessment(result)

        self.assertTrue(review["ai_suppressed"])
        self.assertIsNone(result["ai"]["narrative"])
        self.assertEqual(result["ai"]["interpretations"], [])
        self.assertEqual(
            [(item["status"], item["risk_level"], item["evidence_class"]) for item in result["findings"]],
            original_statuses,
        )


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class OpenRouterTests(unittest.TestCase):
    def test_missing_key_is_graceful(self):
        with patch("agents.llm_utils.OPENROUTER_API_KEY", None), \
                patch("agents.llm_utils.requests.post") as post:
            out = invoke_llm("hello")
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], AI_UNAVAILABLE_MESSAGE)
        post.assert_not_called()

    def test_successful_chat_completion_uses_openrouter_structured_output(self):
        secret = "test-openrouter-key"
        schema = {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }
        response = FakeResponse(200, {
            "choices": [{"message": {"content": '{"answer":"OpenRouter response"}'}}],
        })
        with patch("agents.llm_utils.OPENROUTER_API_KEY", secret), \
                patch("agents.llm_utils.requests.post", return_value=response) as post:
            result = invoke_llm("structured prompt", temperature=0, response_schema=schema)

        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], '{"answer":"OpenRouter response"}')
        args, kwargs = post.call_args
        self.assertEqual(args[0], OPENROUTER_API_URL)
        self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {secret}")
        self.assertEqual(kwargs["json"]["model"], OPENROUTER_MODEL)
        self.assertEqual(kwargs["timeout"], (AI_CONNECT_TIMEOUT_SECONDS, AI_REQUEST_TIMEOUT_SECONDS))
        self.assertEqual(kwargs["json"]["provider"], {"require_parameters": True})
        self.assertEqual(kwargs["json"]["response_format"]["type"], "json_schema")
        self.assertEqual(kwargs["json"]["response_format"]["json_schema"]["schema"], schema)

    def test_invalid_model_is_not_retried_and_error_is_safe(self):
        with patch("agents.llm_utils.OPENROUTER_API_KEY", "test-key"), \
                patch("agents.llm_utils.OPENROUTER_MODEL", "unlisted/model"), \
                patch("agents.llm_utils.requests.post",
                      return_value=FakeResponse(404, {"error": {"message": "No such model"}})) as post, \
                self.assertLogs("agents.llm_utils", level="WARNING") as logs:
            result = invoke_llm("hello")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], AI_UNAVAILABLE_MESSAGE)
        post.assert_called_once()
        self.assertIn("model=unlisted/model", " ".join(logs.output))
        self.assertIn("status=404", " ".join(logs.output))

    def test_rate_limit_retries_once_then_succeeds(self):
        success = FakeResponse(200, {"choices": [{"message": {"content": "Recovered"}}]})
        with patch("agents.llm_utils.OPENROUTER_API_KEY", "test-key"), \
                patch("agents.llm_utils.requests.post", side_effect=[
                    FakeResponse(429, {"error": {"message": "Rate limit exceeded"}}), success,
                ]) as post, \
                patch("agents.llm_utils.time.sleep") as sleep:
            result = invoke_llm("hello")

        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "Recovered")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(AI_RETRY_BASE_DELAY_SECONDS)

    def test_timeout_retries_once_and_hides_provider_details(self):
        secret = "test-openrouter-secret"
        with patch("agents.llm_utils.OPENROUTER_API_KEY", secret), \
                patch("agents.llm_utils.requests.post", side_effect=[
                    requests.Timeout("connect timeout"),
                    requests.Timeout(f"timeout bearer {secret}"),
                ]) as post, \
                patch("agents.llm_utils.time.sleep") as sleep, \
                self.assertLogs("agents.llm_utils", level="WARNING") as logs:
            result = invoke_llm("hello")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], AI_UNAVAILABLE_MESSAGE)
        self.assertEqual(post.call_count, AI_TEMPORARY_RETRIES + 1)
        sleep.assert_called_once_with(AI_RETRY_BASE_DELAY_SECONDS)
        self.assertNotIn(secret, " ".join(logs.output))

    def test_provider_error_retries_once_and_does_not_expose_payload(self):
        secret = "test-openrouter-secret"
        error = FakeResponse(503, {"error": {"message": f"provider issue token={secret}"}})
        with patch("agents.llm_utils.OPENROUTER_API_KEY", secret), \
                patch("agents.llm_utils.requests.post", side_effect=[error, error]) as post, \
                patch("agents.llm_utils.time.sleep") as sleep, \
                self.assertLogs("agents.llm_utils", level="WARNING") as logs:
            result = invoke_llm("hello")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], AI_UNAVAILABLE_MESSAGE)
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(AI_RETRY_BASE_DELAY_SECONDS)
        self.assertIn("status=503", " ".join(logs.output))
        self.assertNotIn(secret, " ".join(logs.output))

    def test_identical_cached_prompt_reuses_openrouter_response(self):
        response = FakeResponse(200, {"choices": [{"message": {"content": "Cached response"}}]})
        prompt = f"unique cached prompt {id(self)}"
        with patch("agents.llm_utils.OPENROUTER_API_KEY", "test-key"), \
                patch("agents.llm_utils.requests.post", return_value=response) as post:
            first = invoke_llm(prompt, cache_result=True)
            second = invoke_llm(prompt, cache_result=True)

        self.assertEqual(first["text"], "Cached response")
        self.assertEqual(second["text"], "Cached response")
        post.assert_called_once()

    def test_combined_assessment_explanations_use_structured_openrouter_response(self):
        response_text = (
            '{"narrative":"Review the evidence gaps.","interpretations":'
            '[{"instrument":"Test regulation","text":"Confirm the listed details."}]}'
        )
        response = FakeResponse(200, {"choices": [{"message": {"content": response_text}}]})
        entry = {
            "id": "R1",
            "instrument": "Test regulation",
            "citation": "Rule 6",
            "title": "Requirement",
            "summary": "Curated summary",
        }
        findings = [{
            "requirement_id": "R1",
            "title": "Requirement",
            "instrument": "Test regulation",
            "status_label": "Insufficient evidence",
            "risk_level": "Medium",
            "evidence_class": "none",
            "explanation": "No evidence was found.",
            "missing_information": ["Record"],
        }]
        applicability = [{
            "requirement_id": "R1",
            "status": "APPLICABLE",
            "reason": "The activity applies.",
        }]
        with patch("agents.llm_utils.OPENROUTER_API_KEY", "test-key"), \
                patch("agents.llm_utils.requests.post", return_value=response) as post:
            result = generate_ai_explanations(
                {"company": "Test"}, findings, {"label": "Evidence incomplete"},
                [entry], applicability,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["narrative"], "Review the evidence gaps.")
        self.assertEqual(result["interpretations"][0]["text"], "Confirm the listed details.")
        request = post.call_args.kwargs["json"]
        self.assertIn("deterministic_findings", request["messages"][0]["content"])
        self.assertEqual(
            request["response_format"]["json_schema"]["schema"]["type"],
            "object",
        )

    def test_document_analysis_hides_provider_errors(self):
        with patch("agents.llm_utils.llm_status",
                   return_value={"available": True, "configured": True, "library_installed": True}), \
                patch("agents.document_agent.analyze_document",
                      side_effect=RuntimeError("raw 503 provider payload")):
            result = analyze_document_full("A test document", use_ai=True)

        self.assertEqual(result["ai_status"], "unavailable")
        self.assertEqual(result["ai_error"], AI_UNAVAILABLE_MESSAGE)
        self.assertNotIn("raw 503 provider payload", result["ai_error"])

if __name__ == "__main__":
    unittest.main()
