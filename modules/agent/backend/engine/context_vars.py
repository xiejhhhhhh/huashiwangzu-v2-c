"""上下文变量引擎：从工具产出中提炼关键变量，注入后续系统提示词。

每次工具调用结束后提取 file_id / folder_id / 文件名等结构化字段，
累积到 AgentConversation.context_vars。下一轮对话时拼接为紧凑提示词块，
减少模型"翻历史找 id"的浪费。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("v2.agent").getChild("context_vars")

# 规则表：(event_type 匹配前缀, 提取路径, 写入 key)
_EXTRACT_RULES: list[tuple[str, list[str], str]] = [
    # desktop-tools list_files → 桌面文件列表
    ("tool_result", ["result", "items"], "desktop_files"),
    # skill_use / docs-open__get_content → 当前文档
    ("tool_result", ["result", "file_id"], "last_file_id"),
    ("tool_result", ["result", "file_name"], "last_file_name"),
    ("tool_result", ["result", "folder_id"], "last_folder_id"),
    # 通用：任何 result 里有 file_id
    ("tool_result", ["result", "data", "file_id"], "last_file_id"),
]


def extract_context_vars(tool_events: list[dict]) -> dict[str, Any]:
    """从一轮工具事件中提取上下文变量。

    Args:
        tool_events: 本轮全部 tool_call/tool_result 事件列表

    Returns:
        增量 context_vars dict，适合与已有累积合并
    """
    extracted: dict[str, Any] = {}

    for evt in tool_events:
        etype = evt.get("type", "")
        if not etype.startswith("tool_result"):
            continue

        result = evt.get("result")
        if not isinstance(result, dict):
            continue

        # 通用提取：result 中任何 file_id / file_name
        _extract_file_info(result, extracted)

        # 桌面文件列表特殊处理
        items = result.get("items")
        if isinstance(items, list) and items:
            extracted["desktop_files"] = [
                {
                    "id": f.get("id"),
                    "name": f.get("name", ""),
                    "extension": f.get("extension", ""),
                }
                for f in items
                if isinstance(f, dict) and f.get("id")
            ]

        # 文档内容提取 → 当前文档标记
        content = result.get("content") or result.get("data", {}).get("content")
        file_id = result.get("file_id") or result.get("data", {}).get("file_id")
        file_name = result.get("file_name") or result.get("data", {}).get("file_name")
        if content and file_id:
            extracted["current_document"] = {
                "file_id": file_id,
                "file_name": file_name or "unknown",
            }

    return extracted


def _extract_file_info(result: dict, out: dict[str, Any]) -> None:
    """递归扫描 result，提取 file_id/file_name 等字段。"""
    for key in ("file_id", "file_name", "folder_id"):
        val = result.get(key)
        if val is not None:
            ctx_key = f"last_{key}"
            if ctx_key not in out:
                out[ctx_key] = val

    # 浅层嵌套 data
    data = result.get("data")
    if isinstance(data, dict):
        _extract_file_info(data, out)


def format_context_vars_section(vars: dict[str, Any]) -> str:
    """将上下文变量格式化为系统提示词块。

    仅在有内容时返回非空字符串，否则返回空。
    """
    if not vars:
        return ""

    lines: list[str] = []
    lines.append("\n## 上下文变量（来自之前的工具调用）")

    # 桌面文件
    desktop_files = vars.get("desktop_files")
    if isinstance(desktop_files, list) and desktop_files:
        lines.append("\n### 桌面文件")
        for f in desktop_files:
            name = f.get("name", "?")
            fid = f.get("id", "?")
            ext = f.get("extension", "")
            lines.append(f"- id={fid} | {name}{'.' + ext if ext else ''}")

    # 当前打开的文档
    current_doc = vars.get("current_document")
    if isinstance(current_doc, dict):
        lines.append(
            f"\n### 当前文档\n"
            f"- file_id={current_doc.get('file_id')} | "
            f"{current_doc.get('file_name', '?')}"
        )

    # 最近操作的 file_id / folder_id
    for key, label in [
        ("last_file_id", "最近文件ID"),
        ("last_file_name", "最近文件名"),
        ("last_folder_id", "最近文件夹ID"),
    ]:
        val = vars.get(key)
        if val is not None:
            lines.append(f"- {label}: {val}")

    # 去重
    unique = list(dict.fromkeys(lines))
    if len(unique) <= 1:
        return ""
    return "\n".join(unique)
