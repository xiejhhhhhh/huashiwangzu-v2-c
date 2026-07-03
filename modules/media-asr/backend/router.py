import time
from pathlib import Path
from typing import Any, Optional

from app.core.exceptions import AppException, ValidationError
from app.database import AsyncSessionLocal
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.file_reader import resolve_caller_user_id
from app.services.file_upload_service import upload_file_from_path
from app.services.module_registry import register_capability
from app.services.uploaded_file_runner import run_uploaded_file_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .services.audio_service import (
    build_segment_blocks,
    copy_temp_file,
    extract_audio_from_video,
    normalize_language,
    transcribe_audio_file,
    validate_audio_format,
    validate_sample_rate,
    validate_whisper_model,
)

router = APIRouter(prefix="/api/media-asr", tags=["media-asr"])

VIDEO_EXTS = {"mp4", "mov", "m4v", "webm", "mkv", "avi"}
AUDIO_EXTS = {"wav", "mp3", "m4a", "aac", "flac", "ogg"}


# ── Request Schemas ────────────────────────────────────────────────

class ExtractAudioRequest(BaseModel):
    file_id: int
    sample_rate: int = 16000
    audio_format: str = "wav"
    save_file: bool = True
    folder_id: Optional[int] = None


class TranscribeAudioRequest(BaseModel):
    file_id: int
    model: str = "large-v3"
    language: Optional[str] = None
    save_text: bool = False
    folder_id: Optional[int] = None


class TranscribeVideoRequest(BaseModel):
    file_id: int
    model: str = "large-v3"
    sample_rate: int = 16000
    language: Optional[str] = None
    save_audio: bool = False
    save_text: bool = False
    folder_id: Optional[int] = None


# ── Capability Implementations ────────────────────────────────────

async def _extract_audio(params: dict, caller: str) -> dict:
    file_id = _required_positive_int(params, "file_id")
    sample_rate = validate_sample_rate(_int_param(params, "sample_rate", 16000))
    audio_format = validate_audio_format(str(params.get("audio_format") or "wav"))
    save_file = _as_bool(params.get("save_file", True), True)
    folder_id = _optional_positive_int(params.get("folder_id"), "folder_id")
    checked_params = {**params, "file_id": file_id}

    user_id = resolve_caller_user_id(caller)

    async def handler(file_id, file, full_path, ext):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            result = await extract_audio_from_video(
                full_path, tmp_path, sample_rate, audio_format,
            )
            audio_path = result["audio_path"]

            audio_file_id = None
            if save_file:
                source_stem = Path(file.name).stem if file.name else f"video_{file_id}"
                audio_filename = f"{source_stem}-audio.{audio_format}"
                audio_file_id = await _upload_with_conflict_retry(
                    audio_path, audio_filename, user_id, folder_id,
                )

            return {
                "source_file_id": file_id,
                "audio_file_id": audio_file_id,
                "audio_format": audio_format,
                "sample_rate": sample_rate,
                "duration_seconds": result.get("duration_seconds"),
                "size": result["size"],
                "blocks": [],
                "resources": [{"id": 1, "type": "video", "file_storage_id": file_id}],
            }

    return await run_uploaded_file_capability(checked_params, caller, VIDEO_EXTS, handler)


