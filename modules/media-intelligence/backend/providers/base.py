from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

MediaType = Literal["image", "video"]
StageName = Literal["local_algorithms", "small_model", "vlm_refine"]


@dataclass(frozen=True)
class MediaContext:
    file_id: int
    file_name: str
    extension: str
    media_type: MediaType
    path: Path
    size_bytes: int
    head_sha256: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageResult:
    stage: StageName
    provider: str
    status: Literal["ok", "skipped", "placeholder"]
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "provider": self.provider,
            "status": self.status,
            "data": self.data,
            "warnings": self.warnings,
            "confidence": self.confidence,
        }


class MediaProvider(ABC):
    provider_key: str = ""

    @abstractmethod
    async def run(self, context: MediaContext) -> StageResult:
        ...
