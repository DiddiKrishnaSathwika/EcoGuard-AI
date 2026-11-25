import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import tests.conftest  # noqa: F401
from utils import storage


class BlobNotFoundError(Exception):
    pass


class FakeBlobClient:
    def __init__(self):
        self.objects = {}

    def put_blob(self, key, content, **kwargs):
        self.objects[key] = content
        self.last_put = (key, kwargs)
        return SimpleNamespace(pathname=key)

    def get_blob(self, key, **kwargs):
        if key not in self.objects:
            raise BlobNotFoundError(key)
        self.last_get = (key, kwargs)
        return SimpleNamespace(body=self.objects[key])


class StorageTests(unittest.TestCase):
    def test_local_json_round_trip_and_missing_object(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(storage, "LOCAL_STORAGE_ROOT", Path(directory)):
                with patch.object(storage, "FILE_STORAGE_BACKEND", "local"):
                    key = "data/cached_regulations/TEST.json"
                    record = {"content_classification": "UNVERIFIED_WEBSITE_CONTENT"}
                    stored_path = storage.put_json(key, record)

                    self.assertEqual(
                        Path(stored_path),
                        Path(directory) / "data" / "cached_regulations" / "TEST.json",
                    )
                    self.assertEqual(storage.get_json(key), record)
                    self.assertIsNone(storage.get_json("reports/missing.pdf"))

    def test_blob_round_trip_is_private_and_never_writes_local_files(self):
        client = FakeBlobClient()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(storage, "LOCAL_STORAGE_ROOT", Path(directory)):
                with patch.object(storage, "FILE_STORAGE_BACKEND", "vercel_blob"):
                    with patch.object(storage, "IS_VERCEL_RUNTIME", True):
                        with patch.object(
                            storage,
                            "_blob_client",
                            return_value=(client, BlobNotFoundError),
                        ):
                            key = "reports/EcoGuard_Report_42.pdf"
                            self.assertEqual(
                                storage.put_bytes(key, b"%PDF", "application/pdf"),
                                key,
                            )
                            self.assertEqual(storage.get_bytes(key), b"%PDF")
                            self.assertEqual(client.last_put[1]["access"], "private")
                            self.assertEqual(client.last_get[1]["access"], "private")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_blob_failure_does_not_fall_back_to_local(self):
        client = FakeBlobClient()

        def fail_upload(*args, **kwargs):
            raise RuntimeError("Blob unavailable")

        client.put_blob = fail_upload
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(storage, "LOCAL_STORAGE_ROOT", Path(directory)):
                with patch.object(storage, "FILE_STORAGE_BACKEND", "vercel_blob"):
                    with patch.object(storage, "IS_VERCEL_RUNTIME", True):
                        with patch.object(
                            storage,
                            "_blob_client",
                            return_value=(client, BlobNotFoundError),
                        ):
                            with self.assertRaisesRegex(RuntimeError, "Blob unavailable"):
                                storage.put_bytes("reports/report.pdf", b"%PDF")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_vercel_rejects_local_storage_backend(self):
        with patch.object(storage, "FILE_STORAGE_BACKEND", "local"):
            with patch.object(storage, "IS_VERCEL_RUNTIME", True):
                with self.assertRaises(storage.StorageConfigurationError):
                    storage.put_bytes("reports/report.pdf", b"%PDF")

    def test_rejects_unsafe_storage_keys(self):
        with patch.object(storage, "FILE_STORAGE_BACKEND", "local"):
            for key in ("../outside", r"reports\report.pdf", "/absolute/path"):
                with self.subTest(key=key):
                    with self.assertRaises(ValueError):
                        storage.put_bytes(key, b"x")


if __name__ == "__main__":
    unittest.main()
