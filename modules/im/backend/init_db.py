"""IM 模块表初始化（幂等，模块加载时跑一次）。"""
import logging

from app.database import engine
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ImConversation, ImMessage, ImReadState

logger = logging.getLogger("v2.im").getChild("init_db")

TABLES = [ImConversation.__table__, ImMessage.__table__, ImReadState.__table__]


async def run_init(db: AsyncSession) -> None:
    """确保 IM 表存在（幂等）。"""
    async with engine.begin() as conn:
        for table in TABLES:
            await conn.run_sync(table.create, checkfirst=True)
    logger.info("IM tables ensured")
