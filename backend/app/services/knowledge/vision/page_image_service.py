import asyncio
import os
from pathlib import Path

from PIL import Image

from app.models.knowledge import Catalog
from app.services.knowledge.extract.vision import screenshot_page

BASE_DIR = Path(__file__).resolve().parents[4] / "data" / "knowledge_visual"
PAGE_DIR = BASE_DIR / "pages"
THUMB_DIR = BASE_DIR / "thumbnails"


def _safe_page_num(page_num: int) -> int:
    if page_num < 1:
        raise ValueError("page_num must be greater than 0")
    return page_num


def _page_path(catalog_id: int, page_num: int) -> Path:
    return PAGE_DIR / str(catalog_id) / f"page_{page_num}.png"


def _thumb_path(catalog_id: int, page_num: int) -> Path:
    return THUMB_DIR / str(catalog_id) / f"page_{page_num}.jpg"


def _is_pdf(catalog: Catalog) -> bool:
    ext = os.path.splitext(catalog.file_path or catalog.file_name)[1].lower()
    return catalog.channel_type == "pdf" or catalog.mime_type == "application/pdf" or ext == ".pdf"


def _render_page_image(catalog: Catalog, page_num: int, target: Path) -> Path | None:
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = screenshot_page(catalog.file_path, page_num, str(target.parent))
    if not rendered:
        return None
    rendered_path = Path(rendered)
    if rendered_path != target:
        rendered_path.replace(target)
    return target if target.exists() else None


def _make_thumbnail(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as img:
        img.thumbnail((360, 480))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(target, "JPEG", quality=82, optimize=True)
    return target


async def ensure_page_image(catalog: Catalog, page_num: int) -> Path | None:
    page_num = _safe_page_num(page_num)
    target = _page_path(catalog.id, page_num)
    if target.exists():
        return target
    if not _is_pdf(catalog) or not os.path.isfile(catalog.file_path):
        return None
    return await asyncio.to_thread(_render_page_image, catalog, page_num, target)


async def ensure_thumbnail(catalog: Catalog, page_num: int) -> Path | None:
    page_num = _safe_page_num(page_num)
    target = _thumb_path(catalog.id, page_num)
    if target.exists():
        return target
    source = await ensure_page_image(catalog, page_num)
    if not source:
        return None
    return await asyncio.to_thread(_make_thumbnail, source, target)
