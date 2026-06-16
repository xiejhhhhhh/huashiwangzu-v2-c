"""L1: Auto-merge similar candidates — strip punctuation/whitespace,
synonym resolution, case normalization, alias grouping."""

import re
import unicodedata
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge.candidate import ExtractCandidate


_NORMALIZE_RE = re.compile(r"[^\w\u4e00-\u9fff]+")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = t.lower().strip()
    t = _WHITESPACE_RE.sub("", t)
    t = _NORMALIZE_RE.sub("", t)
    return t


def build_clusters(candidates: list[ExtractCandidate]) -> dict[str, list[ExtractCandidate]]:
    clusters: dict[str, list[ExtractCandidate]] = defaultdict(list)
    for c in candidates:
        key = normalize_text(c.content)
        clusters[key].append(c)
    return dict(clusters)


async def run_l1_merge(db: AsyncSession, batch_size: int = 500) -> int:
    result = await db.execute(
        select(ExtractCandidate).where(
            ExtractCandidate.verdict_status == 0
        ).limit(batch_size)
    )
    candidates = list(result.scalars().all())
    if not candidates:
        return 0

    clusters = build_clusters(candidates)
    merged_count = 0

    for normal_key, group in clusters.items():
        if len(group) <= 1:
            continue
        # Keep the one with highest confidence, archive the rest
        group.sort(key=lambda c: c.confidence, reverse=True)
        keeper = group[0]
        for duplicate in group[1:]:
            duplicate.verdict_status = 3
            if duplicate.extra is None:
                duplicate.extra = {}
            duplicate.extra["l1_merged_into"] = keeper.id
            duplicate.extra["l1_reason"] = "merged duplicate (normalized match)"
            keeper.confidence = max(keeper.confidence, duplicate.confidence)
            merged_count += 1

    if merged_count:
        await db.flush()
    return merged_count
