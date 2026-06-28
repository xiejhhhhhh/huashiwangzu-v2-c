"""UnderstandingLoopOrchestrator — controlled understanding phase for high-ambiguity tasks.

Runs a small set of understanding roles (intent_clarifier, concern_miner,
plan_critic, retrieval_evidence) with a max of 2-3 iterations and produces
a structured ``UnderstandingPacket``.

Only triggers for high-ambiguity or high-cost tasks.  Simple queries
(e.g. "hi", "what time is it") skip the loop entirely.
"""

from __future__ import annotations

import json
import logging
import time
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.gateway import service as gateway_service
from app.gateway.service import resolve_role_template

from ..prompt_seeds import (
    UNDERSTANDING_CONCERN_KEY,
    UNDERSTANDING_INTENT_KEY,
    UNDERSTANDING_PLAN_KEY,
    UNDERSTANDING_RETRIEVAL_KEY,
)
from ..services.runtime_prompt_provider import RuntimePromptProvider

logger = logging.getLogger("v2.agent").getChild("runtime.understanding")

UNDERSTANDING_MAX_ROUNDS = 2
UNDERSTANDING_BUDGET_RATIO = 0.6

# Simple heuristic thresholds for triggering the understanding loop
HIGH_AMBIGUITY_KEYWORDS = [
    "帮我分析", "帮我规划", "帮我做计划", "帮我设计",
    "我不确定", "有什么选择", "哪个更好", "怎么选",
    "比较一下", "建议一下", "有什么区别",
    "复杂", "大型", "多步骤",
]
LOW_COMPLEXITY_PATTERNS = [
    "hi", "hello", "你好", "在吗", "在不在",
    "谢谢", "再见", "bye", "ok", "好的",
    "?", "？",  # single question mark often means simple greeting
]

UNDERSTANDING_ROLES = [
    "intent_clarifier",
    "concern_miner",
    "plan_critic",
    "retrieval_evidence",
]

ROLE_PROMPT_KEYS: dict[str, str] = {
    "intent_clarifier": UNDERSTANDING_INTENT_KEY,
    "concern_miner": UNDERSTANDING_CONCERN_KEY,
    "plan_critic": UNDERSTANDING_PLAN_KEY,
    "retrieval_evidence": UNDERSTANDING_RETRIEVAL_KEY,
}


def _is_high_ambiguity(user_input: str) -> bool:
    """Simple heuristic: check if the input suggests complex or ambiguous tasks."""
    lower = user_input.lower().strip()
    if len(lower) < 5:
        return False
    for pattern in LOW_COMPLEXITY_PATTERNS:
        if lower == pattern or lower.startswith(pattern):
            return False
    for kw in HIGH_AMBIGUITY_KEYWORDS:
        if kw in lower:
            return True
    word_count = len(lower.split())
    if word_count > 20:
        return True
    return False


def _is_high_cost(user_input: str, profile_key: str) -> bool:
    """Simple heuristic: long inputs or those requiring complex processing cost more."""
    word_count = len(user_input.split())
    if word_count > 50:
        return True
    return False


