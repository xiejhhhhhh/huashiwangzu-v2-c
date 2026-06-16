import base64
import io
import json
import os
import re

import httpx

from app.config import get_settings

MIMO_VISION_BASE = "https://token-plan-cn.xiaomimimo.com/v1"
MIMO_VISION_MODEL = "mimo-v2.5"
LOCAL_VISION_BASE = "http://127.0.0.1:30002/v1"
LOCAL_VISION_MODEL = "Qwen3VL-8B-Instruct-Q4_K_M.gguf"

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "page_summary_prompt.txt")

VISION_DEFAULT = {
    "页面摘要": "", "信息密度": 3, "页面性质": "正文", "页面布局": "",
    "视觉元素": [], "文字内容": "", "表格数据": [],
    "提及品牌": [], "提及产品": [], "提及成分": [], "提及功效": [],
}


def compress_to_base64(img_path: str, max_width: int = 1280) -> str:
    from PIL import Image

    with Image.open(img_path) as img:
        if img.mode != "RGB":
            img = img.convert("RGB")
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii")


def build_prompt(ref_text: str) -> str:
    with open(PROMPT_PATH, encoding="utf-8") as file:
        prompt = file.read()
    if ref_text and ref_text.strip():
        prompt += "\n\n【pdftotext提取的参考文字】\n" + ref_text[:2000]
    return prompt


def parse_vision_output(raw: str) -> dict:
    match = re.search(r"\{[\s\S]*\}", raw or "")
    if match:
        try:
            data = json.loads(match.group())
            return {**VISION_DEFAULT, **data}
        except json.JSONDecodeError:
            pass
    return {**VISION_DEFAULT, "文字内容": raw or "", "页面摘要": (raw or "")[:200]}


def call_vision(base: str, model: str, key: str, prompt: str, img_b64: str) -> str:
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            ],
        }],
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    with httpx.Client(timeout=180.0) as client:
        resp = client.post(f"{base}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def all_gate_keys() -> list[str]:
    settings = get_settings()
    return [key for key in [settings.MIMO_GATE1_KEY] if key]
