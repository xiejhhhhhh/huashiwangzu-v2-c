"""原始层多轮采集服务。

对文档每页执行三轮独立采集（文本提取 / 截图OCR / 视觉构成），
每轮结果各自落盘到 kb_raw_data，落盘后只读不可变。

raw 节点只采集文本/OCR/VLM 结果。PDF/图片页面渲染和压缩由 page_render
节点提前沉淀为页面资产；raw_ocr/raw_vision 只读取这些资产。

Round-2 OCR 增强：在 VLM OCR 之外，若 tesseract 可用则额外提取词级
坐标落盘到 metadata_json.words，供 pdf-viewer 叠扫描件文字层。
"""
import asyncio
import gc
import hashlib
import io
import logging
from contextlib import contextmanager
from time import perf_counter

from app.database import AsyncSessionLocal
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ir_models import to_legacy_dict
from ..models import KbDocument, KbRawData
from .model_routing import (
    knowledge_model_call_slot,
    resolve_knowledge_concurrency,
    resolve_knowledge_image_preprocess_int,
    resolve_knowledge_vision_profile,
)
from .page_asset_service import load_page_asset_bytes
from .parsing_service import IMAGE_FORMATS, parse_document
from .pdf_render_service import get_pdf_page_count
from .prompt_utils import TRAW_OCR, TRAW_VISION, load_prompt

logger = logging.getLogger("v2.knowledge").getChild("raw_collection")

# tesseract 可用性检测
TESSERACT_AVAILABLE = False
try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    logger.info("pytesseract not installed; round-2 word coordinates disabled")

def _tesseract_has_binary() -> bool:
    import shutil
    return shutil.which("tesseract") is not None

def _ocr_words_tesseract(img_bytes: bytes) -> dict | None:
    """用 tesseract 提取词级坐标。返回 {"img_w","img_h","words"} 或 None。"""
    if not TESSERACT_AVAILABLE:
        return None
    if not _tesseract_has_binary():
        logger.info("tesseract binary not found; skip word coordinates")
        return None
    try:
        with Image.open(io.BytesIO(img_bytes)) as img:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, lang="chi_sim+eng")
            img_w, img_h = img.size
        words = []
        for i in range(len(data["text"])):
            t = (data["text"][i] or "").strip()
            if not t:
                continue
            words.append({
                "t": t,
                "x": int(data["left"][i]),
                "y": int(data["top"][i]),
                "w": int(data["width"][i]),
                "h": int(data["height"][i]),
            })
        logger.info("tesseract extracted %d words for image (%dx%d)", len(words), img_w, img_h)
        return {"img_w": img_w, "img_h": img_h, "words": words}
    except Exception as e:
        logger.warning("tesseract OCR failed: %s", e)
        return None


async def _ocr_words_tesseract_async(img_bytes: bytes) -> dict | None:
    """Run blocking tesseract OCR off the worker event loop."""
    prepared, preprocess = _prepare_image_bytes_for_local_ocr(img_bytes)
    result = await asyncio.to_thread(_ocr_words_tesseract, prepared)
    if result is not None:
        result["preprocess"] = preprocess
    return result

# 并发上限对齐 gate_pool.PER_GATE_MAX_CONCURRENT=5
RAW_COLLECT_CONCURRENCY = 5
DEFAULT_LOCAL_OCR_MAX_SIDE = 1600
DEFAULT_LOCAL_OCR_MAX_BYTES = 1_048_576
DEFAULT_LOCAL_OCR_JPEG_QUALITY_START = 84
DEFAULT_LOCAL_OCR_JPEG_QUALITY_FLOOR = 72
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_TEXT_CHUNKS = {b"tEXt", b"zTXt", b"iTXt"}
@contextmanager
def _allow_large_local_image_decode():
    """Allow trusted local enterprise images to open before we downscale them."""
    if not TESSERACT_AVAILABLE:
        yield
        return
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None
    try:
        yield
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit

def _hash_content(content: str) -> str:
    return hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()


def _clean_text_for_postgres(value: object) -> str:
    return str(value or "").replace("\x00", "").strip()


