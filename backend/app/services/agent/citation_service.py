import re
import asyncio
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge import PageFusion, Catalog, Chunk

logger = logging.getLogger("v2.agent.citation")

CITATION_RE = re.compile(r"\[\^(\d+)\]")
VALIDATION_TIMEOUT = 10.0


class CitationService:
    async def validate_and_format(
        self, db: AsyncSession, content: str, timeout: float = VALIDATION_TIMEOUT,
    ) -> dict:
        found_ids = set(int(m) for m in CITATION_RE.findall(content))
        if not found_ids:
            return {"content": content, "sources": []}

        try:
            valid_sources = await asyncio.wait_for(
                self._validate_ids(db, found_ids), timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Citation validation timed out after %.1fs, returning unfiltered", timeout)
            return {"content": content, "sources": [], "warning": "Validation timed out, citations not verified"}

        valid_ids = {s["id"] for s in valid_sources}

        def cleanup(m: re.Match) -> str:
            cid = int(m.group(1))
            return m.group(0) if cid in valid_ids else ""

        cleaned = CITATION_RE.sub(cleanup, content)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return {"content": cleaned, "sources": valid_sources}

    async def _validate_ids(self, db: AsyncSession, ids: set[int]) -> list[dict]:
        sources: list[dict] = []
        for cid in sorted(ids):
            # Try fusion first
            pf = await db.get(PageFusion, cid)
            if pf:
                catalog = await db.get(Catalog, pf.catalog_id)
                sources.append({
                    "id": cid,
                    "type": "fusion",
                    "file_name": catalog.file_name if catalog else "",
                    "page_num": pf.page_num,
                    "source_file_url": f"/api/knowledge/catalogs/{pf.catalog_id}",
                })
                continue
            # Try chunk
            chunk = await db.get(Chunk, cid)
            if chunk:
                catalog = await db.get(Catalog, chunk.catalog_id)
                sources.append({
                    "id": cid,
                    "type": "chunk",
                    "file_name": catalog.file_name if catalog else "",
                    "page_num": chunk.page_num,
                    "source_file_url": f"/api/knowledge/catalogs/{chunk.catalog_id}",
                })
                continue
            # Invalid ID skipped
        return sources

    def format_sources_markdown(self, sources: list[dict]) -> str:
        if not sources:
            return ""
        lines = ["\n\n---\n**来源：**"]
        for s in sources:
            page = f" (第{s['page_num']}页)" if s.get("page_num") else ""
            backlink = f" [🔗]({s['source_file_url']})" if s.get("source_file_url") else ""
            lines.append(f"- [^{s['id']}] {s['file_name']}{page}{backlink}")
        return "\n".join(lines)


citation_service = CitationService()
