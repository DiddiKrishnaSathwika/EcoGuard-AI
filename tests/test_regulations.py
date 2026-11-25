import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import tests.conftest  # noqa: F401
import requests
from rag.local_retriever import BM25Index
from rag.retriever import retrieve_regulations
from rag.text_splitter import split_text_into_chunks
from regulation_engine.amendment_checker import check_amendment_status
from regulation_engine.applicability_checker import check_applicability
from regulation_engine.live_retriever import fetch_source
from regulation_engine import document_ingestor
from regulation_engine.knowledge_base import get_entries, load_knowledge_base, source_status
from regulation_engine import regulation_cache
from regulation_engine.source_registry import validate_sources
from regulation_engine.source_validator import validate_regulation_source
from regulation_engine.regulation_parser import parse_regulation_text
from utils import storage


class KnowledgeBaseTests(unittest.TestCase):
    def test_entries_are_complete_and_sourced(self):
        kb = load_knowledge_base()
        ids = [e["id"] for e in kb["entries"]]
        self.assertEqual(len(ids), len(set(ids)))
        for e in kb["entries"]:
            for key in ("title", "instrument", "citation", "summary", "evidence_topic", "corrective_action", "sources", "verification"):
                self.assertTrue(e.get(key), f"{e['id']} missing {key}")
            self.assertTrue(all(s["url"].startswith("https://") for s in e["sources"]))
            self.assertNotIn("PRIMARY_VERIFIED", e["verification"]["status"])  # never overclaim
        self.assertTrue(kb["coverage_limitations"])

    def test_registry_valid_and_cache_never_treated_as_law(self):
        self.assertTrue(validate_sources()["valid"])
        for s in source_status()["sources"]:
            self.assertFalse(s.get("verified_as_current_law", False))


class ApplicabilityTests(unittest.TestCase):
    P = {"wastewater": "No", "air_emissions": "No", "hazardous_waste": "No"}

    def app(self, **kw):
        return {a["requirement_id"]: a for a in check_applicability({**self.P, **kw})}

    def test_declared_no_not_applicable(self):
        self.assertTrue(all(a["status"] == "NOT_APPLICABLE" for a in self.app().values()))

    def test_declared_yes(self):
        a = self.app(wastewater="Yes", air_emissions="Yes", hazardous_waste="Yes")
        self.assertEqual(a["WATER_S25_CTO"]["status"], "APPLICABLE")
        self.assertEqual(a["AIR_S21_CTO"]["status"], "CONDITIONALLY_APPLICABLE")
        self.assertEqual(a["HWM_R6_AUTHORISATION"]["status"], "APPLICABLE")

    def test_unknown_needs_information(self):
        self.assertEqual(self.app(hazardous_waste="Unknown")["HWM_R6_AUTHORISATION"]["status"], "NEEDS_INFORMATION")

    def test_document_contradiction_flagged(self):
        a = check_applicability(self.P, {"wastewater_reported": True, "air_sources": []})
        self.assertTrue(any(x["discrepancy"] for x in a))


