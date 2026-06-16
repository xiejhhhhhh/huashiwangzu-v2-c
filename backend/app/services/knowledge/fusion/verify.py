"""
L2 page-level fusion — four-way verification (规则优先，不滥用 LLM)
"""
import re

from app.services.knowledge.fusion.conflict import ConflictEntry


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[•·●‣⁃]", "-", text)
    text = re.sub(r"[﻿\u200b\u200c\u200d\ufeff]", "", text)
    return text.strip()


PUNCT_RE = re.compile(r"[，。！？、；：\u201c\u201d\u2018\u2019\u300a\u300b\u3010\u3011\s]+")

def _word_set(text: str) -> set[str]:
    cleaned = PUNCT_RE.sub(" ", text)
    return set(w for w in cleaned.split() if w.strip())


def _line_words(line: str) -> set[str]:
    return set(re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", line))


def _dedup_aligned(script_lines: list[str], ocr_lines: list[str]) -> list[str]:
    merged: list[str] = []
    ocr_idx = 0
    for s_line in script_lines:
        s_clean = s_line.strip()
        if not s_clean:
            continue
        s_words = _line_words(s_clean)
        best_match = None
        best_ratio = 0.0
        for j in range(ocr_idx, min(ocr_idx + 3, len(ocr_lines))):
            o_clean = ocr_lines[j].strip()
            if not o_clean:
                continue
            o_words = _line_words(o_clean)
            if not s_words and not o_words:
                continue
            overlap = len(s_words & o_words) / max(len(s_words | o_words), 1)
            if overlap > best_ratio:
                best_ratio = overlap
                best_match = j
        if best_match is not None and best_ratio > 0.5:
            merged.append(s_line)
            ocr_idx = best_match + 1
        else:
            merged.append(s_line)
    for j in range(ocr_idx, len(ocr_lines)):
        line = ocr_lines[j].strip()
        if line:
            merged.append(line)
    return merged


def _extract_text(source: dict) -> str:
    content = source.get("content") or {}
    if isinstance(content, dict):
        return content.get("text") or content.get("summary") or ""
    return str(content)


def verify_page(sources: list[dict]) -> tuple[str, list[ConflictEntry]]:
    by_type: dict[str, str] = {}
    for src in sources:
        st = src.get("source_type", "")
        by_type[st] = _extract_text(src)

    script = _clean_text(by_type.get("script", ""))
    ocr = _clean_text(by_type.get("ocr", ""))
    vision = _clean_text(by_type.get("vision", ""))
    conflicts: list[ConflictEntry] = []

    # Priority: script > ocr > vision
    if script and ocr:
        s_lines = [l for l in script.split("\n") if l.strip()]
        o_lines = [l for l in ocr.split("\n") if l.strip()]
        aligned = _dedup_aligned(s_lines, o_lines)
        base = "\n".join(aligned)

        if len(base) < max(len(script), len(ocr)) * 0.6:
            conflicts.append(ConflictEntry(
                type="text_mismatch",
                detail="Script vs OCR alignment ratio < 60%, significant mismatch",
                sources=["script", "ocr"],
                severity="warning",
            ))
            base = script if len(script) >= len(ocr) else ocr
    elif script:
        base = script
    elif ocr:
        base = ocr
    else:
        base = ""

    if vision and base:
        vision_clean = _clean_text(vision)
        v_words = _word_set(vision_clean)
        b_words = _word_set(base)
        overlap_ratio = len(v_words & b_words) / max(len(v_words | b_words), 1)
        if overlap_ratio < 0.3:
            conflicts.append(ConflictEntry(
                type="vision_diverges",
                detail=f"Vision text differs significantly from base (overlap={overlap_ratio:.2f})",
                sources=["vision"],
                severity="info",
            ))

    if vision and not base:
        base = vision

    return base, conflicts
