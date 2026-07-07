"""PDF 页面渲染服务：将 PDF 页面渲染为图片字节。

依赖 pymupdf (fitz)，V1 原用 pdftoppm，V2 用 fitz 纯 Python 实现，无外部二进制依赖。
"""
import asyncio
import gc
import logging
import os
from pathlib import Path

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.services.file_service import check_file_access

logger = logging.getLogger("v2.knowledge").getChild("pdf_render")


def _render_pdf_page_bytes(
    full_path: Path,
    *,
    file_id: int,
    page_num: int,
    dpi: int,
    max_dimension: int,
) -> bytes:
    import fitz  # pymupdf

    doc = fitz.open(str(full_path))
    try:
        if page_num < 1 or page_num > doc.page_count:
            raise ValueError(f"Page {page_num} out of range (1-{doc.page_count})")

        page = doc[page_num - 1]
        requested_zoom = dpi / 72.0
        page_longest = max(float(page.rect.width), float(page.rect.height), 1.0)
        dimension_zoom = max_dimension / page_longest
        zoom = max(0.1, min(requested_zoom, dimension_zoom))
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        try:
            png_bytes = pix.tobytes("png")
            pix_width = pix.width
            pix_height = pix.height
        finally:
            pix = None
            gc.collect()
        logger.debug(
            "Rendered page %d of file_id=%d: %dx%d, %d bytes",
            page_num,
            file_id,
            pix_width,
            pix_height,
            len(png_bytes),
        )
        return png_bytes
    finally:
        doc.close()


def _pdf_page_count(full_path: Path) -> int:
    import fitz

    doc = fitz.open(str(full_path))
    try:
        return int(doc.page_count)
    finally:
        doc.close()


async def render_page_to_image(
    file_id: int,
    page_num: int,
    user_id: int,
    dpi: int = 150,
    max_dimension: int = 1600,
) -> bytes:
    """渲染 PDF 单页为 PNG 字节流。

    Args:
        file_id: 框架文件 ID。
        page_num: 页码（从 1 起）。
        user_id: 调用者 ID（用于 check_file_access）。
        dpi: 渲染分辨率（默认 150）。
        max_dimension: 图片最大边长（像素），超限等比例缩小。

    Returns:
        PNG 格式图片字节。
    """
    # 1. 校验文件访问权限并读取
    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / file.storage_path).resolve()
        if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root):
            raise ValueError("Unsafe file storage path")
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
    return await asyncio.to_thread(
        _render_pdf_page_bytes,
        full_path,
        file_id=file_id,
        page_num=page_num,
        dpi=dpi,
        max_dimension=max_dimension,
    )


async def get_pdf_page_count(file_id: int, user_id: int) -> int:
    """获取 PDF 文件的总页数。"""
    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / file.storage_path).resolve()
    return await asyncio.to_thread(_pdf_page_count, full_path)
