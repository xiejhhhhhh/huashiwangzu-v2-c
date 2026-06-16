import logging
from app.services.knowledge.extract.types import PageResult
from app.services.knowledge.extract import pdf_backends
from app.services.knowledge.extract.pdf_vision import augment_with_vision

logger = logging.getLogger(__name__)

# 视觉提取开关：每页都截图喂视觉模型（华哥定，图文设计稿/检测报告必需）
_VISION_ENABLED = True
# 单文件视觉最多跑多少页（防 PDF 过大失控；0=不限）
_VISION_MAX_PAGES = 0

class PdfExtractor:

    def extract(self, file_path: str) -> list[PageResult]:
        pages: list[PageResult] = []
        if pdf_backends.DOCLING_AVAILABLE:
            try:
                pages = pdf_backends.extract_docling(file_path)
            except Exception as e:
                logger.warning("Docling PDF extraction failed: %s, falling back", e)
                pdf_backends.DOCLING_AVAILABLE = False
        if not pages and pdf_backends.PDFPLUMBER_AVAILABLE:
            try:
                pages = pdf_backends.extract_pdfplumber(file_path)
            except Exception as e:
                logger.warning("pdfplumber extraction failed: %s", e)
                pdf_backends.PDFPLUMBER_AVAILABLE = False
        if not pages and pdf_backends.FITZ_AVAILABLE:
            pages = pdf_backends.extract_fitz(file_path)
        if not pages:
            raise RuntimeError("No PDF extraction library available. Install docling, pdfplumber, or PyMuPDF.")

        if _VISION_ENABLED:
            augment_with_vision(file_path, pages, max_pages=_VISION_MAX_PAGES)
        return pages
