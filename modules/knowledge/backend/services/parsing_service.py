"""知识库解析编排服务：按文件格式调对应解析模块，返回统一 DocumentIr。

所有 parser 调用都经过此编排层，产出统一的 DocumentIr 模型。
后续新增格式只需在此添加映射 + 注册 parser capability，下游无需改动。
"""
import logging

from app.services.module_registry import call_capability
from ..ir_models import DocumentIr, from_legacy_blocks

logger = logging.getLogger("v2.knowledge").getChild("parsing")

# 格式 → (模块名, 动作) 映射
# 新格式在此添加一行，下游文档登记/分块/融合/导出均自动适配
FORMAT_PARSER_MAP: dict[str, tuple[str, str]] = {
    "pdf": ("pdf-parser", "parse"),
    "docx": ("docx-parser", "parse"),
    "pptx": ("pptx-parser", "parse"),
    "xlsx": ("xlsx-parser", "parse"),
    "csv": ("csv-parser", "parse"),
    "tsv": ("csv-parser", "parse"),
    "txt": ("text-parser", "parse"),
    "md": ("markdown-parser", "parse"),
    "markdown": ("markdown-parser", "parse"),
    "json": ("structured-parser", "parse"),
    "yaml": ("structured-parser", "parse"),
    "yml": ("structured-parser", "parse"),
    "eml": ("email-parser", "parse"),
    "msg": ("email-parser", "parse"),
}

# 图片格式经 image-vision 模块解析（可选依赖）
IMAGE_FORMATS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "svg"}

# 视频格式暂不支持解析
VIDEO_FORMATS = {"mp4", "avi", "mov", "mkv", "webm"}

# 低质量解析判定阈值
LOW_QUALITY_CHAR_THRESHOLD = 20
EMPTY_RESULT_THRESHOLD = 0


def get_parser_for_format(extension: str) -> tuple[str, str] | None:
    """根据文件扩展名返回 (模块名, 动作) 或 None。"""
    ext = extension.lower().strip(".")
    if ext in FORMAT_PARSER_MAP:
        return FORMAT_PARSER_MAP[ext]
    if ext in IMAGE_FORMATS:
        return ("image-vision", "describe")
    return None


async def parse_document(file_id: int, extension: str, caller: str) -> DocumentIr:
    """按文件格式调用对应的格式解析模块，返回统一 DocumentIr。

    所有下游（分块/融合/导出/检索）只消费 DocumentIr，
    新增格式时只需在 FORMAT_PARSER_MAP 加映射 + 实现 parser capability。

    对低质量解析、空文本、失败结果做明确区分：
    - 空结果：返回 doc_ir 但 parse_errors 包含 "empty_result"
    - 低质量：返回 doc_ir 但 parse_errors 包含 "low_quality"
    - 失败：抛出异常
    """
    parser = get_parser_for_format(extension)
    if not parser:
        raise ValueError(f"Unsupported format: '{extension}'")
    module_key, action = parser
    logger.info("Parsing file_id=%d via %s:%s", file_id, module_key, action)
    try:
        result = await call_capability(module_key, action, {"file_id": file_id}, caller)
    except Exception as e:
        logger.error("Parse failed for file_id=%d via %s:%s: %s", file_id, module_key, action, e)
        raise

    doc_ir: DocumentIr
    if isinstance(result, dict):
        doc_ir = from_legacy_blocks(
            file_id=file_id,
            fmt=result.get("format", extension),
            blocks=result.get("blocks", []),
            resources=result.get("resources"),
        )
    elif isinstance(result, DocumentIr):
        doc_ir = result
    else:
        raise TypeError(f"Unexpected parse result type: {type(result)}")

    non_empty = doc_ir.iter_non_empty()
    total_chars = sum(len(b.text) for b in non_empty)

    if not non_empty or total_chars == 0:
        doc_ir.parse_errors.append("empty_result")
        logger.warning("Parser returned empty result for file_id=%d via %s:%s", file_id, module_key, action)
    elif total_chars < LOW_QUALITY_CHAR_THRESHOLD:
        doc_ir.parse_errors.append("low_quality")
        logger.warning("Parser returned low-quality result for file_id=%d via %s:%s (chars=%d)",
                       file_id, module_key, action, total_chars)

    return doc_ir
