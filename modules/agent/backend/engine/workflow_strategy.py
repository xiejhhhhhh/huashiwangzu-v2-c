"""Workflow strategy: project-level behavior constraints injected at runtime.

Extracts the inline keyword-matching pattern from ``engine.py`` into a
configurable strategy that maps trigger keywords to structured workflow
instructions.  This reduces reliance on prompt text alone — the strategy
can be observed, tested, and extended without touching engine logic.
"""
import logging
import re
from typing import Any

logger = logging.getLogger("v2.agent").getChild("engine.workflow_strategy")

# ── Trigger → Workflow mapping ─────────────────────────────────────────
#
# Each entry: (trigger_keywords, label, workflow_steps)
#   - trigger_keywords: list of substrings that activate this workflow
#   - label: human-readable name for the workflow
#   - workflow_steps: ordered list of step dicts, each with "action" and "detail"

WORKFLOW_DEFINITIONS: list[dict[str, Any]] = [
    {
        "keywords": ["项目", "任务", "收口", "验收", "发信", "投件", "交付", "变更", "重构"],
        "label": "project_workflow",
        "workflow_steps": [
            {"action": "发信", "detail": "需要发信 → 写入投递箱目录（邮箱/投递箱/）"},
            {"action": "查代码", "detail": "用 codegraph 或 codemap 查影响面"},
            {"action": "改前实读", "detail": "修改前实读关联文件确认"},
            {"action": "改后测试", "detail": "修改后运行相关测试"},
            {"action": "验收", "detail": "执行验收命令，贴原始输出"},
            {"action": "留痕", "detail": "memory_write 记录变更摘要"},
            {"action": "回信", "detail": "标准五件套写入收件箱"},
            {"action": "归档", "detail": "蒸馏变更到开发文档，删除临时文件"},
        ],
    },
    {
        "keywords": ["数据库", "SQL", "迁移", "migration", "schema"],
        "label": "database_workflow",
        "workflow_steps": [
            {"action": "先读当前 schema", "detail": "调 db_schema 确认当前数据库结构"},
            {"action": "评估影响", "detail": "确认改 schema 不影响其他模块"},
            {"action": "生成迁移", "detail": "用 Alembic 生成迁移文件"},
            {"action": "验证", "detail": "运行相关测试确认 schema 变更正确"},
        ],
    },
    {
        "keywords": ["模块", "新建模块", "新模块"],
        "label": "module_creation_workflow",
        "workflow_steps": [
            {"action": "复制模板", "detail": "cp -r modules/_template modules/YOUR_MODULE_KEY"},
            {"action": "替换占位符", "detail": "替换 MODULE_KEY / MODULE_DISPLAY_NAME"},
            {"action": "开发", "detail": "在 sandbox/ 中独立开发"},
            {"action": "集成", "detail": "npm run scan:modules + npm run build"},
        ],
    },
]

_DEFAULT_WORKFLOW_PROMPT = """<project_workflow>
检测到项目相关任务，请遵循以下工作流：
1. 需要发信 → 写入投递箱目录（邮箱/投递箱/）
2. 需要查代码 → 先用 codegraph or codemap 查影响面
3. 修改前 → 实读关联文件确认
4. 修改后 → 运行相关测试
5. 验收 → 执行验收命令，贴原始输出
6. 留痕 → memory_write 记录变更摘要
7. 回信 → 标准五件套写入收件箱
8. 归档 → 蒸馏变更到开发文档，删除临时文件
</project_workflow>"""


def match_workflow(user_input: str) -> dict | None:
    """Match user input against known workflow triggers.

    Returns the first matching workflow definition, or None if no trigger
    is detected.  Matching is case-insensitive substring match.
    """
    if not user_input:
        return None
    lower_input = user_input.lower()
    for wf in WORKFLOW_DEFINITIONS:
        for kw in wf["keywords"]:
            if kw.lower() in lower_input:
                logger.debug("Workflow triggered: '%s' by keyword '%s'", wf["label"], kw)
                return wf
    return None


def format_workflow_injection(workflow: dict | None = None) -> str | None:
    """Format workflow as prompt injection block.

    Args:
        workflow: A matched workflow definition dict, or None to use default.

    Returns:
        Formatted prompt injection string, or None if no workflow.
    """
    if workflow is None:
        return _DEFAULT_WORKFLOW_PROMPT

    steps = workflow.get("workflow_steps", [])
    lines = [f"<{workflow['label']}>"]
    lines.append(f"检测到 {workflow['label']} 相关任务，请遵循以下工作流：")
    for i, step in enumerate(steps, 1):
        lines.append(f"{i}. {step['action']} — {step['detail']}")
    lines.append(f"</{workflow['label']}>")
    return "\n".join(lines)


def get_all_workflows() -> list[dict[str, Any]]:
    """Return all registered workflow definitions (for admin / diagnostics)."""
    return [
        {
            "label": wf["label"],
            "keywords": wf["keywords"],
            "step_count": len(wf.get("workflow_steps", [])),
        }
        for wf in WORKFLOW_DEFINITIONS
    ]


def apply_workflow_injection(user_input: str, messages: list[dict]) -> dict:
    """Main entry: detect workflow trigger, inject prompt, return diagnosis.

    This replaces the inline code in ``engine.py`` assemble_context().

    Args:
        user_input: The current user input text.
        messages: The assembled messages list (mutated in place if injection).

    Returns:
        Diagnosis dict with keys:
            ``workflow_injected`` — bool or error string
            ``workflow_label`` — the matched workflow label (if any)
    """
    diagnosis = {"workflow_injected": False, "workflow_label": None}
    try:
        matched = match_workflow(user_input)
        if matched and messages:
            injection = format_workflow_injection(matched)
            for msg in messages:
                if msg["role"] == "system":
                    msg["content"] += "\n\n---\n\n" + injection
                    break
            diagnosis["workflow_injected"] = True
            diagnosis["workflow_label"] = matched["label"]
        return diagnosis
    except Exception as e:
        logger.warning("Workflow injection failed (non-fatal): %s", e)
        diagnosis["workflow_injected"] = f"降级: {e}"
        return diagnosis
