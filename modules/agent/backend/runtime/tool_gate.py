"""ToolGate — tool call validation and retry contract.

Ensures that every tool call from the model refers to a registered tool.
Invalid tool names are intercepted and the model is asked to retry with
a valid tool rather than exhausting tool rounds on failed executions.

This addresses the root cause of "tool rounds depleted with zero valid
calls" which forced fallback summaries that produced XML-only output.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("v2.agent").getChild("runtime.tool_gate")


def _load_registered_tool_names(role: str) -> set[str]:
    """Load registered module__action names available to the current role."""
    try:
        from app.services.module_registry import list_capabilities

        from ..services.tool_discovery import SEP

        return {
            f"{cap['module']}{SEP}{cap['action']}"
            for cap in list_capabilities(role=role)
            if cap.get("module") and cap.get("action")
        }
    except Exception as exc:
        logger.warning("[ToolGate] failed to load registered tool names: %s", exc)
        return set()


RETRY_MESSAGE = (
    "The previous tool call used an unregistered or invalid tool name. "
    "Use only tools from the provided tool list. If you need to search, "
    "use 'skill_use' with the correct internal skill name. "
    "Regenerate the tool call now with a valid name. "
    "Do not write tool calls as XML text."
)


def validate_tool_calls(
    parsed_tools: list[dict],
    tools_spec: list[dict],
    registered_tool_names: set[str] | None = None,
    role: str = "viewer",
) -> tuple[list[dict], list[str]]:
    """Validate parsed tool calls against exposed tools and registered skills.

    Returns:
        (valid_calls, invalid_names)
    """
    valid: list[dict] = []
    invalid_names: list[str] = []

    # Build lookup: exposed meta tools plus registered module__action skills.
    valid_tool_names: set[str] = set()
    for spec in tools_spec or []:
        fn = spec.get("function") or spec
        name = fn.get("name", "")
        if name:
            valid_tool_names.add(name)
    if registered_tool_names is None:
        registered_tool_names = _load_registered_tool_names(role)
    valid_tool_names.update(registered_tool_names)

    for tool in parsed_tools:
        name = tool.get("name", "")
        if name == "skill_use":
            # skill_use is always valid; the inner skill name is resolved later
            valid.append(tool)
        elif name in valid_tool_names:
            valid.append(tool)
        else:
            invalid_names.append(name)
            logger.warning(
                "[ToolGate] rejected unregistered tool call: %s",
                name,
            )

    return valid, invalid_names


def format_retry_message(invalid_names: list[str]) -> str:
    """Format a retry message for the model listing the invalid tools."""
    names = "\n".join(f"  - {n}" for n in invalid_names)
    return (
        f"The following tool names are not registered:\n{names}\n\n"
        f"{RETRY_MESSAGE}"
    )
