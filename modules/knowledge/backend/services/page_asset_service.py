"""Durable page-image asset materialization for knowledge visual stages."""
from __future__ import annotations

import asyncio
import gc
import hashlib
import os
from pathlib import Path
from time import perf_counter

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.gateway.vision_preprocess import (
    VISION_IMAGE_PREPROCESS_VERSION,
    prepare_vision_image_for_model_from_config,
)
from app.services.file_service import check_file_access
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbDocument, KbImageAsset
from .image_similarity_service import IMAGE_HASH_SCHEMA_VERSION, compute_image_fingerprints
from .model_routing import resolve_knowledge_concurrency
from .parsing_service import IMAGE_FORMATS
from .pdf_render_service import get_pdf_page_count, render_page_to_image

PAGE_ASSET_SCHEMA_VERSION = "kb_page_asset_v1"
PAGE_ASSET_ROOT = "knowledge_page_assets"
IMAGE_MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "svg": "image/svg+xml",
}


def _mime_type_for_extension(ext: str) -> str:
    return IMAGE_MIME_TYPES.get(ext.lower().lstrip("."), "image/jpeg")


def _asset_ext(mime_type: str) -> str:
    if mime_type == "image/png":
        return "png"
    if mime_type == "image/webp":
        return "webp"
    return "jpg"


def _upload_root() -> Path:
    return Path(get_settings().UPLOAD_DIR).resolve()


def _asset_storage_path(owner_id: int, document_id: int, page: int, md5_value: str, mime_type: str) -> str:
    ext = _asset_ext(mime_type)
    return f"{PAGE_ASSET_ROOT}/{owner_id}/{document_id}/page-{page:05d}-{md5_value}.{ext}"


def _asset_file_available(storage_path: str | None) -> bool:
    if not storage_path:
        return False
    upload_root = _upload_root()
    abs_path = (upload_root / storage_path).resolve()
    return os.path.commonpath([str(upload_root), str(abs_path)]) == str(upload_root) and abs_path.exists()


async def _read_source_image_bytes(file_id: int, user_id: int) -> tuple[bytes, str]:
    async with AsyncSessionLocal() as db:
        file_rec = await check_file_access(db, file_id, user_id)
    upload_root = _upload_root()
    full_path = (upload_root / file_rec.storage_path).resolve()
    if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root):
        raise ValueError("Unsafe file storage path")
    return full_path.read_bytes(), _mime_type_for_extension(Path(file_rec.storage_path).suffix.lstrip("."))


async def _existing_page_asset(db: AsyncSession, *, document_id: int, page: int) -> KbImageAsset | None:
    asset = await db.scalar(
        select(KbImageAsset)
        .where(
            KbImageAsset.document_id == int(document_id),
            KbImageAsset.page == int(page),
            KbImageAsset.status == "active",
            KbImageAsset.storage_path.is_not(None),
            KbImageAsset.hash_schema_version == IMAGE_HASH_SCHEMA_VERSION,
        )
        .order_by(KbImageAsset.id.desc())
        .limit(1)
    )
    if asset is None or not _asset_file_available(asset.storage_path):
        return None
    diagnostics = asset.diagnostics_json or {}
    if diagnostics.get("schema_version") != PAGE_ASSET_SCHEMA_VERSION:
        return None
    if (diagnostics.get("vlm_image_preprocess") or {}).get("preprocess_version") not in {None, VISION_IMAGE_PREPROCESS_VERSION}:
        return None
    return asset


async def page_assets_complete(db: AsyncSession, *, document_id: int, total_pages: int | None) -> bool:
    """Return whether every expected visual page has a reusable local asset."""
    expected_pages = max(int(total_pages or 1), 1)
    for page in range(1, expected_pages + 1):
        if await _existing_page_asset(db, document_id=document_id, page=page) is None:
            return False
    return True


