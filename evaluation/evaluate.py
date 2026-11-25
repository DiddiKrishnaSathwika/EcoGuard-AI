"""Run the evaluation suite against the assessment pipeline (no LLM involved).

    python -m evaluation.evaluate
"""
import json
import sys
from datetime import date

from evaluation.dataset import load_test_cases
from evaluation.evaluators import integrity_checks, status_checks
from workflows.graph import run_assessment


def run_evaluation():
    data = load_test_cases()
    cases_out, total, passed = [], 0, 0
    for case in data["cases"]:
        docs = [{"id": i, "filename": d["filename"], "text": d["text"]} for i, d in enumerate(case.get("documents", []), 1)]
        try:
            result = run_assessment(case["profile"], docs, date.fromisoformat(data["assessment_date"]), use_ai=False)
            checks = status_checks(case, result) + integrity_checks(result)
            error = None
        except Exception as e:  # a crashing case is a failed case, reported honestly
            checks, error = [], f"{type(e).__name__}: {e}"
        ok = sum(c["passed"] for c in checks)
        total += len(checks)
        passed += ok
        cases_out.append({"id": case["id"], "description": case["description"], "checks": checks, "passed_checks": ok,
                          "total_checks": len(checks), "passed": error is None and ok == len(checks), "error": error})
    n_pass = sum(c["passed"] for c in cases_out)
    return {
        "suite": data["suite"], "assessment_date": data["assessment_date"], "note": data["note"],
        "metrics": {"cases": len(cases_out), "cases_passed": n_pass, "checks": total, "checks_passed": passed,
                    "check_pass_rate": round(passed / total, 4) if total else None},
        "cases": cases_out,
        "scope": "Evaluates the deterministic assessment pipeline; no Gemini-generated assessment content is involved.",
    }


if __name__ == "__main__":
    out = run_evaluation()
    print(json.dumps(out["metrics"], indent=2))
    for c in out["cases"]:
        print(("PASS" if c["passed"] else "FAIL"), c["id"], f"{c['passed_checks']}/{c['total_checks']}", c["error"] or "")
    sys.exit(0 if out["metrics"]["cases"] == out["metrics"]["cases_passed"] else 1)
