"""Background review fork engine.

Runs as a fire-and-forget post-turn task.  The review fork:
  - Has restricted tool access (memory + skill management only)
  - Does NOT interact with the user
  - Produces structured proposals (stable rule, chunk, experience, skill, profile)
  - Proposals are stored in agent_review_results for admin review
  - Proposals cannot directly modify skills — must go through approval gate
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ReviewResult, ReviewTask

logger = logging.getLogger("v2.agent").getChild("services.review_service")

REVIEW_MAX_ROUNDS = 3
REVIEW_CONTEXT_LIMIT = 4000


async def create_review_task(
    db: AsyncSession,
    conversation_id: int,
    owner_id: int,
    review_context: dict | None = None,
) -> ReviewTask | None:
    """Create a review task record (pending)."""
    if review_context is None:
        review_context = {}
    try:
        task = ReviewTask(
            conversation_id=conversation_id,
            owner_id=owner_id,
            status="pending",
            review_context=review_context,
            started_at=datetime.now(timezone.utc),
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task
    except Exception as exc:
        logger.warning("Failed to create review task: %s", exc)
        return None


async def complete_review_task(db: AsyncSession, task: ReviewTask) -> None:
    """Mark a review task as completed."""
    try:
        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to complete review task: %s", exc)


async def save_review_proposal(
    db: AsyncSession,
    review_task_id: int,
    owner_id: int,
    result_type: str,
    title: str,
    summary: str,
    detail: dict | None = None,
) -> ReviewResult | None:
    """Save a structured review proposal."""
    if detail is None:
        detail = {}
    try:
        result = ReviewResult(
            review_task_id=review_task_id,
            owner_id=owner_id,
            result_type=result_type,
            title=title,
            summary=summary,
            detail=detail,
            status="proposal",
        )
        db.add(result)
        await db.commit()
        await db.refresh(result)
        return result
    except Exception as exc:
        logger.warning("Failed to save review proposal: %s", exc)
        return None


async def run_background_review(
    conversation_id: int,
    owner_id: int,
    messages: list[dict],
    tool_events: list[dict] | None = None,
) -> dict:
    """Background review fork — runs with restricted tool access.

    This is the core review loop.  It:
      1. Creates a review task record
      2. Calls the model with a review-specific system prompt
      3. Parses structured proposals from the model response
      4. Saves proposals to agent_review_results
      5. Marks the review task as completed

    Returns a summary of what was proposed.
    """
    tool_events = tool_events or []
    from app.database import AsyncSessionLocal

    # Build review context from the last few messages
    recent = messages[-4:] if len(messages) > 4 else messages
    context_parts: list[str] = []
    for msg in recent:
        role = msg.get("role", "unknown")
        content = (msg.get("content") or "")[:REVIEW_CONTEXT_LIMIT]
        context_parts.append(f"[{role}]: {content}")
    conversation_snippet = "\n".join(context_parts)

    # Tool call context
    tool_summary = ""
    if tool_events:
        tool_names = [e.get("name", "") for e in tool_events if e.get("type") == "tool_call"]
        if tool_names:
            tool_summary = f"Tools used in this turn: {', '.join(tool_names)}"

    system_prompt = (
        "You are a background review agent. Your job is to analyse the conversation turn "
        "and produce structured proposals for improving the system.\n\n"
        "You may ONLY produce proposals from these types:\n"
        "  - stable_rule: A chat-learned rule worth persisting\n"
        "  - chunk_proposal: A memory chunk worth creating/updating\n"
        "  - experience_proposal: A reusable experience pattern\n"
        "  - skill_create: A new skill worth creating\n"
        "  - skill_patch: An existing skill worth modifying\n"
        "  - profile_note: A suggested user profile update\n"
        "  - safety_note: A safety observation\n\n"
        "Rules:\n"
        "  1. Be conservative — only propose what is clearly valuable.\n"
        "  2. Each proposal must have a clear title and actionable summary.\n"
        "  3. You CANNOT directly create or modify skills — only propose.\n"
        "  4. Output format: one JSON object per line, each with "
        '{"type": "...", "title": "...", "summary": "...", "detail": {...}}.\n'
        "  5. If nothing worth proposing, output an empty JSON array []."
    )

    messages_for_model = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"Review this conversation turn:\n\n{conversation_snippet}\n\n"
                f"{tool_summary}\n\n"
                "Produce structured proposals (one JSON per line) or [] if none."
            ),
        },
    ]

    async with AsyncSessionLocal() as db:
        task = await create_review_task(
            db, conversation_id, owner_id,
            {"message_count": len(messages), "tool_event_count": len(tool_events)},
        )
        if task is None:
            return {"error": "Failed to create review task"}
        task.status = "in_progress"
        await db.commit()

    # Call the model for review
    from app.gateway import service as gateway_service

    proposals: list[dict] = []
    try:
        result = await gateway_service.chat(
            messages=messages_for_model,
            profile_key="deepseek-v4-flash",
        )
        if result.get("error"):
            logger.warning("Review model call failed: %s", result["error"])
            async with AsyncSessionLocal() as db:
                await complete_review_task(db, task)
            return {"error": result["error"]}

        raw_content = result.get("content", "").strip()
        if raw_content and raw_content != "[]":
            for line in raw_content.split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    proposal = json.loads(line)
                    if isinstance(proposal, dict) and proposal.get("type"):
                        proposals.append(proposal)
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception as exc:
        logger.warning("Review model call exception: %s", exc)
        async with AsyncSessionLocal() as db:
            await complete_review_task(db, task)
        return {"error": str(exc)}

    # Save all proposals
    saved: list[dict] = []
    async with AsyncSessionLocal() as db:
        for prop in proposals:
            prop_type = prop.get("type", "unknown")
            title = prop.get("title", "")
            summary = prop.get("summary", "")
            detail = prop.get("detail", {})
            r = await save_review_proposal(
                db, task.id, owner_id,
                prop_type, title, summary, detail,
            )
            if r:
                saved.append({"id": r.id, "type": prop_type, "title": title})

        await complete_review_task(db, task)

    logger.info(
        "Background review: conv=%s owner=%s proposals=%d saved=%d",
        conversation_id, owner_id, len(proposals), len(saved),
    )
    return {
        "review_task_id": task.id,
        "proposals_count": len(proposals),
        "saved_count": len(saved),
        "proposals": saved,
    }


async def list_review_tasks(
    db: AsyncSession,
    limit: int = 20,
    status: str | None = None,
) -> list[dict]:
    """List recent review tasks."""
    q = select(ReviewTask).order_by(desc(ReviewTask.created_at)).limit(limit)
    if status:
        q = q.where(ReviewTask.status == status)
    r = await db.execute(q)
    return [
        {
            "id": t.id,
            "conversation_id": t.conversation_id,
            "owner_id": t.owner_id,
            "status": t.status,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in r.scalars().all()
    ]


async def list_review_results(
    db: AsyncSession,
    review_task_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List review proposals."""
    q = select(ReviewResult).order_by(desc(ReviewResult.created_at)).limit(limit)
    if review_task_id is not None:
        q = q.where(ReviewResult.review_task_id == review_task_id)
    if status:
        q = q.where(ReviewResult.status == status)
    r = await db.execute(q)
    return [
        {
            "id": prop.id,
            "review_task_id": prop.review_task_id,
            "owner_id": prop.owner_id,
            "result_type": prop.result_type,
            "title": prop.title,
            "summary": prop.summary,
            "detail": prop.detail,
            "status": prop.status,
            "reviewed_by": prop.reviewed_by,
            "created_at": prop.created_at.isoformat() if prop.created_at else None,
        }
        for prop in r.scalars().all()
    ]
