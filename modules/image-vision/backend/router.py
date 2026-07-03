import base64
import logging

from app.core.exceptions import ValidationError
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.module_registry import register_capability
from app.services.uploaded_file_runner import run_uploaded_file_capability
from fastapi import APIRouter, Depends

from .image_analysis import analyze_image_bytes, build_local_summary, build_vlm_prompt, should_use_vlm

router = APIRouter(prefix="/api/image-vision", tags=["image-vision"])

LOGGER = logging.getLogger("v2.image-vision")
ALLOWED_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "ico"}
ANALYSIS_MODES = {"auto", "local", "semantic"}
MIME_TYPE_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "ico": "image/x-icon",
}


def _normalize_params(params: dict[str, object]) -> dict[str, object]:
    try:
        file_id = int(params.get("file_id", 0))
    except (TypeError, ValueError):
        raise ValidationError("file_id must be a positive integer") from None
    if file_id <= 0:
        raise ValidationError("file_id must be a positive integer")

    raw_mode = params.get("analysis_mode", params.get("mode", "auto"))
    if raw_mode is None:
        analysis_mode = "auto"
    elif isinstance(raw_mode, str):
        analysis_mode = raw_mode.strip().lower()
    else:
        raise ValidationError("analysis_mode must be one of: auto, local, semantic")
    if analysis_mode not in ANALYSIS_MODES:
        raise ValidationError("analysis_mode must be one of: auto, local, semantic")

    raw_prompt = params.get("prompt")
    if raw_prompt is None:
        prompt = None
    elif isinstance(raw_prompt, str):
        prompt = raw_prompt.strip()[:1000] or None
    else:
        raise ValidationError("prompt must be a string")

    return {"file_id": file_id, "analysis_mode": analysis_mode, "prompt": prompt}


async def _describe(params: dict, caller: str) -> dict:
    normalized = _normalize_params(params)
    analysis_mode = str(normalized["analysis_mode"])
    prompt = normalized.get("prompt")

    async def describe_file(file_id, file, full_path, ext):
        raw = full_path.read_bytes()
        filename = f"{file.name}.{file.extension}"
        warnings: list[str] = []
        try:
            local_analysis = analyze_image_bytes(raw, filename, ext)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        local_summary = build_local_summary(local_analysis)
        vlm_decision = should_use_vlm(local_analysis, analysis_mode)
        semantic_description = None
        vlm_attempted = False
        vlm_used = False

        if vlm_decision["use_vlm"]:
            vlm_attempted = True
            try:
                from app.services.model_services import describe_image

                candidate = await describe_image(
                    raw,
                    prompt=build_vlm_prompt(local_summary, prompt if isinstance(prompt, str) else None),
                    mime_type=MIME_TYPE_MAP.get(ext, "image/jpeg"),
                )
                semantic_description = candidate.strip() if isinstance(candidate, str) else None
                vlm_used = bool(semantic_description)
                if not semantic_description:
                    warnings.append("Vision model returned an empty description; using local analysis only.")
            except Exception as exc:
                warnings.append(f"Vision model unavailable; using local analysis only: {exc}")
                LOGGER.warning("image-vision VLM fallback for file_id=%d: %s", file_id, exc)

        description = local_summary
        if semantic_description:
            description = f"{semantic_description}\n\n{local_summary}"

        analysis_strategy = {
            "mode": analysis_mode,
            "local_algorithm": True,
            "local_analyzer": local_analysis["analyzer"],
            "vlm_attempted": vlm_attempted,
            "vlm_used": vlm_used,
            "vlm_decision": vlm_decision,
            "external_vlm_calls": 1 if vlm_attempted else 0,
            "degraded": vlm_attempted and not vlm_used,
        }

        data_b64 = base64.b64encode(raw).decode("ascii")
        resource_id = None
        try:
            from app.services.module_registry import call_capability

            store_result = await call_capability(
                "content", "store_analysis_resource",
                {
                    "data_b64": data_b64,
                    "resource_type": "image",
                    "mime_type": MIME_TYPE_MAP.get(ext, "image/jpeg"),
                    "filename": filename,
                    "description": description,
                    "file_id": file_id,
                },
                caller=caller, caller_role="viewer",
            )
            resource_id = store_result.get("data", store_result).get("id") if isinstance(store_result, dict) else None
            if resource_id:
                LOGGER.info("Persisted image-vision result to Resource id=%s for file_id=%d", resource_id, file_id)
        except Exception as exc:
            warnings.append(f"Analysis resource persistence failed: {exc}")
            LOGGER.warning("Failed to persist image-vision result to Resource: %s", exc)

        block_ref = resource_id if resource_id else 1
        blocks = [
            {"type": "image", "text": description, "page": None, "resource_ref": block_ref},
            {"type": "metadata", "text": local_summary, "page": None, "resource_ref": block_ref},
        ]
        resources = [
            {
                "id": block_ref,
                "type": "image",
                "file_storage_id": file_id,
                "text_desc": description,
                "metadata": local_analysis,
            },
        ]

        return {
            "file_id": file_id,
            "format": ext,
            "blocks": blocks,
            "resources": resources,
            "resource_id": resource_id,
            "description": description,
            "semantic_description": semantic_description,
            "local_analysis": local_analysis,
            "analysis_strategy": analysis_strategy,
            "warnings": warnings,
        }

    return await run_uploaded_file_capability(normalized, caller, ALLOWED_EXTS, describe_file)


@router.get("/health")
async def health():
    return ApiResponse(data={"module": "image-vision", "status": "ok"})


@router.post("/describe")
async def call_describe(payload: dict[str, object], user: User = Depends(require_permission("viewer"))):
    result = await _describe(payload, f"user:{user.id}")
    return ApiResponse(data=result)


register_capability(
    "image-vision", "describe", _describe,
    description="Analyze images locally first, then call the vision model only when semantic detail is needed",
    brief="低成本图片分析",
    parameters={
        "file_id": {"type": "int", "description": "File ID in file storage"},
        "analysis_mode": {
            "type": "string",
            "description": "auto | local | semantic. Defaults to auto.",
        },
        "prompt": {"type": "string", "description": "Optional semantic focus when VLM is used"},
    },
    min_role="viewer",
)