async def _transcribe_audio(params: dict, caller: str) -> dict:
    file_id = _required_positive_int(params, "file_id")
    model = validate_whisper_model(str(params.get("model") or "large-v3"))
    language = normalize_language(params.get("language"))
    save_text = _as_bool(params.get("save_text", False), False)
    folder_id = _optional_positive_int(params.get("folder_id"), "folder_id")
    checked_params = {**params, "file_id": file_id}

    user_id = resolve_caller_user_id(caller)

    async def handler(file_id, file, full_path, ext):
        result = await transcribe_audio_file(full_path, model, language)
        text = result["text"]
        segments = result["segments"]
        blocks = build_segment_blocks(segments)

        text_file_id = None
        if save_text:
            source_stem = Path(file.name).stem if file.name else f"audio_{file_id}"
            txt_filename = f"{source_stem}-transcript.txt"
            import tempfile

            with tempfile.TemporaryDirectory() as tmp_dir:
                txt_path = Path(tmp_dir) / txt_filename
                txt_path.write_text(text, encoding="utf-8")
                text_file_id = await _upload_with_conflict_retry(
                    txt_path, txt_filename, user_id, folder_id,
                )

        return {
            "file_id": file_id,
            "format": ext,
            "model": model,
            "text": text,
            "segments": segments,
            "blocks": blocks,
            "resources": [{"id": 1, "type": "audio", "file_storage_id": file_id}],
            "metadata": {
                "segment_count": len(segments),
                "text_file_id": text_file_id,
                "duration_seconds": result.get("duration_seconds"),
            },
        }

    return await run_uploaded_file_capability(checked_params, caller, AUDIO_EXTS, handler)


async def _transcribe_video(params: dict, caller: str) -> dict:
    file_id = _required_positive_int(params, "file_id")
    model = validate_whisper_model(str(params.get("model") or "large-v3"))
    sample_rate = validate_sample_rate(_int_param(params, "sample_rate", 16000))
    language = normalize_language(params.get("language"))
    save_audio = _as_bool(params.get("save_audio", False), False)
    save_text = _as_bool(params.get("save_text", False), False)
    folder_id = _optional_positive_int(params.get("folder_id"), "folder_id")
    checked_params = {**params, "file_id": file_id}

    user_id = resolve_caller_user_id(caller)

    async def handler(file_id, file, full_path, ext):
        import tempfile

        audio_format = "wav"
        audio_file_id = None
        text_file_id = None

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            extract_result = await extract_audio_from_video(
                full_path, tmp_path, sample_rate, audio_format,
            )
            audio_path = extract_result["audio_path"]

            if save_audio:
                source_stem = Path(file.name).stem if file.name else f"video_{file_id}"
                audio_filename = f"{source_stem}-audio.{audio_format}"
                upload_audio_path = copy_temp_file(audio_path, tmp_path, f"upload-{audio_filename}")
                audio_file_id = await _upload_with_conflict_retry(
                    upload_audio_path, audio_filename, user_id, folder_id,
                )

            transcribe_result = await transcribe_audio_file(
                audio_path, model, language,
            )
            text = transcribe_result["text"]
            segments = transcribe_result["segments"]
            blocks = build_segment_blocks(segments)

            if save_text:
                source_stem = Path(file.name).stem if file.name else f"video_{file_id}"
                txt_filename = f"{source_stem}-transcript.txt"
                txt_path = tmp_path / txt_filename
                txt_path.write_text(text, encoding="utf-8")
                text_file_id = await _upload_with_conflict_retry(
                    txt_path, txt_filename, user_id, folder_id,
                )

        return {
            "source_file_id": file_id,
            "audio_file_id": audio_file_id,
            "text_file_id": text_file_id,
            "model": model,
            "text": text,
            "segments": segments,
            "blocks": blocks,
            "resources": [{"id": 1, "type": "video", "file_storage_id": file_id}],
            "metadata": {
                "segment_count": len(segments),
                "sample_rate": sample_rate,
                "duration_seconds": transcribe_result.get("duration_seconds"),
            },
        }

    return await run_uploaded_file_capability(checked_params, caller, VIDEO_EXTS, handler)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off", ""}:
            return False
    return bool(value)


