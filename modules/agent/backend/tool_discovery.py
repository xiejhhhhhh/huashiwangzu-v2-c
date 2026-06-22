"""把框架开放的跨模块能力（技能）转成大模型 function calling 工具定义。
Agent 不硬编码任何模块工具——有什么技能就有什么工具。
渐进式工具发现：只暴露 3 个元工具（skill_list/skill_describe/skill_use），
模型需先查再调，默认 token 恒定不随模块膨胀。"""
from app.services.module_registry import list_capabilities, call_capability

# 工具名用 module__action（function name 不能含冒号）
SEP = "__"


def build_tools(role: str) -> list[dict]:
    """渐进式工具发现：只返回 3 个元工具，各模块能力通过 skill_list 按需查询。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "skill_list",
                "description": "查看当前角色可用的全部技能（名称+一句话简述）",
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
                            "description": "技能名称（如 image-gen__generate），见 skill_list 返回的 name",
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
                            "description": "技能名称（如 image-gen__generate）",
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


async def handle_skill_list(params: dict, role: str) -> dict:
    """返回当前角色可用能力的紧凑清单（name + brief）。"""
    category = (params.get("category") or "").strip().lower()
    caps = list_capabilities(role=role)
    items = []
    for cap in caps:
        if category and cap["module"].lower() != category and f"{cap['module']}__{cap['action']}" != category:
            continue
        name = f"{cap['module']}{SEP}{cap['action']}"
        brief = cap.get("brief") or cap.get("description", "")[:20]
        items.append({"name": name, "brief": brief})
    return {"skills": items, "total": len(items)}


async def handle_skill_describe(params: dict, role: str) -> dict:
    """返回指定能力的完整描述和参数 schema。"""
    name = params.get("name", "")
    module, action = parse_tool_name(name)
    if not module or not action:
        return {"error": f"Invalid skill name: {name}"}
    caps = list_capabilities(role=role)
    for cap in caps:
        if cap["module"] == module and cap["action"] == action:
            return {
                "name": f"{module}{SEP}{action}",
                "module": module,
                "action": action,
                "description": cap.get("description", ""),
                "parameters": cap.get("parameters", {}),
                "min_role": cap.get("min_role", "viewer"),
            }
    return {"error": f"Skill not found: {name}"}


async def handle_skill_use(params: dict, caller: str, caller_role: str) -> dict:
    """通用调度器：拆 name 为 module/action，走 call_capability。

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
    try:
        return await call_capability(module, action, args, caller=caller, caller_role=caller_role)
    except Exception as exc:
        return {"error": str(exc)}
