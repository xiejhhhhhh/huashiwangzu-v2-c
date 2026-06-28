"""一次性清理脚本：标记历史脏消息（DSML 泄露/空回复+裸 usage）。

用法：
    cd backend && .venv/bin/python3 ../modules/agent/scripts/cleanup_dirty_messages.py

不会删除任何数据，只将脏消息标记为 status='hidden'。
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_DIR))

os.environ.setdefault("APP_ENV", "development")

from app.database import AsyncSessionLocal
from sqlalchemy import select

from modules.agent.backend.models import AgentMessage
from modules.agent.backend.runtime.content_gate import final_clean_content

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cleanup_dirty_messages")


async def cleanup() -> None:
    hidden_count = 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentMessage).where(
                AgentMessage.role == "assistant",
                AgentMessage.status == "active",
            )
        )
        messages = result.scalars().all()

        for msg in messages:
            content = msg.content or ""
            cleaned = final_clean_content(content)
            has_dsml = any(marker in content for marker in ("<", "<INVOKE", "<tool_calls", "<invoke"))
            is_dsml_polluted = has_dsml and (len(cleaned.strip()) == 0 or len(cleaned) < len(content) // 2)

            if is_dsml_polluted or (not content.strip() and has_dsml):
                msg.status = "hidden"
                hidden_count += 1
                logger.info("HIDDEN msg=%d (chars: %d -> %d)", msg.id, len(content), len(cleaned))

        await db.commit()

    logger.info("Done: %d messages hidden", hidden_count)


if __name__ == "__main__":
    asyncio.run(cleanup())
