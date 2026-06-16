"""Label candidate extraction helpers."""
from pathlib import Path

from app.models.knowledge import Catalog, PageFusion


def catalog_label_candidates(catalog: Catalog) -> list[str]:
    stem = Path(catalog.file_name).stem
    parts = [
        stem,
        catalog.channel_type,
        catalog.mime_type.split("/")[-1] if catalog.mime_type else "",
    ]
    return [part for part in parts if part]


def fusion_label_candidates(fusion: PageFusion) -> list[str]:
    values: list[str] = []
    raw = fusion.labels
    if isinstance(raw, list):
        values.extend(str(item) for item in raw)
    if isinstance(raw, dict):
        for item in raw.values():
            values.extend(_label_values(item))
    if fusion.summary:
        values.extend(part.strip() for part in fusion.summary.replace("，", ",").split(","))
    return values


def dedupe_candidates(candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in candidates:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _label_values(item: object) -> list[str]:
    if isinstance(item, list):
        return [str(val) for val in item]
    if item:
        return [str(item)]
    return []
