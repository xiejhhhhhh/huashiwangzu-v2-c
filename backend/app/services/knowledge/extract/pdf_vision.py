import logging
import os
import tempfile

from app.services.knowledge.extract import vision as _vision
from app.services.knowledge.extract.types import PageResult

logger = logging.getLogger(__name__)


def augment_with_vision(file_path: str, pages: list[PageResult], max_pages: int = 0) -> None:
    limit = len(pages)
    if max_pages > 0:
        limit = min(limit, max_pages)
    target = pages[:limit]
    tmp_dir = tempfile.mkdtemp(prefix="pdf_vision_")

    tasks: list[tuple[str, str]] = []
    valid: list[PageResult] = []
    for page in target:
        img = _vision.screenshot_page(file_path, page.page_num, tmp_dir)
        if not img:
            continue
        tasks.append((img, page.script_text or ""))
        valid.append(page)

    if not tasks:
        logger.warning("视觉增强：无可截图页（文件 %s）", os.path.basename(file_path))
        return

    results = _vision.vision_summary_batch(tasks)
    ok = 0
    for page, result in zip(valid, results):
        try:
            _apply_vision_result(page, result)
            if page.vision_text:
                ok += 1
        except Exception as exc:
            logger.warning("视觉结果回填失败 page=%d: %s", page.page_num, exc)
    logger.info("视觉增强完成：%d/%d 页（文件 %s）", ok, len(valid), os.path.basename(file_path))


def _apply_vision_result(page: PageResult, result: dict) -> None:
    summary = result.get("页面摘要") or ""
    text = result.get("文字内容") or ""
    page.vision_text = text or summary
    entities = []
    for key in ("提及品牌", "提及产品", "提及成分", "提及功效"):
        entities.extend(result.get(key) or [])
    page.layout_data = page.layout_data or {}
    page.layout_data["summary"] = summary
    page.layout_data["vision_text"] = text
    if entities:
        page.layout_data["vision_entities"] = entities
    if result.get("表格数据"):
        page.layout_data["vision_tables"] = result["表格数据"]
