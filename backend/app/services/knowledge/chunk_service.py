import asyncio
import hashlib

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import PageFusion, Chunk


SEPARATORS = [
    "\n\n",
    "\n",
    "。",
    "！",
    "？",
    "，",
    "；",
    "：",
    "、",
    " ",
]

CHUNK_SIZE = 1024
CHUNK_OVERLAP = 128


_splitter = RecursiveCharacterTextSplitter(
    separators=SEPARATORS,
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
)


def compute_content_hash(text: str) -> str:
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _split_text(text: str, page_num: int, fusion_id: int) -> list[dict]:
    raw_chunks = _splitter.split_text(text)
    offset = 0
    result = []
    for chunk_text in raw_chunks:
        chunk_len = len(chunk_text)
        if not chunk_text.strip():
            offset += chunk_len
            continue
        result.append({
            "content": chunk_text,
            "page_num": page_num,
            "char_offset": offset,
            "source_fusion_id": fusion_id,
            "content_hash": compute_content_hash(chunk_text),
            "char_count": chunk_len,
        })
        offset += chunk_len
    return result


class ChunkService:

    @staticmethod
    async def build_content_for_chunking(fusion: PageFusion) -> str:
        parts = []
        if fusion.fusion_text:
            parts.append(fusion.fusion_text)
        if fusion.summary:
            parts.append(fusion.summary)
        return "\n".join(parts)

    @staticmethod
    async def chunk_fusion(
        db: AsyncSession,
        fusion: PageFusion,
    ) -> list[Chunk]:
        content = await ChunkService.build_content_for_chunking(fusion)
        if not content.strip():
            return []

        chunk_dicts = await _split_text_async(content, fusion.page_num, fusion.id)
        existing_hashes = await ChunkService._find_existing_hashes(
            db, [c["content_hash"] for c in chunk_dicts]
        )

        saved = []
        for cd in chunk_dicts:
            if cd["content_hash"] in existing_hashes:
                continue
            chunk = Chunk(
                catalog_id=fusion.catalog_id,
                content=cd["content"],
                content_hash=cd["content_hash"],
                page_num=cd["page_num"],
                char_offset=cd["char_offset"],
                source_fusion_id=cd["source_fusion_id"],
                tokens=cd["char_count"],
            )
            db.add(chunk)
            saved.append(chunk)
            existing_hashes.add(cd["content_hash"])

        if saved:
            await db.flush()
            for c in saved:
                await db.refresh(c)

        return saved

    @staticmethod
    async def chunk_all_fusions(
        db: AsyncSession, catalog_id: int | None = None
    ) -> list[Chunk]:
        stmt = select(PageFusion).order_by(PageFusion.catalog_id, PageFusion.page_num)
        if catalog_id is not None:
            stmt = stmt.where(PageFusion.catalog_id == catalog_id)
        result = await db.execute(stmt)
        fusions = result.scalars().all()

        all_chunks = []
        for fusion in fusions:
            chunks = await ChunkService.chunk_fusion(db, fusion)
            all_chunks.extend(chunks)
        await db.commit()
        return all_chunks

    @staticmethod
    async def get_chunks_by_catalog(
        db: AsyncSession, catalog_id: int
    ) -> list[Chunk]:
        result = await db.execute(
            select(Chunk)
            .where(Chunk.catalog_id == catalog_id)
            .order_by(Chunk.page_num, Chunk.char_offset)
        )
        return result.scalars().all()

    @staticmethod
    async def _find_existing_hashes(
        db: AsyncSession, hashes: list[str]
    ) -> set[str]:
        if not hashes:
            return set()
        result = await db.execute(
            select(Chunk.content_hash).where(Chunk.content_hash.in_(hashes))
        )
        return {row[0] for row in result.all()}


async def _split_text_async(text: str, page_num: int, fusion_id: int) -> list[dict]:
    return await asyncio.to_thread(_split_text, text, page_num, fusion_id)
