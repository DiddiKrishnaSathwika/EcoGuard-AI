"""Make a small authenticated request to the configured OpenRouter model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.llm_utils import invoke_llm, llm_status


def main():
    status = llm_status()
    if not status["configured"]:
        print("OPENROUTER_API_KEY is not configured.")
        return 1

    print(f"Testing OpenRouter chat completions with model {status['model']}.")
    response = invoke_llm(
        "Reply with exactly: OpenRouter connectivity successful.",
        temperature=0,
        cache_result=False,
    )
    if not response["ok"]:
        print("OpenRouter connectivity test failed; inspect backend logs for safe diagnostics.")
        return 1

    print("OpenRouter returned a real response:")
    print(response["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
