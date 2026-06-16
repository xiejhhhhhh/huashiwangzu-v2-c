"""
L2 page-level fusion — conflict tracking
"""
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ConflictEntry:
    type: str
    detail: str
    sources: list[str] = field(default_factory=list)
    severity: str = "info"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def detect_conflicts(
    fusion_text: str,
    sources: list[dict],
    subject_candidates: list[dict],
    attributes: list[dict],
) -> list[ConflictEntry]:
    conflicts: list[ConflictEntry] = []

    # Check for empty or very short fusion
    if not fusion_text or len(fusion_text.strip()) < 20:
        conflicts.append(ConflictEntry(
            type="fusion_too_short",
            detail=f"Fusion text too short ({len(fusion_text.strip())} chars)",
            severity="warning",
        ))

    # Check source coverage
    present = {s.get("source_type") for s in sources if s.get("content")}
    if "script" not in present and "ocr" not in present:
        conflicts.append(ConflictEntry(
            type="missing_primary_source",
            detail="No script or OCR source available for this page",
            severity="warning",
        ))

    # Check subject-attribute consistency
    subject_names = {s.get("name") for s in subject_candidates if s.get("name")}
    for attr in attributes:
        if attr.get("subject") and attr["subject"] not in subject_names:
            conflicts.append(ConflictEntry(
                type="orphan_attribute",
                detail=f"Attribute '{attr.get('attr_name')}' references subject '{attr['subject']}' not in subject candidates",
                sources=["attribute"],
                severity="info",
            ))

    return conflicts
