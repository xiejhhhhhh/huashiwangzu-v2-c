from dataclasses import dataclass, field


@dataclass
class PageResult:
    page_num: int
    script_text: str = ""
    ocr_text: str = ""
    vision_text: str = ""
    layout_data: dict = field(default_factory=dict)
    screenshot_path: str | None = None
    screenshot_md5: str | None = None

    def to_page_source_dicts(self, catalog_id: int) -> list[dict]:
        sources = []
        if self.script_text:
            sources.append({
                "catalog_id": catalog_id,
                "page_num": self.page_num,
                "source_type": "script",
                "content": {"text": self.script_text},
                "screenshot_md5": self.screenshot_md5,
            })
        if self.ocr_text:
            sources.append({
                "catalog_id": catalog_id,
                "page_num": self.page_num,
                "source_type": "ocr",
                "content": {"text": self.ocr_text},
                "screenshot_md5": self.screenshot_md5,
            })
        has_vision = self.vision_text or any(k in self.layout_data for k in ("summary", "entities"))
        if has_vision:
            sources.append({
                "catalog_id": catalog_id,
                "page_num": self.page_num,
                "source_type": "vision",
                "content": {
                    "summary": self.vision_text,
                    **({"entities": self.layout_data.get("vision_entities", [])} if self.layout_data.get("vision_entities") else {}),
                },
                "screenshot_md5": self.screenshot_md5,
            })
        if self.layout_data:
            sources.append({
                "catalog_id": catalog_id,
                "page_num": self.page_num,
                "source_type": "layout",
                "content": self.layout_data,
                "screenshot_md5": self.screenshot_md5,
            })
        return sources
