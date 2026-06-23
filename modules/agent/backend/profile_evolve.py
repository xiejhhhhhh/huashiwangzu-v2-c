"""Profile evolution handler — background task for auto-evolving user profiles.

Registered as a task handler via `register_task_handler("profile_evolve", ...)`.
Consumed by the framework worker: analyzes recent user conversations using
the LLM gateway to extract/update tone, taboos, focus areas, and habits.
"""
import json
import logging
from app.database import AsyncSessionLocal
from app.gateway.router import gateway_router

logger = logging.getLogger("v2.agent").getChild("profile_evolve")

# 用于分析画像的 system prompt
ANALYSIS_SYSTEM_PROMPT = (
    "你是一个用户行为分析助手。分析以下对话历史，提取该用户的个人沟通特征。\n\n"
    "请以 JSON 格式输出，包含以下字段：\n"
    "{\n"
    '  "tone": "用户偏好的语气风格描述（如简洁、详细、正式、随意等）",\n'
    '  "taboos": ["用户不愿意谈或不喜欢的主题列表"],\n'
    '  "focus": ["用户经常关注或询问的领域列表"],\n'
    '  "habits": ["用户的沟通习惯，如喜欢举例子、经常追问细节等"]\n'
    "}\n\n"
    "如果没有足够信息推断某个字段，用空字符串或空数组。只输出 JSON，不要额外文字。"
)

# 合并旧画像 + 新分析 → 更新后的画像
MERGE_SYSTEM_PROMPT = (
    "你是一个用户画像更新助手。你将收到：\n"
    "1. 旧画像（该用户的已有特征）\n"
    "2. 新分析（从最近对话提取的新特征）\n\n"
    "请合并两者，输出更新的 JSON 画像。新分析的内容优先，旧画像中未被新分析覆盖的保留。\n"
    "字段：tone（字符串）、taboos（数组）、focus（数组）、habits（数组）。只输出 JSON，不要额外文字。"
)

EVOLVE_MODEL_KEY = "deepseek-v4-flash"  # 使用轻量模型节约成本
MAX_ANALYSIS_MESSAGES = 20  # 分析最近多少条消息


async def handle_profile_evolve(params: dict) -> dict:
    """Profile evolution task handler.

    框架 worker 调用此函数。params 包含 conversation_id 和 owner_id。
    """
    conversation_id = params.get("conversation_id")
    owner_id = params.get("owner_id")
    if not conversation_id or not owner_id:
        return {"error": "Missing conversation_id or owner_id"}

    logger.info("Profile evolve starting for user %s, conv %s", owner_id, conversation_id)

    async with AsyncSessionLocal() as db:
        # 获取最近对话
        from . import conversation_service as conv_svc
        messages = await conv_svc.get_messages(db, owner_id, conversation_id)
        if not messages:
            return {"error": "No messages found", "owner_id": owner_id}

        # 只取最近 N 条消息
        recent = messages[-MAX_ANALYSIS_MESSAGES:]

        # 构建分析用消息
        chat_messages = [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "对话历史：\n" + "\n".join(
                    f"{m.role}: {m.content[:500]}"
                    for m in recent
                    if m.role in ("user", "assistant")
                ),
            },
        ]

        # 调大模型分析
        result = await gateway_router.chat(
            messages=chat_messages,
            profile_key=EVOLVE_MODEL_KEY,
        )

        content = result.get("content", "")
        if not content:
            logger.warning("Profile evolve: empty LLM response for user %s", owner_id)
            return {"error": "Empty LLM response", "owner_id": owner_id}

        # 从返回解析 JSON
        new_profile = _parse_profile_json(content)
        if not new_profile:
            logger.warning("Profile evolve: failed to parse LLM response for user %s: %s", owner_id, content[:200])
            return {"error": "Failed to parse profile JSON", "owner_id": owner_id}

        # 获取旧画像，合并
        old_profile_data = await conv_svc.get_active_user_profile(db, owner_id)
        merged = await _merge_profiles(old_profile_data, new_profile)

        # 更新画像
        updated = await conv_svc.update_user_profile(db, owner_id, merged)
        logger.info(
            "Profile evolved for user %s: version %d -> %d",
            owner_id,
            (updated.version or 1) - 1,
            updated.version,
        )

    return {
        "status": "ok",
        "owner_id": owner_id,
        "version": updated.version,
        "profile_summary": {k: v for k, v in merged.items() if v},
    }


def _parse_profile_json(text: str) -> dict | None:
    """Attempt to extract JSON from LLM response text."""
    # Try direct parse
    text = text.strip()
    # Remove markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            if line.strip().startswith("```"):
                continue
            cleaned.append(line)
        text = "\n".join(cleaned)
    text = text.strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Try extracting first JSON block
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return None


async def _merge_profiles(old: dict, new: dict) -> dict:
    """Use LLM to merge old and new profiles, or fall back to simple merge."""
    # Simple merge strategy (fallback): new data overwrites old, lists merge uniquely
    merged = dict(old)

    for key in ("tone",):
        if key in new and new[key]:
            merged[key] = new[key]

    for key in ("taboos", "focus", "habits"):
        if key in new and isinstance(new[key], list) and new[key]:
            old_list = merged.get(key, [])
            if isinstance(old_list, list):
                # Union: keep old items not contradicted by new, add new items not in old
                old_set = set(item.strip().lower() for item in old_list if isinstance(item, str))
                for item in new[key]:
                    if isinstance(item, str) and item.strip().lower() not in old_set:
                        old_list.append(item.strip())
                        old_set.add(item.strip().lower())
                merged[key] = old_list
            else:
                merged[key] = new[key]

    return merged
