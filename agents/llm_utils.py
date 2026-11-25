"""Safe OpenRouter chat completions with bounded retries and response caching."""
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
import hashlib
import json
import logging
import re
import threading
import time

import requests

from config import OPENROUTER_API_KEY, OPENROUTER_API_URL, OPENROUTER_MODEL

AI_CONNECT_TIMEOUT_SECONDS = 5
AI_REQUEST_TIMEOUT_SECONDS = 20
AI_TEMPORARY_RETRIES = 1
AI_RETRY_BASE_DELAY_SECONDS = 0.5
AI_UNAVAILABLE_MESSAGE = (
    "AI-generated explanations are temporarily unavailable. "
    "Your rule-based assessment and findings are still available."
)
AI_RESPONSE_CACHE_TTL_SECONDS = 600
AI_RESPONSE_CACHE_MAX_ENTRIES = 128
AI_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

logger = logging.getLogger(__name__)
_AI_RESPONSE_CACHE = {}
_AI_IN_FLIGHT = {}
_AI_CACHE_LOCK = threading.Lock()


def _safe_provider_message(message):
    message = str(message or "")
    if OPENROUTER_API_KEY:
        message = message.replace(OPENROUTER_API_KEY, "[REDACTED]")
    message = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", message)
    message = re.sub(
        r"(?i)(authorization|api[_-]?key|token)([\"']?\s*[:=]\s*[\"']?)[^,\s&;\"'}]+",
        r"\1\2[REDACTED]",
        message,
    )
    return " ".join(message.split())[:600]


def _provider_error(response):
    try:
        payload = response.json()
    except ValueError:
        return "Provider returned an unreadable error response."
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return _safe_provider_message(error.get("message") or error.get("code"))
    if isinstance(error, str):
        return _safe_provider_message(error)
    return "Provider returned an error without a message."


def _log_request_failure(status_code, attempt, error):
    logger.warning(
        "OpenRouter chat completion failed (endpoint=%s, model=%s, status=%s, attempt=%s, error=%s)",
        OPENROUTER_API_URL,
        OPENROUTER_MODEL,
        status_code or "unknown",
        attempt,
        _safe_provider_message(error),
    )


def _chat_content(payload):
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("OpenRouter response did not contain a completion choice.")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    if not isinstance(content, str) or not content.strip():
        raise ValueError("OpenRouter response contained no text.")
    return content


def llm_status():
    configured = bool(OPENROUTER_API_KEY)
    return {
        "configured": configured,
        "library_installed": True,
        "available": configured,
        "model": OPENROUTER_MODEL,
    }


def _request_payload(prompt, temperature, response_schema):
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 1800,
        "stream": False,
    }
    if response_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "ecoguard_assessment_explanations",
                "strict": True,
                "schema": response_schema,
            },
        }
        payload["provider"] = {"require_parameters": True}
    return payload


def _invoke_uncached(prompt, temperature, response_schema):
    if not OPENROUTER_API_KEY:
        return {"ok": False, "text": "", "error": AI_UNAVAILABLE_MESSAGE}

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = _request_payload(prompt, temperature, response_schema)
    for attempt in range(AI_TEMPORARY_RETRIES + 1):
        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=(AI_CONNECT_TIMEOUT_SECONDS, AI_REQUEST_TIMEOUT_SECONDS),
            )
        except requests.exceptions.RequestException as error:
            _log_request_failure(None, attempt + 1, f"{type(error).__name__}: {error}")
            if attempt < AI_TEMPORARY_RETRIES:
                time.sleep(AI_RETRY_BASE_DELAY_SECONDS * (2 ** attempt))
                continue
            return {"ok": False, "text": "", "error": AI_UNAVAILABLE_MESSAGE}

        if response.status_code >= 400:
            error = _provider_error(response)
            _log_request_failure(response.status_code, attempt + 1, error)
            if response.status_code in AI_RETRYABLE_STATUS_CODES and attempt < AI_TEMPORARY_RETRIES:
                time.sleep(AI_RETRY_BASE_DELAY_SECONDS * (2 ** attempt))
                continue
            return {"ok": False, "text": "", "error": AI_UNAVAILABLE_MESSAGE}

        try:
            text = _chat_content(response.json())
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            _log_request_failure(response.status_code, attempt + 1, error)
            return {"ok": False, "text": "", "error": AI_UNAVAILABLE_MESSAGE}
        return {"ok": True, "text": text, "error": None}

    return {"ok": False, "text": "", "error": AI_UNAVAILABLE_MESSAGE}


def _response_cache_key(prompt, temperature, response_schema):
    payload = json.dumps(
        [OPENROUTER_MODEL, temperature, response_schema, prompt],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def invoke_llm(prompt, temperature=0.1, response_schema=None, cache_result=False):
    if not llm_status()["configured"]:
        return {"ok": False, "text": "", "error": AI_UNAVAILABLE_MESSAGE}
    if not cache_result:
        return _invoke_uncached(prompt, temperature, response_schema)

    cache_key = _response_cache_key(prompt, temperature, response_schema)
    now = time.monotonic()
    with _AI_CACHE_LOCK:
        cached = _AI_RESPONSE_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return dict(cached[1])
        if cached:
            del _AI_RESPONSE_CACHE[cache_key]
        future = _AI_IN_FLIGHT.get(cache_key)
        owner = future is None
        if owner:
            future = Future()
            _AI_IN_FLIGHT[cache_key] = future

    if not owner:
        wait_seconds = (
            (AI_CONNECT_TIMEOUT_SECONDS + AI_REQUEST_TIMEOUT_SECONDS) * (AI_TEMPORARY_RETRIES + 1)
            + AI_RETRY_BASE_DELAY_SECONDS * ((2 ** AI_TEMPORARY_RETRIES) - 1)
            + 5
        )
        try:
            return dict(future.result(timeout=wait_seconds))
        except FutureTimeoutError:
            return {"ok": False, "text": "", "error": AI_UNAVAILABLE_MESSAGE}

    result = _invoke_uncached(prompt, temperature, response_schema)
    with _AI_CACHE_LOCK:
        if result["ok"]:
            _AI_RESPONSE_CACHE[cache_key] = (
                time.monotonic() + AI_RESPONSE_CACHE_TTL_SECONDS,
                dict(result),
            )
            if len(_AI_RESPONSE_CACHE) > AI_RESPONSE_CACHE_MAX_ENTRIES:
                oldest = min(_AI_RESPONSE_CACHE, key=lambda key: _AI_RESPONSE_CACHE[key][0])
                del _AI_RESPONSE_CACHE[oldest]
        _AI_IN_FLIGHT.pop(cache_key, None)
        future.set_result(dict(result))
    return result
