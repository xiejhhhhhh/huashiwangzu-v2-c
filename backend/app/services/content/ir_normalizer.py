"""Content IR normalizer — fills in defaults, block ids, resource refs.

Called after validation passes. Produces a complete, normalized IR
ready for write_ir.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("v2.content").getChild("ir_normalizer")


async def normalize_ir(content_ir: dict[str, Any]) -> dict[str, Any]:
    """Normalize a validated Content IR in-place and return it.

    - Ensure schema_version defaults to '1.0'
    - Ensure locale defaults to 'zh-CN'
    - Ensure metadata is a dict
    - Auto-generate block ids for blocks without id
    - Normalize resource ids
    - Add defaults from content_type profile
    """
    ir = dict(content_ir)

    ir.setdefault("schema_version", "1.0")
    ir.setdefault("locale", "zh-CN")
    ir.setdefault("metadata", {})
    ir.setdefault("warnings", [])
    ir.setdefault("quality", {})
    if "resources" not in ir and isinstance(ir.get("assets"), list):
        ir["resources"] = list(ir["assets"])
    ir.setdefault("resources", [])

    # Normalize blocks recursively
    blocks = ir.get("blocks", [])
    _normalize_blocks(blocks)

    # Normalize resources
    resources = ir.get("resources", [])
    used_resource_ids: set[str | int] = set()
    for res in resources:
        rid = res.get("id")
        if rid is None or str(rid) in used_resource_ids:
            rid = f"r{hashlib.sha256(json.dumps(res, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]}"
            res["id"] = rid
        used_resource_ids.add(str(rid))
        res.setdefault("resource_type", "image")
        res.setdefault("mime_type", "application/octet-stream")
        res.setdefault("filename", "")

    ir["blocks"] = blocks
    ir["resources"] = resources
    ir["assets"] = list(resources)
    return ir


def _normalize_blocks(blocks: list[dict]) -> None:
    for i, block in enumerate(blocks):
        if not block.get("id"):
            raw = f"{i}:{block.get('text', '')}:{block.get('type', '')}:{datetime.now(timezone.utc).timestamp()}"
            block["id"] = f"b{hashlib.md5(raw.encode()).hexdigest()[:12]}"
        block.setdefault("data", {})
        block.setdefault("style", {})

        children = block.get("children")
        if isinstance(children, list):
            _normalize_blocks(children)
