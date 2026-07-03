from __future__ import annotations

from .base import MediaContext, MediaProvider, StageResult


class VlmRefineProvider(MediaProvider):
    provider_key = "vlm_refine.placeholder"

    async def run(self, context: MediaContext) -> StageResult:
        prompt = str(context.options.get("prompt", "") or "").strip()
        suffix = f" Requested focus: {prompt}" if prompt else ""
        return StageResult(
            stage="vlm_refine",
            provider=self.provider_key,
            status="placeholder",
            data={
                "refined_summary": (
                    "VLM refine layer is reserved for expensive visual reasoning after local and small-model "
                    f"signals are assembled.{suffix}"
                ),
                "model": "not_configured",
                "adapter_boundary": "Use framework model gateway VLM or an approved local VLM adapter here.",
            },
            warnings=["VLM refine is intentionally a placeholder to keep the initial module dependency-light."],
            confidence=0.3,
        )
