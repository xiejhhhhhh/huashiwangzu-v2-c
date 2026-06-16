import json
import re

from app.database import AsyncSessionLocal
from app.services.agent.tools.registry import ToolResult, tool_registry

MAX_TOOL_ROUNDS = 5
TOOL_CALL_RE = re.compile(
    r'\{\s*(?:"name"|"function")\s*:\s*"[^"]+".*?"arguments"\s*:\s*\{[^}]*\}\s*\}',
    re.DOTALL,
)


def parse_text_tool_calls(text: str) -> list[dict]:
    calls: list[dict] = []
    for item in TOOL_CALL_RE.findall(text):
        try:
            data = json.loads(item)
        except json.JSONDecodeError:
            continue
        name = data.get("name") or data.get("function", "")
        args = data.get("arguments", {})
        if name:
            calls.append({"function": {"name": name, "arguments": args}})
    return calls


def strip_text_tool_calls(text: str) -> str:
    return TOOL_CALL_RE.sub("", text).strip()


def build_tool_specs() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": item["name"],
                "description": item["description"],
                "parameters": item["parameters"],
            },
        }
        for item in tool_registry.list_tools()
    ]


def normalize_tool_call(call: dict) -> tuple[str, dict]:
    fn = call.get("function", {})
    name = fn.get("name", "") or call.get("tool", "")
    args = fn.get("arguments", {}) or call.get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    return name, args if isinstance(args, dict) else {}


def build_assistant_tool_calls(tool_calls: list[dict]) -> list[dict]:
    calls = []
    for call in tool_calls:
        name, args = normalize_tool_call(call)
        calls.append({"type": "function", "function": {"name": name, "arguments": args}})
    return calls


def make_result_summary(tool_name: str, result: ToolResult) -> str:
    if not result.success:
        return f"Error: {result.error}"
    if tool_name == "search_knowledge" and isinstance(result.data, dict):
        items = result.data.get("items", [])
        ids = [str(item.get("fusion_id", "")) for item in items if item.get("fusion_id")]
        return f"命中{len(items)}条，fusion_id=[{','.join(ids)}]"
    if isinstance(result.data, dict):
        return f"返回{len(result.data)}个字段"
    return "OK"


async def execute_tool_calls(
    user_id: int,
    tool_calls: list[dict],
    context: list[dict],
) -> list[dict]:
    audited: list[dict] = []
    for call in tool_calls:
        name, args = normalize_tool_call(call)
        if not name:
            continue
        async with AsyncSessionLocal() as tool_db:
            result = await tool_registry.call_tool(tool_db, user_id, name, **args)
        audited.append({
            "name": name,
            "arguments": args,
            "result_summary": make_result_summary(name, result),
        })
        content = json.dumps(result.data, ensure_ascii=False)[:3000] if result.success else f"Error: {result.error}"
        context.append({"role": "tool", "content": content})
    return audited
