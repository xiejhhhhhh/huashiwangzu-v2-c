from __future__ import annotations

from .base import MediaContext, MediaProvider, StageResult


class SmallModelProvider(MediaProvider):
    provider_key = "small_model.placeholder"

    async def run(self, context: MediaContext) -> StageResult:
        modality = "image" if context.media_type == "image" else "video"
        summary = (
            f"{modality.title()} file {context.file_name} was analyzed with local deterministic signals. "
            "No small model runtime is configured yet."
        )
        tags = [context.media_type, context.extension]
        if context.size_bytes > 20_000_000:
            tags.append("large_file")
        return StageResult(
            stage="small_model",
            provider=self.provider_key,
            status="placeholder",
            data={
                "summary": summary,
                "tags": tags,
                "model": "not_configured",
                "adapter_boundary": "Replace this provider with CLIP/YOLO/OCR/embedding/ASR local model adapters.",
            },
            warnings=["Small-model provider registry is present but only the deterministic placeholder is enabled."],
            confidence=0.4,
        )
