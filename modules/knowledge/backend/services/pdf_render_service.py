"""PDF 页面渲染服务：将 PDF 页面渲染为图片字节。

依赖 pymupdf (fitz)，V1 原用 pdftoppm，V2 用 fitz 纯 Python 实现，无外部二进制依赖。
"""
import logging
import os
from pathlib import Path

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.services.file_service import check_file_access

logger = logging.getLogger("v2.knowledge").getChild("pdf_render")


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
    import fitz  # pymupdf

    # 1. 校验文件访问权限并读取
    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / file.storage_path).resolve()
        if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root):
            raise ValueError("Unsafe file storage path")
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
        raw_bytes = full_path.read_bytes()

    # 2. 渲染页面
    doc = fitz.open(stream=raw_bytes, filetype="pdf")
    if page_num < 1 or page_num > doc.page_count:
        doc.close()
        raise ValueError(f"Page {page_num} out of range (1-{doc.page_count})")

    page = doc[page_num - 1]

    # 缩放计算：dpi 映射到 fitz 的 matrix
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)

    # 大图缩小
    if max(pix.width, pix.height) > max_dimension:
        scale = max_dimension / max(pix.width, pix.height)
        mat = fitz.Matrix(zoom * scale, zoom * scale)
        pix = page.get_pixmap(matrix=mat)

    png_bytes = pix.tobytes("png")
    doc.close()
    logger.debug("Rendered page %d of file_id=%d: %dx%d, %d bytes", page_num, file_id, pix.width, pix.height, len(png_bytes))
    return png_bytes


async def get_pdf_page_count(file_id: int, user_id: int) -> int:
    """获取 PDF 文件的总页数。"""
    import fitz

    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / file.storage_path).resolve()
        raw_bytes = full_path.read_bytes()

    doc = fitz.open(stream=raw_bytes, filetype="pdf")
    count = doc.page_count
    doc.close()
    return count
