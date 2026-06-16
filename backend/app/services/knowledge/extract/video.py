import logging
from app.services.knowledge.extract.types import PageResult

logger = logging.getLogger(__name__)


class VideoExtractor:
    """Video placeholder: only recognizes and catalogs, no actual extraction.

    Marked as channel_type=video, status=pending_video.
    Actual transcription will come via Whisper in a later batch.
    """

    def extract(self, file_path: str) -> list[PageResult]:
        logger.info("Video placeholder for %s - no extraction implemented yet", file_path)
        return [PageResult(
            page_num=1,
            script_text="",
            layout_data={
                "type": "video_placeholder",
                "note": "视频文件仅做编目，转写由后续 Whisper 批次处理",
            },
        )]
