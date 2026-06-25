"""Runtime policy: stop policy, budget pressure, stuck detection, inline recovery.

Consolidates the scattered stop/budget/stuck thresholds from the old
``chat.py`` into a single configurable policy object.  All the precision
handles (MAX_TOOL_ROUNDS, stuck thresholds, diminishing returns, etc.)
live here and can be overridden per-conversation or per-agent-config.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SLOW_SKILL_NAMES: set[str] = {
    "image-gen__generate",
    "office-gen__convert",
}


@dataclass
class RuntimePolicy:
    """Configurable runtime policy for the agent chat tool loop.

    All stop/budget/stuck/recovery thresholds live here as a single
    policy object.  Future AgentConfig overrides can create a custom
    policy per-agent-code by setting these fields before the run.

    Attributes:
        max_tool_rounds: Maximum tool-call iterations before forcing
            a final summary turn.
        slow_skill_names: Set of skill/module names that execute in
            the background task queue instead of inline.
        stuck_consecutive_threshold: How many identical tool-call
            fingerprints before the stuck detector fires.
        diminishing_budget_threshold: Token-growth ratio below which
            the budget tracker considers returns "diminishing".
        allow_inline_tool_recovery: When True, stream content is
            scanned for inline XML tool calls after streaming.
        allow_final_summary_fallback: When True, a final summary turn
            is generated when all tool rounds are exhausted.
    """

    max_tool_rounds: int = 5
    slow_skill_names: set[str] = field(default_factory=lambda: set(SLOW_SKILL_NAMES))
    stuck_consecutive_threshold: int = 3
    diminishing_budget_threshold: float = 0.15
    allow_inline_tool_recovery: bool = True
    allow_final_summary_fallback: bool = True

    # ── Convenience factory ────────────────────────────────────────

    @classmethod
    def default(cls) -> RuntimePolicy:
        return cls()
