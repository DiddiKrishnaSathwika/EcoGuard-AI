"""Loads evaluation test cases."""
import json
from pathlib import Path

CASES_FILE = Path(__file__).parent / "test_cases.json"


def load_test_cases(path=CASES_FILE):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "cases" not in data or not data["cases"]:
        raise ValueError("test_cases.json contains no cases.")
    return data