def _prepare_page_asset_bytes(image_bytes: bytes, mime_type: str) -> tuple[bytes, str, dict]:
    prepared, prepared_mime, metadata = prepare_vision_image_for_model_from_config(image_bytes, mime_type)
    metadata["stage"] = "knowledge_page_render"
    metadata["schema_version"] = PAGE_ASSET_SCHEMA_VERSION
    metadata["preprocess_version"] = VISION_IMAGE_PREPROCESS_VERSION
    metadata["source_original_md5"] = metadata.get("original_md5") or hashlib.md5(image_bytes).hexdigest()
    metadata["source_prepared_md5"] = metadata.get("prepared_md5") or hashlib.md5(prepared).hexdigest()
    return prepared, prepared_mime, metadata


async def _upsert_page_asset(
    db: AsyncSession,
    *,
    owner_id: int,
    document_id: int,
    file_id: int,
    page: int,
    image_bytes: bytes,
    mime_type: str,
    asset_type: str,
    preprocess: dict,
) -> KbImageAsset:
    fingerprints = compute_image_fingerprints(image_bytes)
    md5_value = fingerprints.file_md5
    storage_path = _asset_storage_path(owner_id, document_id, page, md5_value, mime_type)
    abs_path = _upload_root() / storage_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    if not abs_path.exists():
        abs_path.write_bytes(image_bytes)

    asset = await db.scalar(
        select(KbImageAsset).where(
            KbImageAsset.owner_id == owner_id,
            KbImageAsset.document_id == document_id,
            KbImageAsset.page == page,
            KbImageAsset.hash_schema_version == IMAGE_HASH_SCHEMA_VERSION,
        )
    )
    if asset is None:
        asset = KbImageAsset(
            owner_id=owner_id,
            document_id=document_id,
            file_id=file_id,
            page=page,
            hash_schema_version=IMAGE_HASH_SCHEMA_VERSION,
        )
        db.add(asset)
    asset.raw_data_id = None
    asset.asset_type = asset_type
    asset.width = fingerprints.width
    asset.height = fingerprints.height
    asset.storage_path = storage_path
    asset.mime_type = mime_type
    asset.byte_size = len(image_bytes)
    asset.file_md5 = md5_value
    asset.ahash = fingerprints.ahash
    asset.dhash = fingerprints.dhash
    asset.phash = fingerprints.phash
    asset.status = "active"
    asset.diagnostics_json = {
        "schema_version": PAGE_ASSET_SCHEMA_VERSION,
        "hash_schema_version": IMAGE_HASH_SCHEMA_VERSION,
        "image_bytes_md5": md5_value,
        "storage_path": storage_path,
        "mime_type": mime_type,
        "byte_size": len(image_bytes),
        "vlm_image_preprocess": preprocess,
        "phase": "page_asset_materialized",
    }
    await db.flush()
    return asset


async def _materialize_single_page_asset(
    *,
    owner_id: int,
    document_id: int,
    file_id: int,
    user_id: int,
    page: int,
    is_pdf: bool,
) -> dict:
    """Materialize one page asset with its own DB transaction."""
    started = perf_counter()
    async with AsyncSessionLocal() as db:
        existing = await _existing_page_asset(db, document_id=document_id, page=page)
        if existing is not None:
            return {
                "page": page,
                "status": "reused",
                "asset_id": int(existing.id),
                "byte_size": int(existing.byte_size or 0),
                "duration_ms": round((perf_counter() - started) * 1000),
            }

    try:
        if is_pdf:
            source_bytes = await render_page_to_image(file_id, page, user_id)
            source_mime = "image/png"
            asset_type = "page_render"
        else:
            source_bytes, source_mime = await _read_source_image_bytes(file_id, user_id)
            asset_type = "image_file"
        prepared, prepared_mime, preprocess = _prepare_page_asset_bytes(source_bytes, source_mime)
        preprocess["page"] = page

        async with AsyncSessionLocal() as db:
            asset = await _upsert_page_asset(
                db,
                owner_id=owner_id,
                document_id=document_id,
                file_id=file_id,
                page=page,
                image_bytes=prepared,
                mime_type=prepared_mime,
                asset_type=asset_type,
                preprocess=preprocess,
            )
            await db.commit()
            return {
                "page": page,
                "status": "materialized",
                "asset_id": int(asset.id),
                "byte_size": len(prepared),
                "width": asset.width,
                "height": asset.height,
                "duration_ms": round((perf_counter() - started) * 1000),
            }
    except Exception as exc:
        return {
            "page": page,
            "status": "failed",
            "error": str(exc),
            "duration_ms": round((perf_counter() - started) * 1000),
        }
    finally:
        source_bytes = b""
        prepared = b""
        gc.collect()


