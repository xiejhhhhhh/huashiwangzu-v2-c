import asyncio
import logging
import random
import re
from typing import Any

logger = logging.getLogger("v2.gateway.error_classifier")

_AUTH_BODY_KW = ["invalid_api_key", "unauthorized", "forbidden", "authentication", "auth"]
_QUOTA_BODY_KW = ["insufficient_quota", "billing", "quota_exceeded", "exceeded your", "payment_required"]
_RATE_LIMIT_BODY_KW = ["rate_limit", "rate limit", "too_many_requests"]
_PROTOCOL_BODY_KW = [
    "invalid_request_error",
    "bad request",
    "tool_calls must be followed",
    "tool messages responding to each",
    "insufficient tool messages",
    "messages malformed",
    "orphan tool message",
    "missing matching tool results",
    "tool_call_id",
]


class ErrorClassification:
    def __init__(self, category: str, retryable: bool, retry_after: float | None = None, message: str = ""):
        self.category = category
        self.retryable = retryable
        self.retry_after = retry_after
        self.message = message

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "retryable": self.retryable,
            "retry_after": self.retry_after,
            "message": self.message,
        }


def _extract_retry_after(body: Any) -> float | None:
    if not body:
        return None
    body_str = str(body) if not isinstance(body, str) else body
    m = re.search(r'"retry_after"\s*:\s*(\d+(?:\.\d+)?)', body_str, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m = re.search(r'retry-after[^0-9]+(\d+)', body_str, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


def _get_status_code(exception: Exception) -> int | None:
    response = getattr(exception, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    status = getattr(exception, "status_code", None) or getattr(exception, "status", None)
    return status if isinstance(status, int) else None


def _get_response_body(exception: Exception) -> str | None:
    response = getattr(exception, "response", None)
    if response is None:
        return None
    try:
        return getattr(response, "text", None) or str(response)
    except Exception:
        return None


def classify_error(
    status_code: int | None = None,
    body: str | None = None,
    exception: Exception | None = None,
) -> ErrorClassification:
    if exception is not None:
        if status_code is None:
            status_code = _get_status_code(exception)
        if body is None:
            body = _get_response_body(exception)

    body_lower = body.lower() if body else ""
    if exception is not None:
        body_lower = f"{body_lower}\n{exception}".lower()

    if any(kw in body_lower for kw in _PROTOCOL_BODY_KW):
        return ErrorClassification("protocol", False, message="Invalid model request payload")

    if status_code == 429:
        retry_after = _extract_retry_after(body)
        return ErrorClassification("rate_limit", True, retry_after, "Rate limited")

    if status_code in (401, 403):
        return ErrorClassification("auth", False, message="Authentication failed, check API key")

    if status_code == 402:
        return ErrorClassification("quota", False, message="Quota exhausted")
    if status_code == 400 and any(kw in body_lower for kw in _QUOTA_BODY_KW):
        return ErrorClassification("quota", False, message="Quota exhausted")
    if status_code == 400:
        return ErrorClassification("protocol", False, message="Invalid model request payload")

    if status_code and 500 <= status_code < 600:
        return ErrorClassification("server", True, message=f"Server error {status_code}")

    if exception is not None:
        if isinstance(exception, asyncio.TimeoutError):
            return ErrorClassification("timeout", True, message="Request timed out")
        exc_name = type(exception).__name__
        if "Timeout" in exc_name:
            return ErrorClassification("timeout", True, message=str(exception))

    if exception is not None and isinstance(exception, ConnectionError):
        return ErrorClassification("server", True, message="Connection error")

    if body:
        if any(kw in body_lower for kw in _AUTH_BODY_KW):
            return ErrorClassification("auth", False, message="Authentication error detected in response")
        if any(kw in body_lower for kw in _QUOTA_BODY_KW):
            return ErrorClassification("quota", False, message="Quota exceeded")
        if any(kw in body_lower for kw in _RATE_LIMIT_BODY_KW):
            retry_after = _extract_retry_after(body)
            return ErrorClassification("rate_limit", True, retry_after, "Rate limit detected in response")
        if any(kw in body_lower for kw in _PROTOCOL_BODY_KW):
            return ErrorClassification("protocol", False, message="Invalid model request payload")

    return ErrorClassification("unknown", True, message="Unknown error, retry once")


def compute_delay(
    classification: ErrorClassification,
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> float:
    if classification.retry_after is not None:
        delay = classification.retry_after
    else:
        delay = base_delay * (2 ** attempt)
    delay = min(delay, max_delay)
    jitter = random.uniform(-delay * 0.25, delay * 0.25) if delay > 0 else 0
    return max(0.1, delay + jitter)


def max_attempts_for_category(category: str, default_max: int = 3) -> int:
    mapping = {
        "auth": 1,
        "quota": 1,
        "rate_limit": default_max,
        "timeout": default_max,
        "server": default_max,
        "unknown": 2,
    }
    return mapping.get(category, 1)