class RetrievalTests(unittest.TestCase):
    def test_bm25_ranks_relevant_first(self):
        idx = BM25Index([("a", "hazardous waste authorisation manifest"), ("b", "wastewater trade effluent consent")])
        self.assertEqual(idx.search("trade effluent discharge", 2)[0][0], "b")

    def test_retrieval_uses_profile(self):
        r = retrieve_regulations({"industry": "Food", "state": "Telangana", "hazardous_waste": "Yes"}, get_entries())
        self.assertTrue(r["results"][0]["requirement_id"].startswith("HWM"))
        self.assertEqual(r["method"], "local_bm25")

    def test_empty_query_safe(self):
        self.assertEqual(len(retrieve_regulations({}, get_entries())["results"]), len(get_entries()))

    @patch("regulation_engine.live_retriever.requests.Session")
    def test_source_fetch_success_keeps_tls_verification_enabled(self, session_factory):
        session = session_factory.return_value.__enter__.return_value
        response = session.get.return_value
        response.status_code = 200
        response.url = "https://example.gov/"
        response.headers = {"Content-Type": "text/html"}
        response.text = "<html><title>Portal</title><body>Page text</body></html>"

        result = fetch_source({
            "source_id": "TEST",
            "authority": "Test authority",
            "url": "https://example.gov/",
        })

        self.assertEqual(result["retrieval_status"], "HTTP_SUCCESS")
        self.assertEqual(result["content"], "Portal Page text")
        self.assertTrue(result["error_type"] is None)
        self.assertTrue(session.get.call_args.kwargs["verify"])
        session.mount.assert_called_once()

    @patch("regulation_engine.live_retriever.requests.Session")
    def test_source_fetch_reports_ssl_verification_failure(self, session_factory):
        session = session_factory.return_value.__enter__.return_value
        session.get.side_effect = requests.exceptions.SSLError("certificate verify failed")

        result = fetch_source({
            "source_id": "TEST",
            "authority": "Test authority",
            "url": "https://example.gov/",
        })

        self.assertEqual(result["error_type"], "SSL_ERROR")
        self.assertIn("TLS certificate verification failed", result["error"])
        self.assertEqual(result["retrieval_status"], "FAILED")

    @patch("regulation_engine.live_retriever.requests.Session")
    def test_source_fetch_reports_connection_timeout(self, session_factory):
        session = session_factory.return_value.__enter__.return_value
        session.get.side_effect = requests.exceptions.Timeout("read timed out")

        result = fetch_source({
            "source_id": "TEST",
            "authority": "Test authority",
            "url": "https://example.gov/",
        })

        self.assertEqual(result["error_type"], "TIMEOUT")
        self.assertIn("timed out", result["error"])

    @patch("regulation_engine.live_retriever.requests.Session")
    def test_source_fetch_reports_connection_failure(self, session_factory):
        session = session_factory.return_value.__enter__.return_value
        session.get.side_effect = requests.exceptions.ConnectionError("network unreachable")

        result = fetch_source({
            "source_id": "TEST",
            "authority": "Test authority",
            "url": "https://example.gov/",
        })

        self.assertEqual(result["error_type"], "CONNECTION_ERROR")
        self.assertIn("Connection failed", result["error"])

    @patch("regulation_engine.live_retriever.requests.Session")
    def test_source_fetch_reports_http_failure(self, session_factory):
        session = session_factory.return_value.__enter__.return_value
        response = session.get.return_value
        response.status_code = 503
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("503 Server Error")

        result = fetch_source({
            "source_id": "TEST",
            "authority": "Test authority",
            "url": "https://example.gov/",
        })

        self.assertEqual(result["error_type"], "HTTP_ERROR")
        self.assertEqual(result["http_status"], 503)
        self.assertIn("HTTP request failed", result["error"])

    @patch("regulation_engine.regulation_cache.retrieve_source_by_id")
    def test_successful_retrieval_remains_unverified_in_cache(self, retrieve):
        retrieve.return_value = {
            "retrieval_status": "HTTP_SUCCESS",
            "source_id": "TEST",
            "authority": "Test authority",
            "url": "https://parivesh.nic.in/portal/",
            "final_url": "https://parivesh.nic.in/portal/",
            "page_title": "Official portal",
            "content": "Environmental portal content",
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(storage, "LOCAL_STORAGE_ROOT", Path(directory)):
                with patch.object(storage, "FILE_STORAGE_BACKEND", "local"):
                    result = regulation_cache.process_and_cache_source("TEST")
                    cached = json.loads(
                        (Path(directory) / "data" / "cached_regulations" / "TEST.json")
                        .read_text(encoding="utf-8")
                    )

        self.assertTrue(result["success"])
        self.assertIn("retrieved_at", cached)
        self.assertEqual(cached["content_classification"], "UNVERIFIED_WEBSITE_CONTENT")
        self.assertFalse(cached["validation"]["verified_as_current_law"])

    @patch("regulation_engine.knowledge_base.get_json")
    def test_source_status_reads_persistent_cache_without_verifying_website_content(self, get_json):
        get_json.return_value = {
            "retrieved_at": "2026-01-01T00:00:00+00:00",
            "validation": {"status": "UNVERIFIED_DOMAIN", "verified_as_current_law": False},
            "content_classification": "UNVERIFIED_WEBSITE_CONTENT",
        }

        status = source_status()

        self.assertTrue(status["sources"][0]["cached"])
        self.assertEqual(
            status["sources"][0]["content_classification"],
            "UNVERIFIED_WEBSITE_CONTENT",
        )
        self.assertFalse(status["sources"][0]["verified_as_current_law"])
        self.assertTrue(
            get_json.call_args_list[0].args[0].startswith("data/cached_regulations/")
        )


class MiscTests(unittest.TestCase):
    @patch("regulation_engine.document_ingestor.parse_regulation_text")
    @patch("regulation_engine.document_ingestor.validate_regulation_source")
    @patch("regulation_engine.document_ingestor.extract_pdf_text")
    def test_document_ingestor_persists_metadata_through_storage(
        self, extract, validate, parse
    ):
        extract.return_value = {
            "success": True,
            "full_text": "Sample regulation text",
            "total_pages": 2,
        }
        validate.return_value = {
            "status": "UNVERIFIED_DOMAIN",
            "verified_as_current_law": False,
        }
        parse.return_value = {
            "total_paragraphs": 1,
            "sections": [],
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_pdf = root / "source.pdf"
            source_pdf.write_bytes(b"mock PDF")
            with patch.object(storage, "LOCAL_STORAGE_ROOT", root):
                with patch.object(storage, "FILE_STORAGE_BACKEND", "local"):
                    result = document_ingestor.ingest_regulation_pdf(
                        source_pdf,
                        "Sample-ID",
                        "Sample regulation",
                        "Test authority",
                        "https://example.gov/regulation.pdf",
                    )
                    cached = json.loads(
                        (
                            root / "data" / "cached_regulations" / "Sample-ID.json"
                        ).read_text(encoding="utf-8")
                    )

        self.assertTrue(result["success"])
        self.assertEqual(cached["verification_status"], "PENDING_MANUAL_VERIFICATION")
        self.assertFalse(cached["verified_as_current_law"])

    def test_amendment_checker_never_claims_checked(self):
        e = get_entries()[0]
        self.assertFalse(check_amendment_status(e, date(2026, 12, 1))["amendments_checked"])
        self.assertTrue(check_amendment_status(e, date(2028, 1, 1))["stale"])

    def test_source_validator_not_current_law(self):
        v = validate_regulation_source("https://cpcb.gov.in/x.pdf", "Water Act text", "Water Act")
        self.assertFalse(v["verified_as_current_law"])
        self.assertEqual(validate_regulation_source("https://evil.example/x.pdf", "x")["status"], "UNVERIFIED_DOMAIN")

    def test_parser_and_splitter(self):
        self.assertEqual(parse_regulation_text("", "s", "u")["status"], "INSUFFICIENT_CONTENT")
        self.assertTrue(parse_regulation_text("Section 25 applies", "s", "u")["sections"])
        self.assertEqual(split_text_into_chunks("   "), [])
        self.assertTrue(split_text_into_chunks("word " * 500, 200, 20))


if __name__ == "__main__":
    unittest.main()
