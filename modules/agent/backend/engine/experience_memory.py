"""engine与 memory 模块之间的成功经验薄客户端。
走框架跨模块通路，不直读 memory 表。"""
import json
import logging
from app.services.module_registry import call_capability

logger = logging.getLogger("v2.agent").getChild("engine.experience_memory")

EXPERIENCE_INJECTION_TEMPLATE = (
    "\n\n💡已知成功路径：当前请求与以下成功经验相似——"
    "\n触发：{trigger}"
    "\n路径：{steps_short}"
    "\n（参考但需结合当前情况验证，不足则正常摸索）"
)


async def save_experience(
    trigger_condition: str,
    steps: str,
    tools_used: str | None = None,
    source_conversation_id: int | None = None,
    caller: str = "system:agent-engine",
) -> dict:
    """保存一条成功经验到 memory 模块。走框架跨模块通路。"""
    try:
        result = await call_capability(
            "memory", "save_experience",
            {
                "trigger_condition": trigger_condition,
                "steps": steps,
                "tools_used": tools_used,
                "source_conversation_id": source_conversation_id,
            },
            caller=caller,
            caller_role="admin",
        )
        return result
    except Exception as e:
        logger.warning("保存经验 failed (non-fatal): %s", e)
        return {"success": False, "error": str(e), "fallback": True}


async def match_experience(
    query: str,
    limit: int = 2,
    caller: str = "system:agent-engine",
) -> list[dict]:
    """语义匹配当前输入相关的成功经验。失败返回空列表。"""
    if not query or not query.strip():
        return []
    try:
        result = await call_capability(
            "memory", "match_experience",
            {"query": query, "limit": limit},
            caller=caller,
            caller_role="admin",
        )
        if result and result.get("success") and result.get("data"):
            return result["data"]
        return []
    except Exception as e:
        logger.warning("匹配经验 failed (non-fatal): %s", e)
        return []


async def experience_feedback(
    experience_id: int,
    success: bool,
    note: str | None = None,
    caller: str = "system:agent-engine",
) -> dict:
    """反馈经验执行结果：成功加权 / 失败降权+注释。"""
    try:
        result = await call_capability(
            "memory", "experience_feedback",
            {
                "experience_id": experience_id,
                "success": success,
                "note": note,
            },
            caller=caller,
            caller_role="admin",
        )
        return result
    except Exception as e:
        logger.warning("经验反馈 failed (non-fatal): %s", e)
        return {"success": False, "error": str(e), "fallback": True}


def format_injection(experiences: list[dict]) -> str | None:
    """将匹配到的经验格式化为提示注入段。无可注入内容时返回 None。"""
    if not experiences:
        return None
    segments = []
    for exp in experiences[:2]:
        trigger = exp.get("trigger_condition", "")
        steps_raw = exp.get("steps", "[]")
        try:
            steps_list = json.loads(steps_raw) if isinstance(steps_raw, str) else steps_raw
        except (json.JSONDecodeError, TypeError):
            steps_list = []
        steps_short = "; ".join(
            f"{s.get('tool_name', s.get('意图', '?'))}" for s in (steps_list or [])[:4]
        ) if steps_list else steps_raw[:120]
        net_weight = exp.get("net_weight", exp.get("success_weight", 1) or 1)
        segments.append(
            f"· 经验（权重{net_weight}）：{trigger[:100]}"
            f"\n  路径：{steps_short[:200]}"
        )
    if not segments:
        return None
    return "\n\n---\n\n💡相关成功经验参考：\n" + "\n".join(segments) + (
        "\n（执行多步流程前，可参考注入的已知成功路径；没有就正常摸索。）"
    )
