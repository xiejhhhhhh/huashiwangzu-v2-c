"""轻量 Gate 校验链：子 Agent 输出质量验证。

借鉴 Draftpaper-loop 的 IntegrityGate 模式：
- 每个 gate 是一个纯 async 函数，输入 result dict，输出 GateResult
- 多个 gate 组合成链，全部执行不短路
- error → 触发重试；warning → 允许通过但带标记
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

logger = logging.getLogger("v2.agent").getChild("gate")


@dataclass
class GateIssue:
    severity: str   # "error" | "warning"
    code: str       # 机器可读，如 "missing_conclusion"
    message: str    # 人类可读的描述


@dataclass
class GateResult:
    passed: bool
    issues: list[GateIssue] = field(default_factory=list)


GateFn = Callable[[dict], Awaitable[GateResult]]


# ── 内置 Gate ─────────────────────────────────────────


async def gate_has_conclusion(result: dict) -> GateResult:
    """子 Agent 必须有结论。"""
    c = result.get("conclusion", "")
    if not c or c == "子 Agent 未生成结论":
        return GateResult(False, [
            GateIssue("error", "missing_conclusion", "子 Agent 未生成结论"),
        ])
    return GateResult(True)


async def gate_min_length(result: dict, min_chars: int = 50) -> GateResult:
    """结论不能太短。"""
    c = result.get("conclusion", "")
    if len(c.strip()) < min_chars:
        return GateResult(False, [
            GateIssue("warning", "conclusion_too_short",
                      f"结论仅 {len(c.strip())} 字符，建议至少 {min_chars} 字符"),
        ])
    return GateResult(True)


async def gate_no_error(result: dict) -> GateResult:
    """子 Agent 执行不能报错。"""
    if result.get("error"):
        return GateResult(False, [
            GateIssue("error", "execution_error", f"子 Agent 执行错误：{result['error']}"),
        ])
    return GateResult(True)


async def gate_rounds_reasonable(result: dict, max_rounds: int = 15) -> GateResult:
    """工具调用轮次在合理范围内。"""
    rounds = result.get("rounds_used", 0)
    if rounds >= max_rounds:
        return GateResult(False, [
            GateIssue("warning", "too_many_rounds",
                      f"使用了 {rounds} 轮工具调用（上限 {max_rounds}），可能陷入循环"),
        ])
    return GateResult(True)


DEFAULT_GATES: list[GateFn] = [
    gate_has_conclusion,
    gate_no_error,
    gate_min_length,
    gate_rounds_reasonable,
]


async def run_gates(
    result: dict,
    gates: list[GateFn] | None = None,
) -> GateResult:
    """执行 gate 校验链。

    所有 gate 都跑完再汇总结果，不短路。
    只要有一个 error 级别的 issue，passed = False。
    纯 warning 级别的 issue 允许通过。
    """
    gates = gates or DEFAULT_GATES
    all_issues: list[GateIssue] = []
    for gate_fn in gates:
        try:
            gr = await gate_fn(result)
            all_issues.extend(gr.issues)
        except Exception as e:
            all_issues.append(
                GateIssue("error", "gate_crash",
                          f"Gate '{gate_fn.__name__}' 执行异常：{e}"),
            )
    has_error = any(iss.severity == "error" for iss in all_issues)
    return GateResult(passed=not has_error, issues=all_issues)
