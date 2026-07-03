"""Normalize tool failures before they are fed back to the model."""

from __future__ import annotations

_HARD_TOOL_ERROR_CLASSES = {
    "network_error",
    "timeout",
    "rate_limited",
    "permission_denied",
    "path_denied",
    "needs_browser",
    "needs_publish",
}
_RECOVERABLE_TOOL_ERROR_CLASSES = {
    "tool_not_found",
    "model_bad_arguments",
    "syntax_error",
}
_EXTERNAL_TOOL_PREFIXES = (
    "web-tools__",
    "browser-tools__",
    "github-search__",
)


def effective_tool_name(tool: dict) -> str:
    name = str(tool.get("name") or "")
    args = tool.get("args") or tool.get("arguments") or {}
    if name != "skill_use" or not isinstance(args, dict):
        return name
    target = args.get("name")
    return str(target or name)


def _explicit_error_class(result: dict) -> str | None:
    for key in ("error_class", "error_type", "code"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = result.get("type")
    if isinstance(value, str) and ("error" in value.lower() or "timeout" in value.lower()):
        return value.strip()
    return None


def _failure_error_text(result: dict, default: str) -> str:
    error = result.get("error")
    if error:
        return str(error)
    message = result.get("message")
    if message:
        return str(message)
    error_class = _explicit_error_class(result)
    if error_class:
        return error_class
    if result.get("timeout") is True:
        return "tool timed out"
    return default


def _extract_tool_failure(result: object) -> tuple[dict, str] | None:
    if not isinstance(result, dict):
        return None

    candidates: list[tuple[dict, str]] = [(result, "result")]
    inner = result.get("data")
    if isinstance(inner, dict):
        candidates.append((inner, "data"))

    for candidate, source in candidates:
        status = candidate.get("status")
        status_failed = isinstance(status, str) and status.lower() in {
            "failed",
            "error",
            "timeout",
        }
        typed_failure = bool(_explicit_error_class(candidate))
        if (
            candidate.get("success") is False
            or bool(candidate.get("error"))
            or candidate.get("timeout") is True
            or status_failed
            or typed_failure
        ):
            return candidate, source
    return None


def _classify_tool_error(result: dict, error: str) -> str:
    explicit = _explicit_error_class(result)
    if explicit:
        return explicit
    try:
        from ..services.tool_guidance_service import classify_error

        return classify_error(result, error)
    except Exception:
        error_lower = error.lower()
        if "timeout" in error_lower or "timed out" in error_lower:
            return "timeout"
        if any(marker in error_lower for marker in ("network", "connection", "dns")):
            return "network_error"
    return "unknown"


def normalize_tool_result_for_model(
    result: object,
    effective_name: str,
) -> tuple[object, dict | None]:
    failure = _extract_tool_failure(result)
    if failure is None:
        return result, None

    failure_payload, source = failure
    error = _failure_error_text(failure_payload, "tool failed")
    error_class = _classify_tool_error(failure_payload, error)
    external_tool = effective_name.startswith(_EXTERNAL_TOOL_PREFIXES)
    recoverable = error_class in _RECOVERABLE_TOOL_ERROR_CLASSES
    hard_failure = (error_class in _HARD_TOOL_ERROR_CLASSES or external_tool) and not recoverable
    failure_kind = "hard" if hard_failure else "recoverable"

    annotated = dict(result) if isinstance(result, dict) else {"result": result}
    if annotated.get("success") is True and source == "data":
        annotated["transport_success"] = True
    annotated["success"] = False
    annotated.setdefault("error", error)
    annotated["error_class"] = error_class
    annotated["failure_kind"] = failure_kind
    annotated["hard_failure"] = hard_failure
    annotated["effective_tool_name"] = effective_name
    annotated["model_instruction"] = (
        "This tool call failed. Do not treat it as successful tool output; "
        "explain the failure or choose a safe alternative."
    )
    annotated["tool_failure"] = {
        "tool_name": effective_name,
        "error": error,
        "error_class": error_class,
        "kind": failure_kind,
        "hard": hard_failure,
        "source": source,
    }
    return annotated, annotated["tool_failure"]