class UnderstandingLoopOrchestrator:
    """Orchestrates the understanding phase for a single chat turn.

    Usage::

        orchestrator = UnderstandingLoopOrchestrator(
            conversation_id=conv_id,
            owner_id=user_id,
            profile_key=profile_key,
        )
        packet = await orchestrator.run(user_input)
    """

    def __init__(
        self,
        conversation_id: int,
        owner_id: int,
        profile_key: str = "deepseek-v4-flash",
    ) -> None:
        self.conversation_id = conversation_id
        self.owner_id = owner_id
        self.profile_key = profile_key
        self.rounds_used = 0
        self.roles_executed: list[str] = []
        self.events: list[dict] = []

    async def should_trigger(self, user_input: str) -> bool:
        """Determine whether the understanding loop should run for this input."""
        return _is_high_ambiguity(user_input) or _is_high_cost(user_input, self.profile_key)

    async def run(self, user_input: str) -> dict:
        """Run the understanding loop and return an UnderstandingPacket-compatible dict.

        Returns a dict with all UnderstandingPacket fields filled, or
        an empty-skeleton if no roles executed.
        """
        packet: dict = {
            "owner_id": self.owner_id,
            "conversation_id": self.conversation_id,
            "trigger_reason": "high_ambiguity" if _is_high_ambiguity(user_input) else "high_cost",
            "user_input": user_input,
            "intent": "",
            "concerns": [],
            "plan_critique": "",
            "retrieval_evidence": [],
            "summary": "",
            "rounds_used": 0,
            "roles_executed": [],
            "resolved_profile_key": self.profile_key,
            "resolved_template": "understanding",
        }

        resolved = resolve_role_template("understanding")
        understanding_profile = resolved.primary_profile
        packet["resolved_profile_key"] = understanding_profile
        packet["resolved_template"] = resolved.name

        async with AsyncSessionLocal() as prompt_db:
            prompt_provider = RuntimePromptProvider(prompt_db)
            role_prompts = {
                role: await prompt_provider.get_system_prompt(key)
                for role, key in ROLE_PROMPT_KEYS.items()
            }

        for round_i in range(UNDERSTANDING_MAX_ROUNDS):
            self.rounds_used = round_i + 1
            for role in UNDERSTANDING_ROLES:
                system_prompt = role_prompts.get(role, "")
                if not system_prompt:
                    continue
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ]
                if role == "plan_critic" and packet.get("intent"):
                    messages.append({
                        "role": "user",
                        "content": f"额外参考 - 已识别的意图：{packet['intent']}"
                    })

                t0 = time.monotonic()
                try:
                    result = await gateway_service.chat(
                        messages=messages,
                        profile_key=understanding_profile,
                    )
                    duration_ms = (time.monotonic() - t0) * 1000
                    content = result.get("content", "")
                    if result.get("error"):
                        logger.warning("Understanding role '%s' error: %s", role, result["error"])
                        self._record_event(role, system_prompt, content, understanding_profile,
                                           round_i, duration_ms, False, result["error"])
                        continue

                    parsed = self._parse_json_response(content)
                    if not parsed:
                        logger.warning("Understanding role '%s' returned non-JSON: %s", role, content[:200])
                        self._record_event(role, system_prompt, content, understanding_profile,
                                           round_i, duration_ms, True)
                        continue

                    self._record_event(role, system_prompt, content, understanding_profile,
                                       round_i, duration_ms, True)
                    self.roles_executed.append(role)

                    if role == "intent_clarifier":
                        packet["intent"] = parsed.get("core_intent", content[:300])
                        if not packet.get("intent"):
                            packet["intent"] = content[:300]
                    elif role == "concern_miner":
                        packet["concerns"] = parsed.get("concerns", [])
                    elif role == "plan_critic":
                        packet["plan_critique"] = json.dumps(parsed, ensure_ascii=False)
                    elif role == "retrieval_evidence":
                        packet["retrieval_evidence"] = parsed.get("search_queries", [])
                except Exception as exc:
                    duration_ms = (time.monotonic() - t0) * 1000
                    logger.warning("Understanding role '%s' exception: %s", role, exc)
                    self._record_event(role, system_prompt, "", understanding_profile,
                                       round_i, duration_ms, False, str(exc))

            if self.roles_executed:
                break

        packet["rounds_used"] = self.rounds_used
        packet["roles_executed"] = list(dict.fromkeys(self.roles_executed))

        packet["summary"] = self._build_summary(packet)

        await self._persist_packet(packet)

        logger.info(
            "Understanding loop done: roles=%s rounds=%d",
            packet["roles_executed"], packet["rounds_used"],
        )
        return packet

    def _parse_json_response(self, content: str) -> dict | None:
        """Try to extract JSON from the model response."""
        if not content:
            return None
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            cleaned = []
            in_code = False
            for line in lines:
                if line.startswith("```"):
                    in_code = not in_code
                    continue
                if in_code:
                    cleaned.append(line)
            content = "\n".join(cleaned).strip()
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            try:
                start = content.index("{")
                end = content.rindex("}") + 1
                return json.loads(content[start:end])
            except (ValueError, json.JSONDecodeError):
                return None

    def _build_summary(self, packet: dict) -> str:
        parts = []
        if packet.get("intent"):
            parts.append(f"意图: {packet['intent']}")
        concerns = packet.get("concerns", [])
        if concerns:
            top = concerns[:3]
            parts.append(f"关注点({len(concerns)}个): {'; '.join(c.get('concern', '') for c in top)}")
        if packet.get("plan_critique"):
            parts.append("计划评估: 已完成")
        if packet.get("retrieval_evidence"):
            parts.append(f"检索需求: {len(packet['retrieval_evidence'])}条")
        return "; ".join(parts) if parts else "理解环完成"

    def _record_event(
        self,
        role: str,
        prompt: str,
        response: str,
        profile_key: str,
        round_index: int,
        duration_ms: float,
        success: bool,
        error: str | None = None,
    ) -> None:
        self.events.append({
            "owner_id": self.owner_id,
            "conversation_id": self.conversation_id,
            "role_name": role,
            "prompt": prompt,
            "response": response,
            "profile_key": profile_key,
            "round_index": round_index,
            "duration_ms": round(duration_ms, 1),
            "success": success,
            "error": error,
        })

    async def _persist_packet(self, packet: dict) -> None:
        """Persist the understanding packet and its events to DB."""
        try:
            from ..models import UnderstandingPacket, UnderstandingEvent
            async with AsyncSessionLocal() as db:
                db_packet = UnderstandingPacket(
                    owner_id=packet["owner_id"],
                    conversation_id=packet["conversation_id"],
                    trigger_reason=packet.get("trigger_reason", "high_ambiguity"),
                    user_input=packet.get("user_input", ""),
                    intent=packet.get("intent", ""),
                    concerns=packet.get("concerns", []),
                    plan_critique=packet.get("plan_critique", ""),
                    retrieval_evidence=packet.get("retrieval_evidence", []),
                    summary=packet.get("summary", ""),
                    rounds_used=packet.get("rounds_used", 0),
                    roles_executed=packet.get("roles_executed", []),
                    resolved_profile_key=packet.get("resolved_profile_key", ""),
                    resolved_template=packet.get("resolved_template", "default"),
                )
                db.add(db_packet)
                await db.flush()

                for ev in self.events:
                    db_event = UnderstandingEvent(
                        owner_id=ev["owner_id"],
                        packet_id=db_packet.id,
                        conversation_id=ev["conversation_id"],
                        role_name=ev["role_name"],
                        prompt=ev["prompt"],
                        response=ev["response"],
                        profile_key=ev["profile_key"],
                        round_index=ev["round_index"],
                        duration_ms=ev["duration_ms"],
                        success=ev["success"],
                        error=ev.get("error"),
                    )
                    db.add(db_event)

                await db.commit()
                logger.info("Persisted understanding packet id=%d roles=%s", db_packet.id, packet["roles_executed"])
        except Exception as exc:
            logger.warning("Failed to persist understanding packet (non-fatal): %s", exc)
