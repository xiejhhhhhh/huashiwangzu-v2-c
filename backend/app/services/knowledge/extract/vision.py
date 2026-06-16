"""
PDF 页面视觉提取（1:1 翻译 V1 的"截图→VLM摘要"路）。
截图 pdftoppm → Pillow 压缩 base64 → 云端 mimo 视觉模型 → 结构化 JSON。
本地 30002 Qwen3VL 作兜底。
"""
import glob
import logging
import os
import shutil
import subprocess

from app.config import get_settings
from app.services.knowledge.extract.vision_client import (
    LOCAL_VISION_BASE,
    LOCAL_VISION_MODEL,
    MIMO_VISION_BASE,
    MIMO_VISION_MODEL,
    VISION_DEFAULT,
    all_gate_keys,
    build_prompt,
    call_vision,
    compress_to_base64,
    parse_vision_output,
)

logger = logging.getLogger(__name__)

def _find_cmd(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for d in ("/opt/homebrew/bin/", "/usr/local/bin/", "/usr/bin/"):
        p = d + name
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return ""


def screenshot_page(pdf_path: str, page_num: int, out_dir: str) -> str:
    """pdftoppm 截单页为 png（200dpi），返回图片路径。失败返回空串。"""
    pdftoppm = _find_cmd("pdftoppm")
    if not pdftoppm:
        logger.warning("pdftoppm 未安装，无法截图")
        return ""
    prefix = os.path.join(out_dir, f"page_{page_num}")
    cmd = [pdftoppm, "-png", "-r", "200", "-f", str(page_num),
           "-l", str(page_num), pdf_path, prefix]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    except Exception as e:
        logger.warning("pdftoppm 截图失败 page=%d: %s", page_num, e)
        return ""
    matches = glob.glob(prefix + "*.png")
    return matches[0] if matches else ""


def vision_summary(img_path: str, ref_text: str = "") -> dict:
    """对单页截图调视觉模型，返回结构化摘要 dict。云端优先，本地兜底。"""
    img_b64 = compress_to_base64(img_path)
    prompt = build_prompt(ref_text)
    settings = get_settings()

    try:
        raw = call_vision(MIMO_VISION_BASE, MIMO_VISION_MODEL,
                           settings.MIMO_GATE1_KEY, prompt, img_b64)
        return parse_vision_output(raw)
    except Exception as e:
        logger.warning("云端视觉失败，转本地兜底: %s", e)

    try:
        raw = call_vision(LOCAL_VISION_BASE, LOCAL_VISION_MODEL, "", prompt, img_b64)
        return parse_vision_output(raw)
    except Exception as e:
        logger.error("本地视觉也失败: %s", e)
        return dict(VISION_DEFAULT)


# ── 批量并发：单 KEY × 5 线程 ──
_TOTAL_THREADS = 5


def _vision_one(idx: int, img_path: str, ref_text: str, key: str) -> tuple[int, dict]:
    """单页：压缩→调视觉(指定门KEY)→解析。失败本地兜底。"""
    try:
        img_b64 = compress_to_base64(img_path)
    except Exception as e:
        logger.warning("压缩失败 idx=%d: %s", idx, e)
        return idx, dict(VISION_DEFAULT)
    prompt = build_prompt(ref_text)
    try:
        raw = call_vision(MIMO_VISION_BASE, MIMO_VISION_MODEL, key, prompt, img_b64)
        return idx, parse_vision_output(raw)
    except Exception as e:
        logger.warning("云端视觉失败 idx=%d，转本地兜底: %s", idx, e)
    try:
        raw = call_vision(LOCAL_VISION_BASE, LOCAL_VISION_MODEL, "", prompt, img_b64)
        return idx, parse_vision_output(raw)
    except Exception as e:
        logger.error("本地视觉也失败 idx=%d: %s", idx, e)
        return idx, dict(VISION_DEFAULT)


def vision_summary_batch(tasks: list[tuple[str, str]]) -> list[dict]:
    """
    批量视觉：tasks=[(图片路径, 参考文字), ...]，整批 20 并发跑完才返回。
    第 i 个任务用第 (i % 门数) 个门的 KEY，实现 4 门轮转负载均衡。
    返回顺序与输入一致。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if not tasks:
        return []
    keys = all_gate_keys()
    if not keys:
        keys = [""]  # 没云端KEY就全走本地兜底
    results: list[dict] = [dict(VISION_DEFAULT) for _ in tasks]
    with ThreadPoolExecutor(max_workers=_TOTAL_THREADS) as pool:
        futs = [
            pool.submit(_vision_one, i, img, ref, keys[i % len(keys)])
            for i, (img, ref) in enumerate(tasks)
        ]
        for fut in as_completed(futs):
            idx, data = fut.result()
            results[idx] = data
    return results