async def materialize_page_assets_stage(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
    file_id: int,
    user_id: int,
) -> dict:
    """Render/compress visual pages once and persist local reusable assets."""
    started = perf_counter()
    doc = await db.scalar(select(KbDocument).where(KbDocument.id == int(document_id)))
    if doc is None:
        return {"document_id": document_id, "status": "skipped", "reason": "doc_missing"}
    ext = (doc.extension or "").lower()
    is_pdf = ext == "pdf"
    is_image = ext in IMAGE_FORMATS
    if not (is_pdf or is_image):
        return {"document_id": document_id, "status": "skipped", "reason": "page_assets_not_required"}

    if is_pdf:
        try:
            total_pages = await get_pdf_page_count(file_id, user_id)
        except Exception:
            total_pages = int(doc.total_pages or 1)
    else:
        total_pages = int(doc.total_pages or 1)
    doc.total_pages = total_pages
    await db.commit()

    page_concurrency = resolve_knowledge_concurrency(
        "page_render_pages",
        2 if is_pdf else 1,
        minimum=1,
        maximum=32,
    )
    sem = asyncio.Semaphore(page_concurrency)

    async def _page_worker(page: int) -> dict:
        async with sem:
            return await _materialize_single_page_asset(
                owner_id=owner_id,
                document_id=document_id,
                file_id=file_id,
                user_id=user_id,
                page=page,
                is_pdf=is_pdf,
            )

    page_results = await asyncio.gather(
        *(_page_worker(page) for page in range(1, total_pages + 1)),
        return_exceptions=True,
    )
    normalized_results: list[dict] = []
    for page, result in enumerate(page_results, start=1):
        if isinstance(result, Exception):
            normalized_results.append({"page": page, "status": "failed", "error": str(result)})
        else:
            normalized_results.append(result)

    assets = sum(1 for result in normalized_results if result.get("status") in {"materialized", "reused"})
    reused = sum(1 for result in normalized_results if result.get("status") == "reused")
    materialized = sum(1 for result in normalized_results if result.get("status") == "materialized")
    failed_pages = [
        {"page": result.get("page"), "error": result.get("error") or "page_render_failed"}
        for result in normalized_results
        if result.get("status") == "failed"
    ]
    await db.commit()
    status = "done" if assets == total_pages and not failed_pages else ("degraded" if assets else "failed")
    return {
        "document_id": document_id,
        "status": status,
        "total_pages": total_pages,
        "assets": assets,
        "materialized": materialized,
        "reused": reused,
        "failed_pages": failed_pages,
        "page_concurrency": page_concurrency,
        "pages": normalized_results,
        "timing": {"stage_wall_ms": round((perf_counter() - started) * 1000)},
    }


async def load_page_asset_bytes(
    db: AsyncSession,
    *,
    document_id: int,
    page: int,
) -> tuple[bytes, str, dict] | None:
    asset = await db.scalar(
        select(KbImageAsset)
        .where(
            KbImageAsset.document_id == int(document_id),
            KbImageAsset.page == int(page),
            KbImageAsset.status == "active",
            KbImageAsset.storage_path.is_not(None),
        )
        .order_by(KbImageAsset.id.desc())
        .limit(1)
    )
    if asset is None or not asset.storage_path:
        return None
    upload_root = _upload_root()
    abs_path = (upload_root / asset.storage_path).resolve()
    if os.path.commonpath([str(upload_root), str(abs_path)]) != str(upload_root) or not abs_path.exists():
        return None
    return abs_path.read_bytes(), asset.mime_type or "image/jpeg", asset.diagnostics_json or {}
