import io
import logging

from PIL import Image, ImageDraw, ImageFont

from .base import GenResult, GenSpec, ImageProvider

logger = logging.getLogger("v2.image-gen").getChild("placeholder")


class PlaceholderProvider(ImageProvider):
    provider_key = "placeholder"

    async def generate(self, spec: GenSpec) -> list[GenResult]:
        results: list[GenResult] = []
        for _ in range(spec.count):
            buf = io.BytesIO()
            img = self._make_placeholder(spec.prompt, spec.width, spec.height)
            img.save(buf, format="PNG")
            results.append(GenResult(
                image_bytes=buf.getvalue(),
                meta={"placeholder": True},
            ))
        logger.info("Generated %d placeholder images for prompt=%r", spec.count, spec.prompt[:80])
        return results

    @staticmethod
    def _make_placeholder(prompt: str, width: int, height: int) -> Image.Image:
        img = Image.new("RGB", (width, height), (245, 245, 245))
        draw = ImageDraw.Draw(img)

        watermark_text = "图片生成功能开发中"
        prompt_display = prompt if len(prompt) <= 60 else prompt[:57] + "..."

        font_large = None
        font_small = None
        for font_path in (
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        ):
            try:
                font_large = ImageFont.truetype(font_path, 32)
                font_small = ImageFont.truetype(font_path, 24)
                break
            except (OSError, IOError):
                continue
        if font_large is None:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), prompt_display, font=font_large)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (width - tw) // 2
        ty = (height - th) // 2 - 30
        draw.text((tx, ty), prompt_display, fill=(60, 60, 60), font=font_large)

        wbbox = draw.textbbox((0, 0), watermark_text, font=font_small)
        ww = wbbox[2] - wbbox[0]
        wx = (width - ww) // 2
        wy = ty + th + 40
        draw.text((wx, wy), watermark_text, fill=(160, 160, 160), font=font_small)

        return img
