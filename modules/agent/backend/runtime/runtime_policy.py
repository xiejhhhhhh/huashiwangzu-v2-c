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
        fast_tool_timeout_seconds: Hard timeout for inline tool calls so
            one slow capability cannot exhaust the whole chat response.
    """

    max_tool_rounds: int = 5
    slow_skill_names: set[str] = field(default_factory=lambda: set(SLOW_SKILL_NAMES))
    stuck_consecutive_threshold: int = 3
    diminishing_budget_threshold: float = 0.15
    allow_inline_tool_recovery: bool = False
    allow_final_summary_fallback: bool = True
    enable_single_pass_streaming_tools: bool = True
    llm_stop_decision_enabled: bool = False
    fast_tool_timeout_seconds: float = 18.0

    # ── Checkpointer (crash recovery) ──────────────────────────────

    enable_checkpointer: bool = False
    checkpoint_interval: int = 1

    # ── Understanding loop precision handles ───────────────────────

    enable_understanding_loop: bool = False
    understanding_max_rounds: int = 2
    understanding_min_chars: int = 20

    # ── Generic intent preflight ─────────────────────────────────────

    intent_preflight_enabled: bool = True
    intent_preflight_mode: str = "rules"
    intent_preflight_min_confidence: float = 0.75
    intent_preflight_max_llm_calls: int = 0
    intent_preflight_use_verifier: bool = False
    intent_preflight_allow_short_circuit: bool = False
    intent_preflight_force_for_evidence_sensitive: bool = True
    intent_preflight_force_for_operation_path: bool = True

    # ── Convenience factory ────────────────────────────────────────

    @classmethod
    def default(cls) -> RuntimePolicy:
        return cls()
