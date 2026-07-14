from __future__ import annotations

import logging

from app.services.model_services import describe_image_detailed

from .base import MediaContext, MediaProvider, StageResult

logger = logging.getLogger("v2.media_intelligence").getChild("vlm")

_MIME_MAP: dict[str, str] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "jfif": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "avif": "image/avif",
}


class VlmRefineProvider(MediaProvider):
    provider_key = "vlm_refine"

    async def run(self, context: MediaContext) -> StageResult:
        if not context.path or not context.path.is_file():
            return self._degraded("Approved media file is not accessible on disk.")

        try:
            image_bytes = context.path.read_bytes()
        except OSError as exc:
            logger.warning("Cannot read media file for VLM: %s", exc)
            return self._degraded(f"Cannot read media file: {exc}")

        if not image_bytes:
            return self._degraded("Media file is empty; no bytes to send to VLM.")

        prompt = str(context.options.get("prompt", "") or "").strip()
        if not prompt:
            prompt = "请详细描述这张图片的内容、场景、主体和文字信息。"

        mime_type = _MIME_MAP.get(context.extension, "image/jpeg")

        try:
            detailed = await describe_image_detailed(
                image_bytes=image_bytes,
                prompt=prompt,
                profile_key=None,  # use default vision profile (gpt-5.5-vision)
                mime_type=mime_type,
            )
        except Exception as exc:
            logger.error("VLM gateway call failed: %s", exc)
            return self._degraded(f"VLM gateway error: {exc}")

        content = ""
        if isinstance(detailed, dict):
            content = str(detailed.get("content") or "")
            diagnostics = detailed.get("diagnostics") or {}
        else:
            content = str(detailed)
            diagnostics = {}

        if not content:
            return self._degraded("VLM gateway returned empty content.")

        data: dict[str, object] = {
            "refined_summary": content,
            "model": str(
                diagnostics.get("model")
                or detailed.get("model")
                or "gpt-5.5-vision"
            ),
        }

        model_fallback: dict[str, object] = {
            "primary_model": diagnostics.get("primary_model", "gpt-5.5-vision"),
            "final_success": True,
        }
        failure = diagnostics.get("failure_category")
        if failure:
            model_fallback["failure_category"] = failure
            model_fallback["primary_failed"] = True
            model_fallback["fallback_used"] = True
            model_fallback["fallback_model"] = diagnostics.get("fallback_model", "unknown")
            data["model_fallback"] = model_fallback

        degraded_entries = diagnostics.get("degraded", [])
        if isinstance(degraded_entries, list):
            data["degraded"] = degraded_entries

        return StageResult(
            stage="vlm_refine",
            provider=self.provider_key,
            status="ok",
            data=data,
            warnings=[],
            confidence=0.85,
        )

    def _degraded(self, message: str) -> StageResult:
        return StageResult(
            stage="vlm_refine",
            provider=f"{self.provider_key}.degraded",
            status="degraded",
            data={
                "refined_summary": (
                    f"VLM refine is unavailable: {message} "
                    "Local and rule-based facts are returned without visual reasoning."
                ),
                "model": "degraded",
                "model_fallback": {
                    "primary_model": "vlm_refine.primary",
                    "primary_failed": True,
                    "fallback_used": True,
                    "fallback_model": "local_and_rule_based_summary",
                    "final_success": True,
                    "failure_category": "gateway_error",
                    "failure_code": "vlm_gateway_error",
                    "retryable": True,
                },
                "degraded": [
                    {
                        "code": "vlm_gateway_error",
                        "dependency": "vlm",
                        "message": message,
                    }
                ],
            },
            warnings=[message],
            confidence=0.3,
        )
