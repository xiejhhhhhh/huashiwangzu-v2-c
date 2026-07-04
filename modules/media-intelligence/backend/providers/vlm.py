from __future__ import annotations

from .base import MediaContext, MediaProvider, StageResult


class VlmRefineProvider(MediaProvider):
    provider_key = "vlm_refine.not_configured"

    async def run(self, context: MediaContext) -> StageResult:
        prompt = str(context.options.get("prompt", "") or "").strip()
        suffix = f" Requested focus: {prompt}" if prompt else ""
        return StageResult(
            stage="vlm_refine",
            provider=self.provider_key,
            status="degraded",
            data={
                "refined_summary": (
                    "VLM refine is not configured; local and rule-based facts are returned without visual reasoning."
                    f"{suffix}"
                ),
                "model": "not_configured",
                "model_fallback": {
                    "primary_model": "vlm_refine.primary",
                    "primary_failed": True,
                    "fallback_used": True,
                    "fallback_model": "local_and_rule_based_summary",
                    "final_success": True,
                    "failure_category": "not_configured",
                    "failure_code": "vlm_missing",
                    "retryable": False,
                },
                "degraded": [
                    {
                        "code": "vlm_missing",
                        "dependency": "vlm",
                        "message": "No VLM adapter is configured for media-intelligence refine.",
                        "install_command": "Wire the framework model gateway VLM or an approved local VLM adapter.",
                    }
                ],
            },
            warnings=["No VLM adapter is configured; refine returned a structured degraded result."],
            confidence=0.3,
        )
