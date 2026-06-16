import logging
import os
from app.services.knowledge.extract.types import PageResult

logger = logging.getLogger(__name__)

_EASYOCR_AVAILABLE = False
try:
    import easyocr
    _EASYOCR_AVAILABLE = True
except ImportError:
    pass


class ImageExtractor:

    def __init__(self):
        self._reader = None

    def _get_reader(self):
        if self._reader is None and _EASYOCR_AVAILABLE:
            self._reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
        return self._reader

    def extract(self, file_path: str) -> list[PageResult]:
        from PIL import Image
        with Image.open(file_path) as img:
            layout_blocks = [
                {
                    "type": "image_meta",
                    "format": img.format,
                    "mode": img.mode,
                    "width": img.width,
                    "height": img.height,
                }
            ]
        ocr_text = ""

        reader = self._get_reader()
        if reader:
            try:
                results = reader.readtext(file_path)
                text_parts = []
                for bbox, text, conf in results:
                    text_parts.append(text)
                    layout_blocks.append({
                        "type": "ocr_region",
                        "bbox": [[float(v) for v in pt] for pt in bbox],
                        "text": text,
                        "confidence": round(float(conf), 3),
                    })
                ocr_text = "\n".join(text_parts)
            except Exception as e:
                logger.warning("EasyOCR failed: %s", e)

        return [PageResult(
            page_num=1,
            script_text="",
            ocr_text=ocr_text,
            layout_data={"blocks": layout_blocks},
        )]
