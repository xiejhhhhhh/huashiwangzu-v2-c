import asyncio
import logging

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Catalog, PageSource
from app.services.knowledge.catalog_service import CatalogService

logger = logging.getLogger(__name__)


class ExtractDispatcher:
    _handlers: dict[str, type] = {}

    @classmethod
    def register(cls, channel_type: str):
        def wrapper(handler_cls: type):
            cls._handlers[channel_type] = handler_cls
            return handler_cls
        return wrapper

    @classmethod
    async def dispatch(cls, db: AsyncSession, catalog: Catalog) -> None:
        channel = catalog.channel_type
        handler_cls = cls._handlers.get(channel)

        if not handler_cls:
            await CatalogService.update_status(db, catalog.id, "failed", f"No handler for channel: {channel}")
            return

        await CatalogService.update_status(db, catalog.id, "processing")

        try:
            extractor = handler_cls()
            pages = await asyncio.to_thread(extractor.extract, catalog.file_path)
            await cls._write_sources(db, catalog.id, pages)
            await CatalogService.update_status(db, catalog.id, "done")
        except Exception as e:
            logger.exception("Extraction failed for catalog %d (%s)", catalog.id, catalog.file_name)
            await CatalogService.update_status(db, catalog.id, "failed", str(e))
            raise

    @classmethod
    async def _write_sources(cls, db: AsyncSession, catalog_id: int, pages: list) -> None:
        from app.services.knowledge.extract.types import PageResult
        records = []
        for page in pages:
            if isinstance(page, PageResult):
                records.extend(page.to_page_source_dicts(catalog_id))
            elif isinstance(page, dict):
                records.append(page)
        if not records:
            return

        seen = set()
        unique_records = []
        for r in records:
            key = (r["catalog_id"], r["page_num"], r["source_type"])
            if key not in seen:
                seen.add(key)
                unique_records.append(r)

        stmt = pg_insert(PageSource).values(unique_records)
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_page_source"
        )
        await db.execute(stmt)
        await db.commit()
