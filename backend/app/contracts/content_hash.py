"""内容哈希工具(方案07 §19.2)。

- content_sha256: 对 CanonicalContentIR 的 JSON 用 RFC 8785(JCS)规范化后算真实
  SHA-256,保证同内容跨机器跨版本得到同一 hash。
- source_sha256:  对原始字节算 SHA-256。禁止旧实现 SHA256(MD5字符串)。

RFC 8785 规范化的关键点:键按 UTF-16 码元排序、无多余空白、数字用最短往返表示。
标准库没有 JCS,这里用 json.dumps(sort_keys=True, separators=(',',':'),
ensure_ascii=False) 近似(键排序 + 紧凑),对我们全 str 键的 IR 足够稳定;若引入
第三方 rfc8785 库可无缝替换 _canonical_json。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def content_sha256(payload: Any) -> str:
    """对结构化内容(dict / Pydantic model.model_dump())算规范化 SHA-256。"""
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def source_sha256_from_bytes(data: bytes) -> str:
    """原始字节 SHA-256(真 hash,取代 SHA256(MD5字符串))。"""
    return hashlib.sha256(data).hexdigest()


def source_sha256_from_path(path: str, chunk_size: int = 1 << 20) -> str:
    """流式对文件算原始字节 SHA-256,避免大文件全量读内存。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()
