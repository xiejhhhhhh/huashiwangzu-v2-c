"""L0: Auto-ignore dirty candidates — JSON fragments, paths, process words,
generic words, pure symbols, abnormal length."""

import re
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge.candidate import ExtractCandidate
from app.services.knowledge.dictionary.seed import is_stop_word, is_process_word


def _looks_like_json_fragment(text: str) -> bool:
    patterns = [
        r"^\{.*\"", r"^\".*\":", r"^\[.*\]$",
        r"\bnull\b", r"\btrue\b|\bfalse\b",
        r"[a-z_]+\.[a-z_]+\(.*\)",
    ]
    return any(re.search(p, text) for p in patterns)


def _looks_like_path(text: str) -> bool:
    patterns = [
        r"^/", r"^[A-Za-z]:\\", r"^\.\./", r"^\.\/",
        r"\.(png|jpg|pdf|docx|xlsx|txt)$",
        r"^https?://", r"^ftp://",
    ]
    return any(re.search(p, text.strip()) for p in patterns)


def _is_pure_symbol(text: str) -> bool:
    return bool(re.match(r"^[^a-zA-Z0-9\u4e00-\u9fff]{1,10}$", text))


def _has_length_anomaly(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) <= 1:
        return True
    if len(stripped) > 200:
        return True
    return False


def _is_candidate_ignorable(content: str) -> tuple[bool, str]:
    text = content.strip()
    if _has_length_anomaly(text):
        return True, "L0: length anomaly"
    if _looks_like_json_fragment(text):
        return True, "L0: JSON fragment"
    if _looks_like_path(text):
        return True, "L0: path/URL"
    if _is_pure_symbol(text):
        return True, "L0: pure symbol"
    if is_process_word(text):
        return True, "L0: process/backend word"
    if is_stop_word(text):
        return True, "L0: generic stop word"
    return False, ""


async def run_l0_ignore(db: AsyncSession, batch_size: int = 500) -> int:
    result = await db.execute(
        select(ExtractCandidate).where(
            ExtractCandidate.verdict_status == 0
        ).limit(batch_size)
    )
    candidates = list(result.scalars().all())
    ignored = 0
    for c in candidates:
        should_ignore, reason = _is_candidate_ignorable(c.content)
        if should_ignore:
            c.verdict_status = 2
            if c.extra is None:
                c.extra = {}
            c.extra["l0_reason"] = reason
            ignored += 1
    if ignored:
        await db.flush()
    return ignored
