from app.services.knowledge.extract.types import PageResult
from app.services.knowledge.extract.dispatch import ExtractDispatcher

# ── Auto-register all extractors ──
from app.services.knowledge.extract.pdf import PdfExtractor
from app.services.knowledge.extract.office import OfficeExtractor
from app.services.knowledge.extract.excel import ExcelExtractor
from app.services.knowledge.extract.image import ImageExtractor
from app.services.knowledge.extract.video import VideoExtractor

_extractors = {
    "pdf": PdfExtractor,
    "office": OfficeExtractor,
    "excel": ExcelExtractor,
    "image": ImageExtractor,
    "video": VideoExtractor,
}
for _channel, _cls in _extractors.items():
    ExtractDispatcher.register(_channel)(_cls)

__all__ = ["PageResult", "ExtractDispatcher"]