def _clean_json_for_postgres(value):
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {str(key).replace("\x00", ""): _clean_json_for_postgres(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_json_for_postgres(item) for item in value]
    if isinstance(value, tuple):
        return [_clean_json_for_postgres(item) for item in value]
    return value


def _strip_png_text_chunks(img_bytes: bytes) -> tuple[bytes, dict]:
    diagnostics = {
        "stripped": False,
        "removed_chunks": 0,
        "removed_bytes": 0,
        "original_bytes": len(img_bytes),
        "prepared_bytes": len(img_bytes),
    }
    if not img_bytes.startswith(PNG_SIGNATURE):
        return img_bytes, diagnostics
    output = bytearray(PNG_SIGNATURE)
    offset = len(PNG_SIGNATURE)
    try:
        while offset + 12 <= len(img_bytes):
            chunk_start = offset
            length = int.from_bytes(img_bytes[offset:offset + 4], "big")
            chunk_type = img_bytes[offset + 4:offset + 8]
            chunk_end = offset + 12 + length
            if chunk_end > len(img_bytes):
                return img_bytes, {**diagnostics, "error": "malformed_png_chunk"}
            if chunk_type in PNG_TEXT_CHUNKS:
                diagnostics["stripped"] = True
                diagnostics["removed_chunks"] += 1
                diagnostics["removed_bytes"] += chunk_end - chunk_start
            else:
                output.extend(img_bytes[chunk_start:chunk_end])
            offset = chunk_end
            if chunk_type == b"IEND":
                break
    except Exception as exc:
        return img_bytes, {**diagnostics, "error": str(exc)}
    prepared = bytes(output)
    diagnostics["prepared_bytes"] = len(prepared)
    return prepared, diagnostics


def _prepare_image_bytes_for_local_ocr(img_bytes: bytes) -> tuple[bytes, dict]:
    """Resize/re-encode local OCR input so huge images do not monopolize a worker lane."""
    metadata = {
        "original_bytes": len(img_bytes),
        "prepared_bytes": len(img_bytes),
        "resized": False,
        "reencoded": False,
    }
    if not TESSERACT_AVAILABLE:
        return img_bytes, metadata

    max_side = resolve_knowledge_image_preprocess_int(
        "raw_ocr_max_side",
        DEFAULT_LOCAL_OCR_MAX_SIDE,
        minimum=640,
        maximum=4096,
    )
    max_bytes = resolve_knowledge_image_preprocess_int(
        "raw_ocr_max_bytes",
        DEFAULT_LOCAL_OCR_MAX_BYTES,
        minimum=256 * 1024,
        maximum=32 * 1024 * 1024,
    )
    metadata["max_side"] = max_side
    metadata["max_bytes"] = max_bytes
    quality_start = resolve_knowledge_image_preprocess_int(
        "raw_ocr_jpeg_quality_start",
        DEFAULT_LOCAL_OCR_JPEG_QUALITY_START,
        minimum=40,
        maximum=95,
    )
    quality_floor = resolve_knowledge_image_preprocess_int(
        "raw_ocr_jpeg_quality_floor",
        DEFAULT_LOCAL_OCR_JPEG_QUALITY_FLOOR,
        minimum=40,
        maximum=quality_start,
    )
    quality_steps = [q for q in (quality_start, 78, quality_floor) if quality_floor <= q <= quality_start]
    qualities = sorted(set(quality_steps), reverse=True)
    metadata["jpeg_quality_start"] = quality_start
    metadata["jpeg_quality_floor"] = quality_floor

    cleaned_bytes, cleanup_info = _strip_png_text_chunks(img_bytes)
    if cleanup_info.get("stripped"):
        img_bytes = cleaned_bytes
        metadata["png_text_chunk_cleanup"] = cleanup_info

    try:
        with _allow_large_local_image_decode():
            with Image.open(io.BytesIO(img_bytes)) as image:
                original_format = (image.format or "").lower()
                metadata["original_size"] = [int(image.width), int(image.height)]
                working = image.copy()
    except Exception as exc:
        metadata["skipped_reason"] = f"unreadable_image:{exc}"
        return img_bytes, metadata

    longest = max(working.size)
    if longest > max_side:
        scale = max_side / longest
        next_size = (
            max(1, round(working.width * scale)),
            max(1, round(working.height * scale)),
        )
        working = working.resize(next_size, Image.Resampling.LANCZOS)
        metadata["resized"] = True
        metadata["prepared_size"] = [int(next_size[0]), int(next_size[1])]
    else:
        metadata["prepared_size"] = [int(working.width), int(working.height)]

    if not metadata["resized"] and len(img_bytes) <= max_bytes and original_format in {"jpeg", "jpg"}:
        working.close()
        return img_bytes, metadata

    if working.mode in {"RGBA", "LA"} or (working.mode == "P" and "transparency" in working.info):
        background = Image.new("RGB", working.size, (255, 255, 255))
        alpha = working.convert("RGBA").getchannel("A")
        background.paste(working.convert("RGBA"), mask=alpha)
        working = background
    elif working.mode != "RGB":
        working = working.convert("RGB")

    prepared = img_bytes
    selected_quality = qualities[-1]

    def encode_jpeg(quality: int) -> bytes:
        out = io.BytesIO()
        working.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()

    for quality in qualities:
        prepared = encode_jpeg(quality)
        selected_quality = quality
        if len(prepared) <= max_bytes:
            break

    metadata["prepared_bytes"] = len(prepared)
    metadata["prepared_size"] = [int(working.width), int(working.height)]
    metadata["jpeg_quality"] = selected_quality
    metadata["reencoded"] = True
    working.close()
    return prepared, metadata


def _vision_model_metadata(method: str, profile_key: str, result: dict | None = None) -> dict:
    diagnostics = (result or {}).get("diagnostics") or {}
    selected_profile = str(diagnostics.get("selected_profile") or profile_key)
    selected_provider = str(diagnostics.get("selected_provider") or "")
    model_degraded = bool(diagnostics.get("fallback_used")) and selected_profile != profile_key
    model_diagnostics = {
        "requested_profile": profile_key,
        "selected_profile": selected_profile,
        "selected_provider": selected_provider,
        "fallback_used": bool(diagnostics.get("fallback_used")),
    }
    if diagnostics.get("image_preprocess"):
        model_diagnostics["image_preprocess"] = diagnostics["image_preprocess"]
    return {
        "method": method,
        "provider": selected_provider,
        "profile_key": profile_key,
        "model_used": selected_profile,
        "model_degraded": model_degraded,
        "model_diagnostics": model_diagnostics,
    }


def classify_raw_collection_status(
    total_rounds: int,
    valid_rounds: int,
    failed_rounds: int,
    task_count: int,
    total_pages: int | None = None,
    valid_pages: int | None = None,
    primary_valid_pages: int | None = None,
) -> str:
    """根据有效内容统计判定 raw 阶段状态。"""
    if total_rounds > 0 and valid_rounds == 0:
        return "failed" if task_count > 0 and failed_rounds >= task_count else "degraded"
    if failed_rounds > 0:
        return "degraded"
    if total_pages is not None and valid_pages is not None:
        if primary_valid_pages is not None:
            if total_pages > 0 and primary_valid_pages == 0:
                return "degraded"
            if total_pages > primary_valid_pages:
                return "degraded"
            return "done"
        if total_pages > 0 and valid_pages == 0:
            return "degraded"
        if total_pages > valid_pages:
            return "degraded"
        return "done"
    if total_rounds > valid_rounds:
        return "degraded"
    return "done"


def completed_raw_pages(rows: list[tuple[int, str]], expected_rounds: int) -> set[int]:
    """Pages with every expected round completed successfully."""
    page_round_count: dict[int, int] = {}
    for page, status in rows:
        if status == "done":
            page_round_count[page] = page_round_count.get(page, 0) + 1
    return {page for page, count in page_round_count.items() if count >= expected_rounds}


def completed_raw_rounds(rows: list[tuple[int, int, str]]) -> set[tuple[int, int]]:
    """Individual (page, round) records that are already durable and reusable."""
    return {
        (int(page), int(round_num))
        for page, round_num, status in rows
        if status == "done"
    }


def summarize_raw_content_quality(
    rows: list[tuple[int, int, str, str, str, int | None, dict | None]],
    *,
    total_pages: int,
    expected_rounds: int,
    visual_document: bool,
) -> dict:
    """Summarize raw rows without treating empty OCR as primary content loss."""
    raw_contents = [content or "" for (_page, _round, _source, content, _status, _duration, _metadata) in rows]
    total_rounds = total_pages * expected_rounds
    valid_rounds = sum(1 for content in raw_contents if content.strip())
    valid_pages = len({
        page
        for (page, _round, _source, content, _status, _duration, _metadata) in rows
        if (content or "").strip()
    })
    primary_source_types = {"text", "vision"} if visual_document else {"text"}
    primary_valid_pages = len({
        page
        for (page, _round, source_type, content, status, _duration, _metadata) in rows
        if source_type in primary_source_types and status == "done" and (content or "").strip()
    })
    optional_empty_rounds = sum(
        1
        for (_page, _round, source_type, content, status, _duration, _metadata) in rows
        if visual_document
        and source_type == "ocr"
        and status != "failed"
        and not (content or "").strip()
    )
    return {
        "total_rounds": total_rounds,
        "valid_rounds": valid_rounds,
        "empty_rounds": max(total_rounds - valid_rounds, 0),
        "valid_pages": valid_pages,
        "empty_pages": max(total_pages - valid_pages, 0),
        "primary_valid_pages": primary_valid_pages,
        "primary_empty_pages": max(total_pages - primary_valid_pages, 0),
        "optional_empty_rounds": optional_empty_rounds,
    }


def _compact_raw_stage_results(results: list[dict], limit: int = 80) -> list[dict]:
    """Keep queue payloads small; durable per-page details live in kb_raw_data."""
    compacted: list[dict] = []
    for item in results[:limit]:
        compacted.append({
            "round": item.get("round"),
            "page": item.get("page"),
            "chars": item.get("chars"),
            "status": item.get("status"),
            "duration_ms": item.get("duration_ms"),
            "processor": item.get("processor"),
            "error": item.get("error"),
            "model_degraded": bool(item.get("model_degraded")),
        })
    return compacted


def _compact_page_asset_metadata(metadata: dict | None) -> dict:
    if not isinstance(metadata, dict):
        return {}
    preprocess = metadata.get("vlm_image_preprocess") or {}
    return {
        "storage_path": metadata.get("storage_path"),
        "mime_type": metadata.get("mime_type"),
        "byte_size": metadata.get("byte_size"),
        "image_bytes_md5": metadata.get("image_bytes_md5"),
        "preprocess_version": preprocess.get("preprocess_version"),
        "prepared_bytes": preprocess.get("prepared_bytes"),
        "prepared_size": preprocess.get("prepared_size"),
    }


async def _exec_round_1_text(
    doc_id: int, file_id: int, owner_id: int,
    page: int, caller: str, ext: str = "pdf",
    page_text_map: dict[int, str] | None = None,
    preparse_error: str = "",
) -> dict:
    """第1轮：文本提取。独立 DB 会话，单独 commit。"""
    started = perf_counter()
    error_message = ""
    try:
        if preparse_error:
            raise RuntimeError(preparse_error)
        if page_text_map is not None:
            content = page_text_map.get(page, "")
        else:
            parsed = to_legacy_dict(await parse_document(file_id, ext, caller))
            blocks = parsed.get("blocks", [])
            page_texts = [
                (b.get("text") or "").strip()
                for b in blocks
                if (b.get("page") == page or (page == 1 and b.get("page") is None))
                and (b.get("text") or "").strip()
            ]
            content = "\n\n".join(page_texts)
    except Exception as e:
        logger.warning("Round 1 text extraction failed for doc_id=%d page=%d: %s", doc_id, page, e)
        content = ""
        error_message = str(e)

    duration_ms = round((perf_counter() - started) * 1000)
    content = _clean_text_for_postgres(content)
    error_message = _clean_text_for_postgres(error_message)
    status = "done" if content else ("failed" if error_message else "degraded")
    record = KbRawData(
        document_id=doc_id,
        file_id=file_id,
        owner_id=owner_id,
        page=page,
        round=1,
        source_type="text",
        content=content,
        model_used="parser",
        confidence=0.95 if content else 0.0,
        content_hash=_hash_content(content),
        status=status,
        error_message=error_message or None,
        duration_ms=duration_ms,
    )
    async with AsyncSessionLocal() as task_db:
        task_db.add(record)
        await task_db.commit()
    logger.info("Raw collection round=1 page=%d done (%d chars)", page, len(content))
    return {
        "round": 1,
        "page": page,
        "chars": len(content),
        "status": status,
        "duration_ms": duration_ms,
        "processor": "local_parser",
    }


async def _build_page_text_map(file_id: int, ext: str, caller: str) -> tuple[dict[int, str], str]:
    """Parse the source once and split parser text blocks by page."""
    page_texts: dict[int, list[str]] = {}
    try:
        parsed = to_legacy_dict(await parse_document(file_id, ext, caller))
        for block in parsed.get("blocks", []):
            text = (block.get("text") or "").strip()
            if not text:
                continue
            page = int(block.get("page") or 1)
            page_texts.setdefault(page, []).append(text)
    except Exception as exc:
        return {}, str(exc)
    return {
        page: "\n\n".join(texts)
        for page, texts in page_texts.items()
    }, ""


async def _exec_round_2_ocr(
    doc_id: int, file_id: int, owner_id: int,
    page: int, user_id: int,
    img_bytes: bytes | None = None,
    mime_type: str = "image/png",
) -> dict:
    """第2轮：截图 OCR。独立 DB 会话，单独 commit。

    优先用 tesseract 出文本+词坐标（方案①：一趟出）。
    若 tesseract 不可用则回退到 VLM OCR（仅文本）。
    """
    from app.services.model_services import describe_image_detailed

    started = perf_counter()
    error_message = ""
    profile_key = resolve_knowledge_vision_profile("raw_ocr")
    content = ""
    metadata: dict = _vision_model_metadata("vlm_ocr", profile_key)
    try:
        if img_bytes is None:
            raise RuntimeError("page_asset_required_for_raw_ocr")

        # 方案①：优先 tesseract——一趟出文本+词坐标
        tesseract_result = await _ocr_words_tesseract_async(img_bytes)
        if tesseract_result is not None:
            # 从词坐标组装纯文本
            words = tesseract_result.get("words", [])
            content = " ".join(w["t"] for w in words)
            metadata = {
                "method": "tesseract_boxes",
                "provider": "tesseract",
                "img_w": tesseract_result["img_w"],
                "img_h": tesseract_result["img_h"],
                "words": words,
                "image_preprocess": tesseract_result.get("preprocess") or {},
            }
        else:
            # 回退：纯 VLM OCR（不产生词坐标）
            async with AsyncSessionLocal() as task_db:
                prompt = await load_prompt(task_db, TRAW_OCR, release_transaction=True)
            async with knowledge_model_call_slot("raw_ocr"):
                result = await describe_image_detailed(
                    img_bytes,
                    prompt=prompt,
                    mime_type=mime_type,
                    profile_key=profile_key,
                )
            content = str(result.get("content") or "")
            metadata = _vision_model_metadata("vlm_ocr", profile_key, result)
    except Exception as e:
        logger.warning("Round 2 OCR failed for doc_id=%d page=%d: %s", doc_id, page, e)
        content = ""
        metadata = _vision_model_metadata("vlm_ocr", profile_key)
        error_message = str(e)

    duration_ms = round((perf_counter() - started) * 1000)
    content = _clean_text_for_postgres(content)
    error_message = _clean_text_for_postgres(error_message)
    metadata = _clean_json_for_postgres(metadata)
    status = "done" if content else ("failed" if error_message else "degraded")
    record = KbRawData(
        document_id=doc_id,
        file_id=file_id,
        owner_id=owner_id,
        page=page,
        round=2,
        source_type="ocr",
        content=content,
        model_used="tesseract" if metadata.get("provider") == "tesseract" else str(metadata.get("model_used") or profile_key),
        confidence=0.85 if content else 0.0,
        content_hash=_hash_content(content),
        metadata_json=metadata,
        status=status,
        error_message=error_message or None,
        duration_ms=duration_ms,
    )
    async with AsyncSessionLocal() as task_db:
        task_db.add(record)
        await task_db.commit()
    img_bytes = None
    gc.collect()
    logger.info("Raw collection round=2 page=%d done (%d chars, %d words)",
                 page, len(content),
                 len(metadata.get("words", [])))
    return {
        "round": 2,
        "page": page,
        "chars": len(content),
        "status": status,
        "duration_ms": duration_ms,
        "processor": metadata.get("provider") or "vlm",
        "model_degraded": bool(metadata.get("model_degraded")),
        "model_diagnostics": metadata.get("model_diagnostics") or {},
    }


async def _exec_round_3_vision(
    doc_id: int, file_id: int, owner_id: int,
    page: int, user_id: int,
    img_bytes: bytes | None = None,
    mime_type: str = "image/png",
) -> dict:
    """第3轮：视觉构成。独立 DB 会话，单独 commit。"""
    from app.services.model_services import describe_image_detailed

    started = perf_counter()
    error_message = ""
    profile_key = resolve_knowledge_vision_profile("raw_vision")
    metadata = _vision_model_metadata("vlm_vision", profile_key)
    try:
        if img_bytes is None:
            raise RuntimeError("page_asset_required_for_raw_vision")
        async with AsyncSessionLocal() as task_db:
            prompt = await load_prompt(task_db, TRAW_VISION, release_transaction=True)
        async with knowledge_model_call_slot("raw_vision"):
            result = await describe_image_detailed(
                img_bytes,
                prompt=prompt,
                mime_type=mime_type,
                profile_key=profile_key,
            )
        content = str(result.get("content") or "")
        metadata = _vision_model_metadata("vlm_vision", profile_key, result)
    except Exception as e:
        logger.warning("Round 3 vision failed for doc_id=%d page=%d: %s", doc_id, page, e)
        content = ""
        error_message = str(e)

    duration_ms = round((perf_counter() - started) * 1000)
    content = _clean_text_for_postgres(content)
    error_message = _clean_text_for_postgres(error_message)
    metadata = _clean_json_for_postgres(metadata)
    status = "done" if content else ("failed" if error_message else "degraded")
    record = KbRawData(
        document_id=doc_id,
        file_id=file_id,
        owner_id=owner_id,
        page=page,
        round=3,
        source_type="vision",
        content=content,
        model_used=str(metadata.get("model_used") or profile_key),
        confidence=0.80 if content else 0.0,
        content_hash=_hash_content(content),
        metadata_json=metadata,
        status=status,
        error_message=error_message or None,
        duration_ms=duration_ms,
    )
    async with AsyncSessionLocal() as task_db:
        task_db.add(record)
        await task_db.commit()
    img_bytes = None
    gc.collect()
    logger.info("Raw collection round=3 page=%d done (%d chars)", page, len(content))
    return {
        "round": 3,
        "page": page,
        "chars": len(content),
        "status": status,
        "duration_ms": duration_ms,
        "processor": metadata.get("provider") or "vlm",
        "model_degraded": bool(metadata.get("model_degraded")),
        "model_diagnostics": metadata.get("model_diagnostics") or {},
    }


async def collect_raw_stage(
    db: AsyncSession,
    doc_id: int,
    owner_id: int,
    file_id: int,
    user_id: int,
    stage: str,
) -> dict:
    """Run one explicit raw node for DAG queue execution."""
    caller = f"user:{user_id}"
    stage_started = perf_counter()
    stage_to_round = {
        "raw_text": 1,
        "raw_ocr": 2,
        "raw_vision": 3,
    }
    round_num = stage_to_round.get(stage)
    if round_num is None:
        return {"document_id": doc_id, "stage": stage, "status": "failed", "error": "unknown_raw_stage"}

    doc = await db.scalar(select(KbDocument).where(KbDocument.id == doc_id))
    if not doc:
        return {"document_id": doc_id, "stage": stage, "status": "skipped", "reason": "doc_missing"}

    ext = (doc.extension or "").lower()
    is_pdf = ext == "pdf"
    is_image = ext in IMAGE_FORMATS
    if round_num in {2, 3} and not (is_pdf or is_image):
        return {
            "document_id": doc_id,
            "stage": stage,
            "round": round_num,
            "status": "skipped",
            "reason": "round_not_required_for_file_type",
        }

    if is_pdf:
        try:
            total_pages = await get_pdf_page_count(file_id, user_id)
        except Exception:
            total_pages = doc.total_pages or 1
    else:
        total_pages = doc.total_pages or 1
    doc.total_pages = total_pages
    if doc.raw_status in {"pending", "", None}:
        doc.raw_status = "collecting"
    await db.commit()

    existing_rows = await db.execute(
        select(KbRawData.page, KbRawData.round, KbRawData.status).where(
            KbRawData.document_id == doc_id,
            KbRawData.round == round_num,
        )
    )
    done_rounds = completed_raw_rounds(existing_rows.all())
    await db.commit()
    for page in range(1, total_pages + 1):
        if (page, round_num) in done_rounds:
            continue
        async with AsyncSessionLocal() as clean_db:
            await clean_db.execute(
                sa_delete(KbRawData).where(
                    KbRawData.document_id == doc_id,
                    KbRawData.page == page,
                    KbRawData.round == round_num,
                )
            )
            await clean_db.commit()

    page_text_map: dict[int, str] | None = None
    preparse_error = ""
    text_parse_duration_ms = 0
    page_asset_wait_ms = 0

    if round_num == 1 and any((page, 1) not in done_rounds for page in range(1, total_pages + 1)):
        text_parse_started = perf_counter()
        page_text_map, preparse_error = await _build_page_text_map(file_id, ext, caller)
        text_parse_duration_ms = round((perf_counter() - text_parse_started) * 1000)
        if preparse_error:
            logger.warning("Raw stage text map failed for doc_id=%d: %s", doc_id, preparse_error)

    raw_collect_concurrency = resolve_knowledge_concurrency(
        stage,
        resolve_knowledge_concurrency("raw_collect", RAW_COLLECT_CONCURRENCY),
        maximum=256 if round_num == 1 else 64,
    )
    sem = asyncio.Semaphore(raw_collect_concurrency)
    tasks = []

    async def _task_wrapper(page: int) -> dict:
        nonlocal page_asset_wait_ms
        async with sem:
            if round_num == 1:
                return await _exec_round_1_text(
                    doc_id,
                    file_id,
                    owner_id,
                    page,
                    caller,
                    ext=ext,
                    page_text_map=page_text_map,
                    preparse_error=preparse_error,
                )
            if round_num == 2:
                asset_started = perf_counter()
                async with AsyncSessionLocal() as asset_db:
                    asset = await load_page_asset_bytes(asset_db, document_id=doc_id, page=page)
                page_asset_wait_ms += round((perf_counter() - asset_started) * 1000)
                if asset is None:
                    return {"round": 2, "page": page, "status": "failed", "error": "page_asset_missing"}
                img_bytes, _mime_type, asset_metadata = asset
                result = await _exec_round_2_ocr(
                    doc_id,
                    file_id,
                    owner_id,
                    page,
                    user_id,
                    img_bytes=img_bytes,
                    mime_type=_mime_type,
                )
                result["page_asset"] = _compact_page_asset_metadata(asset_metadata)
                return result
            asset_started = perf_counter()
            async with AsyncSessionLocal() as asset_db:
                asset = await load_page_asset_bytes(asset_db, document_id=doc_id, page=page)
            page_asset_wait_ms += round((perf_counter() - asset_started) * 1000)
            if asset is None:
                return {"round": 3, "page": page, "status": "failed", "error": "page_asset_missing"}
            img_bytes, mime_type, asset_metadata = asset
            result = await _exec_round_3_vision(
                doc_id,
                file_id,
                owner_id,
                page,
                user_id,
                img_bytes=img_bytes,
                mime_type=mime_type,
            )
            result["page_asset"] = _compact_page_asset_metadata(asset_metadata)
            return result

    for page in range(1, total_pages + 1):
        if (page, round_num) in done_rounds:
            continue
        tasks.append(_task_wrapper(page))

    task_wall_started = perf_counter()
    all_results: list[dict] = []
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for item in results:
            if isinstance(item, Exception):
                logger.warning("Raw stage task failed stage=%s: %s", stage, item)
                all_results.append({"status": "failed", "error": str(item)})
            else:
                all_results.append(item)
    task_wall_duration_ms = round((perf_counter() - task_wall_started) * 1000)

    full_expected_rounds = 3 if (is_pdf or is_image) else 1
    raw_rows = await db.execute(
        select(
            KbRawData.page,
            KbRawData.round,
            KbRawData.source_type,
            KbRawData.content,
            KbRawData.status,
            KbRawData.duration_ms,
            KbRawData.metadata_json,
        ).where(KbRawData.document_id == doc_id)
    )
    raw_result_rows = raw_rows.all()
    quality = summarize_raw_content_quality(
        raw_result_rows,
        total_pages=total_pages,
        expected_rounds=full_expected_rounds,
        visual_document=is_pdf or is_image,
    )
    completed_round_rows = {
        (int(page), int(row_round))
        for page, row_round, _source, _content, status, _duration, _metadata in raw_result_rows
        if status in {"done", "degraded"}
    }
    required_rounds = [1, 2, 3] if (is_pdf or is_image) else [1]
    raw_complete = all(
        (page, required_round) in completed_round_rows
        for page in range(1, total_pages + 1)
        for required_round in required_rounds
    )
    failed_count = sum(1 for item in all_results if item.get("status") == "failed" or item.get("error"))
    await db.refresh(doc)
    if raw_complete:
        doc.raw_status = classify_raw_collection_status(
            total_rounds=int(quality["total_rounds"]),
            valid_rounds=int(quality["valid_rounds"]),
            failed_rounds=failed_count,
            task_count=len(tasks),
            total_pages=total_pages,
            valid_pages=int(quality["valid_pages"]),
            primary_valid_pages=int(quality["primary_valid_pages"]),
        )
    elif failed_count:
        doc.raw_status = "degraded"
    else:
        doc.raw_status = "collecting"
    await db.commit()

    return {
        "document_id": doc_id,
        "stage": stage,
        "round": round_num,
        "status": "done" if not failed_count else "degraded",
        "raw_complete": raw_complete,
        "total_pages": total_pages,
        "rounds": _compact_raw_stage_results(all_results),
        "round_result_count": len(all_results),
        "round_results_truncated": len(all_results) > 80,
        "total_rounds": int(quality["total_rounds"]),
        "valid_rounds": int(quality["valid_rounds"]),
        "empty_rounds": int(quality["empty_rounds"]),
        "valid_pages": int(quality["valid_pages"]),
        "primary_empty_pages": int(quality["primary_empty_pages"]),
        "failed_rounds": failed_count,
        "model_degraded": any(item.get("model_degraded") for item in all_results),
        "model_diagnostics": [
            item.get("model_diagnostics")
            for item in all_results
            if item.get("model_degraded") and item.get("model_diagnostics")
        ],
        "timing": {
            "stage_wall_ms": round((perf_counter() - stage_started) * 1000),
            "text_parse_ms": text_parse_duration_ms,
            "page_asset_read_ms": page_asset_wait_ms,
            "task_wall_ms": task_wall_duration_ms,
            "raw_stage_concurrency": raw_collect_concurrency,
            "skipped_rounds": [
                {"page": page, "round": existing_round}
                for page, existing_round in sorted(done_rounds)
                if existing_round == round_num
            ],
        },
    }


async def get_raw_data(
    db: AsyncSession, document_id: int, page: int | None = None,
    round_num: int | None = None,
) -> list[dict]:
    """查询原始采集数据。

    返回: [{"id": int, "page": int, "round": int, "source_type": str, "content": str, ...}, ...]
    """
    stmt = select(KbRawData).where(KbRawData.document_id == document_id)
    if page is not None:
        stmt = stmt.where(KbRawData.page == page)
    if round_num is not None:
        stmt = stmt.where(KbRawData.round == round_num)
    stmt = stmt.order_by(KbRawData.page, KbRawData.round)

    r = await db.execute(stmt)
    records = r.scalars().all()
    return [
        {
            "id": rec.id,
            "page": rec.page,
            "round": rec.round,
            "source_type": rec.source_type,
            "content": rec.content,
            "model_used": rec.model_used,
            "confidence": rec.confidence,
            "content_hash": rec.content_hash,
            "status": getattr(rec, "status", "done"),
            "error_message": getattr(rec, "error_message", None),
            "duration_ms": getattr(rec, "duration_ms", None),
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        }
        for rec in records
    ]


async def get_ocr_words(
    db: AsyncSession, file_id: int, page: int, owner_id: int,
) -> dict:
    """获取指定文件某页的 OCR 词坐标（供 pdf-viewer 跨模块调用）。

    从 round-2 原始采集记录的 metadata_json 读 words + img_w/img_h。
    若该文件尚未被知识库采集 / 该页不是 tesseract OCR → 返回空。
    """
    # 先查文档
    dr = await db.execute(
        select(KbDocument).where(
            KbDocument.file_id == file_id,
            KbDocument.owner_id == owner_id,
            KbDocument.deleted.is_(False),
        )
    )
    doc = dr.scalar_one_or_none()
    if not doc:
        return {"words": [], "img_w": 0, "img_h": 0}

    rr = await db.execute(
        select(KbRawData).where(
            KbRawData.document_id == doc.id,
            KbRawData.page == page,
            KbRawData.round == 2,
        ).order_by(KbRawData.id.desc()).limit(1)
    )
    rec = rr.scalar_one_or_none()
    if not rec or not rec.metadata_json:
        return {"words": [], "img_w": 0, "img_h": 0}

    meta = rec.metadata_json
    words = meta.get("words", [])
    return {
        "words": words,
        "img_w": meta.get("img_w", 0),
        "img_h": meta.get("img_h", 0),
    }