def _int_param(params: dict, name: str, default: int) -> int:
    value = params.get(name, default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must be an integer") from exc


def _required_positive_int(params: dict, name: str) -> int:
    if params.get(name) in (None, ""):
        raise ValidationError(f"{name} is required")
    value = _int_param(params, name, 0)
    if value <= 0:
        raise ValidationError(f"{name} must be a positive integer")
    return value


def _optional_positive_int(value: Any, name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValidationError(f"{name} must be a positive integer")
    return parsed


async def _upload_with_conflict_retry(
    file_path: Path,
    filename: str,
    owner_id: int,
    folder_id: Optional[int] = None,
) -> int:
    async with AsyncSessionLocal() as db:
        try:
            result = await upload_file_from_path(
                db, file_path, filename, owner_id=owner_id,
                folder_id=folder_id,
            )
            return result["id"]
        except AppException as exc:
            if "already exists" in str(exc):
                name_part, ext_part = filename.rsplit(".", 1) if "." in filename else (filename, "")
                alt_filename = f"{name_part}-{int(time.time())}.{ext_part}" if ext_part else f"{name_part}-{int(time.time())}"
                result = await upload_file_from_path(
                    db, file_path, alt_filename, owner_id=owner_id,
                    folder_id=folder_id,
                )
                return result["id"]
            raise


# ── HTTP Endpoints ────────────────────────────────────────────────

@router.get("/health")
async def health():
    return ApiResponse(data={"module": "media-asr", "status": "ok"})


@router.post("/extract-audio")
async def call_extract_audio(
    payload: ExtractAudioRequest,
    user: User = Depends(require_permission("editor")),
):
    params = payload.model_dump()
    result = await _extract_audio(params, f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/transcribe-audio")
async def call_transcribe_audio(
    payload: TranscribeAudioRequest,
    user: User = Depends(require_permission("editor")),
):
    params = payload.model_dump()
    result = await _transcribe_audio(params, f"user:{user.id}")
    return ApiResponse(data=result)


@router.post("/transcribe-video")
async def call_transcribe_video(
    payload: TranscribeVideoRequest,
    user: User = Depends(require_permission("editor")),
):
    params = payload.model_dump()
    result = await _transcribe_video(params, f"user:{user.id}")
    return ApiResponse(data=result)


# ── Capability Registration ──────────────────────────────────────

register_capability(
    "media-asr", "extract_audio", _extract_audio,
    description="Extract audio track from an uploaded video file, optionally save as a framework file",
    brief="提取视频音频",
    parameters={
        "file_id": {"type": "int", "description": "Source video file ID"},
        "sample_rate": {"type": "int", "description": "Output sample rate (default 16000)"},
        "audio_format": {"type": "string", "description": "Output audio format: wav/mp3/m4a/flac/ogg (default wav)"},
        "save_file": {"type": "bool", "description": "Save audio as a framework file (default true)"},
        "folder_id": {"type": "int", "description": "Target folder ID for saved audio"},
    },
    min_role="editor",
)

register_capability(
    "media-asr", "transcribe_audio", _transcribe_audio,
    description="Transcribe an audio file into timestamped text using mlx_whisper",
    brief="音频转文字",
    parameters={
        "file_id": {"type": "int", "description": "Audio file ID"},
        "model": {"type": "string", "description": "Whisper model: tiny/small/medium/large/large-v2/large-v3/turbo (default large-v3)"},
        "language": {"type": "string", "description": "Language hint (optional, e.g. zh, en)"},
        "save_text": {"type": "bool", "description": "Save transcript as a framework text file (default false)"},
        "folder_id": {"type": "int", "description": "Target folder ID for saved transcript"},
    },
    min_role="editor",
)

register_capability(
    "media-asr", "transcribe_video", _transcribe_video,
    description="Extract audio from a video and transcribe it to timestamped text in one step",
    brief="视频转文字",
    parameters={
        "file_id": {"type": "int", "description": "Source video file ID"},
        "model": {"type": "string", "description": "Whisper model: tiny/small/medium/large/large-v2/large-v3/turbo (default large-v3)"},
        "sample_rate": {"type": "int", "description": "Audio extraction sample rate (default 16000)"},
        "language": {"type": "string", "description": "Language hint (optional)"},
        "save_audio": {"type": "bool", "description": "Save extracted audio as a framework file (default false)"},
        "save_text": {"type": "bool", "description": "Save transcript as a framework text file (default false)"},
        "folder_id": {"type": "int", "description": "Target folder ID for saved files"},
    },
    min_role="editor",
)
