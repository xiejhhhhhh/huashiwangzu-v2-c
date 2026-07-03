"""把框架开放的跨模块能力（技能）转成大模型 function calling 工具定义。
Agent 不硬编码任何模块工具——有什么技能就有什么工具。
渐进式工具发现：只暴露 3 个元工具（skill_list/skill_describe/skill_use），
模型需先查再调，默认 token 恒定不随模块膨胀。"""
import logging
import re
import time

from app.services.module_registry import call_capability, list_capabilities

# 工具名用 module__action（function name 不能含冒号）
SEP = "__"
logger = logging.getLogger("v2.agent").getChild("services.tool_discovery")


def build_tools(role: str) -> list[dict]:
    """渐进式工具发现：只返回 3 个元工具，各模块能力通过 skill_list 按需查询。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "skill_list",
                "description": "查看当前角色可用的全部技能。返回 display_name（给用户看的中文名）和 name（skill_use 调用用的英文内部名）。向用户展示技能列表时优先展示 display_name，不要把 name 当作用户可见名称。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "可选分类过滤（如 image-gen / office-gen / knowledge / web-tools 等）",
                            "default": "",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "skill_describe",
                "description": "查看某个技能的完整描述和参数",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "技能内部调用名（如 image-gen__generate），见 skill_list 返回的 name；展示给用户时用 display_name",
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "skill_use",
                "description": "调用一个技能执行任务",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "技能内部调用名（如 image-gen__generate），必须使用 skill_list 返回的 name",
                        },
                        "args": {
                            "type": "object",
                            "description": "技能参数，见 skill_describe 返回的 parameters",
                        },
                    },
                    "required": ["name", "args"],
                },
            },
        },
    ]


def parse_tool_name(name: str) -> tuple[str, str]:
    """module__action -> (module, action).  Uses rpartition so module
    names containing '__' still parse correctly."""
    module, sep, action = name.rpartition(SEP)
    if not sep:
        return name, ""
    return module, action


def _display_name(cap: dict) -> str:
    return cap.get("brief") or cap.get("description", "")[:20] or f"{cap.get('module', '')}{SEP}{cap.get('action', '')}"


async def handle_skill_list(params: dict, role: str) -> dict:
    """返回当前角色可用能力的紧凑清单（display_name + name + brief）。"""
    category = (params.get("category") or "").strip().lower()
    caps = list_capabilities(role=role)
    items = []
    for cap in caps:
        if category and cap["module"].lower() != category and f"{cap['module']}__{cap['action']}" != category:
            continue
        name = f"{cap['module']}{SEP}{cap['action']}"
        display_name = _display_name(cap)
        items.append({"display_name": display_name, "name": name, "brief": display_name})
    return {"skills": items, "total": len(items)}


async def handle_skill_describe(
    params: dict,
    role: str,
    owner_id: int | None = None,
    agent_code: str = "default",
) -> dict:
    """返回指定能力的完整描述、参数 schema 和匹配的工具指引。"""
    name = params.get("name", "")
    module, action = parse_tool_name(name)
    if not module or not action:
        return {"error": f"Invalid skill name: {name}"}
    caps = list_capabilities(role=role)
    for cap in caps:
        if cap["module"] == module and cap["action"] == action:
            result = {
                "name": f"{module}{SEP}{action}",
                "display_name": _display_name(cap),
                "module": module,
                "action": action,
                "description": cap.get("description", ""),
                "parameters": cap.get("parameters", {}),
                "min_role": cap.get("min_role", "viewer"),
            }
            if owner_id is not None:
                try:
                    from app.database import AsyncSessionLocal

                    from . import tool_guidance_service as tgs

                    async with AsyncSessionLocal() as db:
                        guidance = await tgs.render_tool_guidance(
                            db,
                            owner_id=owner_id,
                            agent_code=agent_code,
                            tool_names=[f"{module}{SEP}{action}"],
                            max_tokens=512,
                        )
                    if guidance:
                        result["tool_guidance"] = guidance
                except Exception:
                    pass
            return result
    return {"error": f"Skill not found: {name}"}


async def handle_skill_use(params: dict, caller: str, caller_role: str) -> dict:
    """通用调度器：拆 name 为 module/action，走 call_capability。

    特殊处理 content:write_ir — 调用前先 validate，失败后自动 LLM 修正最多 3 次。

    容错：模型常把 args 传成 JSON 字符串，先处理再透传。
    """
    name = params.get("name", "")
    args = params.get("args", {})
    if isinstance(args, str):
        import json
        try:
            args = json.loads(args) if args.strip() else {}
        except Exception:
            args = {}
    if not isinstance(args, dict):
        args = {}
    module, action = parse_tool_name(name)
    if not module or not action:
        return {"error": f"Invalid skill name: {name}"}

    started = time.perf_counter()
    # Content IR validate + correct loop
    if module == "content" and action == "write_ir" and args.get("content_ir"):
        try:
            result = await _handle_write_ir_with_correction(args, caller, caller_role)
            await record_skill_invocation(
                name,
                success=_skill_result_succeeded(result),
                duration_ms=(time.perf_counter() - started) * 1000,
                caller=caller,
                error_detail=_skill_result_error(result),
            )
            return result
        except Exception as exc:
            await record_skill_invocation(
                name,
                success=False,
                duration_ms=(time.perf_counter() - started) * 1000,
                caller=caller,
                error_detail=str(exc),
            )
            return {"error": str(exc)}

    try:
        result = await call_capability(module, action, args, caller=caller, caller_role=caller_role)
        await record_skill_invocation(
            name,
            success=_skill_result_succeeded(result),
            duration_ms=(time.perf_counter() - started) * 1000,
            caller=caller,
            error_detail=_skill_result_error(result),
        )
        return result
    except Exception as exc:
        await record_skill_invocation(
            name,
            success=False,
            duration_ms=(time.perf_counter() - started) * 1000,
            caller=caller,
            error_detail=str(exc),
        )
        return {"error": str(exc)}


def _skill_result_succeeded(result: object) -> bool:
    if not isinstance(result, dict):
        return True
    if result.get("success") is False:
        return False
    return not bool(result.get("error"))


def _skill_result_error(result: object) -> str | None:
    if not isinstance(result, dict):
        return None
    if result.get("success") is False:
        return str(result.get("error") or "capability returned success=false")
    if result.get("error"):
        return str(result["error"])
    return None


def _parse_owner_id(caller: str) -> int | None:
    match = re.search(r"\buser:(\d+)\b", caller or "")
    if not match:
        return None
    return int(match.group(1))


async def record_skill_invocation(
    skill_name: str,
    *,
    success: bool,
    duration_ms: float,
    caller: str,
    conversation_id: int | None = None,
    owner_id: int | None = None,
    error_detail: str | None = None,
) -> None:
    """Persist skill usage without letting governance telemetry affect the flow."""
    try:
        from app.database import AsyncSessionLocal

        from . import skill_governance_service as sgs

        async with AsyncSessionLocal() as db:
            await sgs.record_skill_usage(
                db,
                skill_name=skill_name,
                success=success,
                duration_ms=duration_ms,
                conversation_id=conversation_id,
                owner_id=owner_id if owner_id is not None else _parse_owner_id(caller),
                error_detail=error_detail,
            )
    except Exception as exc:
        logger.warning("record_skill_invocation failed (non-fatal): %s", exc)


async def _handle_write_ir_with_correction(args: dict, caller: str, caller_role: str) -> dict:
    """Handle content:write_ir with validate -> correct -> write pipeline."""
    import logging

    from ..services.content_ir_correction import validate_and_correct

    logger = logging.getLogger("v2.agent").getChild("write_ir_correction")

    content_ir = args.get("content_ir", {})
    file_id = args.get("file_id")
    expected_version_id = args.get("expected_version_id")

    # Step 1: Validate
    validation = await call_capability(
        "content", "validate_ir",
        {"content_ir": content_ir},
        caller=caller, caller_role=caller_role,
    )
    inner = validation.get("data", validation) if isinstance(validation, dict) else {}
    errors = inner.get("errors", []) if isinstance(inner, dict) else []

    if errors:
        logger.info("Content IR validation failed, starting correction loop (%d errors)", len(errors))
        # Try to extract conversation_id from caller
        import re
        conv_match = re.search(r"agent_engine:(\d+)", caller)
        conv_id = int(conv_match.group(1)) if conv_match else 0

        correction_result = await validate_and_correct(
            content_ir,
            conversation_id=conv_id,
            profile_key="deepseek-v4-flash",
        )
        if not correction_result["success"]:
            return {
                "error": f"Content IR validation failed after {correction_result['retry_count']} correction attempts",
                "validation_errors": correction_result["errors"],
            }
        content_ir = correction_result["content_ir"]
        logger.info("Content IR corrected after %d retries", correction_result["retry_count"])

    # Step 2: Write
    try:
        write_args = {"content_ir": content_ir}
        if file_id:
            write_args["file_id"] = file_id
        if expected_version_id:
            write_args["expected_version_id"] = expected_version_id

        result = await call_capability(
            "content", "write_ir", write_args,
            caller=caller, caller_role=caller_role,
        )
        return result
    except Exception as exc:
        return {"error": str(exc)}
