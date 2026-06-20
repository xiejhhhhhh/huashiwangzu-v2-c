"""知识库解析编排服务：按文件格式调对应解析模块，返回统一内容块。"""
import logging

from app.services.module_registry import call_capability

logger = logging.getLogger("v2.knowledge.parsing")

# 格式 → (模块名, 动作) 映射
FORMAT_PARSER_MAP: dict[str, tuple[str, str]] = {
    "pdf": ("pdf-parser", "parse"),
    "docx": ("docx-parser", "parse"),
    "pptx": ("pptx-parser", "parse"),
    "xlsx": ("xlsx-parser", "parse"),
    "csv": ("xlsx-parser", "parse"),  # csv 走 xlsx-parser
    "txt": ("text-parser", "parse"),
    "md": ("text-parser", "parse"),
}

# 图片格式经 image-vision 模块解析（可选依赖）
IMAGE_FORMATS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "svg"}

# 视频格式暂不支持解析
VIDEO_FORMATS = {"mp4", "avi", "mov", "mkv", "webm"}


def get_parser_for_format(extension: str) -> tuple[str, str] | None:
    """根据文件扩展名返回 (模块名, 动作) 或 None。"""
    ext = extension.lower().strip(".")
    if ext in FORMAT_PARSER_MAP:
        return FORMAT_PARSER_MAP[ext]
    if ext in IMAGE_FORMATS:
        return ("image-vision", "describe")
    return None


async def parse_document(file_id: int, extension: str, caller: str) -> dict:
    """按文件格式调用对应的格式解析模块，返回统一内容块结构。

    返回格式：
    {
        "file_id": int,
        "format": str,
        "blocks": [{"type": str, "text": str, "page": int|null, "resource_ref": int|null}, ...],
        "resources": [{"id": int, "type": str, "file_storage_id": null, "text_desc": str}, ...],
    }
    """
    parser = get_parser_for_format(extension)
    if not parser:
        raise ValueError(f"Unsupported format: '{extension}'")
    module_key, action = parser
    logger.info("Parsing file_id=%d via %s:%s", file_id, module_key, action)
    try:
        result = await call_capability(module_key, action, {"file_id": file_id}, caller)
        return result
    except Exception as e:
        logger.error("Parse failed for file_id=%d via %s:%s: %s", file_id, module_key, action, e)
        raise
