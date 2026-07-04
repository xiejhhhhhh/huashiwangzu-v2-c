"""Memory signal bus: collects runtime signals that influence engine decisions.

Signals are lightweight sensor readings collected at each turn and stored
in a per-worker ring buffer. Downstream consumers (skill injection,
compression, tool selection, budget) read the latest window to adapt
their behaviour.

Signal types:
  - memory_recall_quality — hit rate, credibility, noise
  - budget_pressure — how close we are to the context limit
  - degradation_status — whether a fallback happened recently
  - tool_failure_rate — recent tool call failure proportion
  - diminishing_returns — whether the current loop is losing information gain
"""
import logging
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger("v2.agent").getChild("engine.signals")

_MAX_SIGNAL_HISTORY = 20


@dataclass
class SignalReading:
    timestamp: float
    signal_type: str
    value: float
    detail: str = ""


class SignalBus:
    """Per-worker ring buffer of runtime signals.

    Not persisted across workers — the agent engine reads the recent
    window to modulate its behaviour.  Critical state (e.g. locked
    resources) still goes through the DB.
    """

    def __init__(self, max_history: int = _MAX_SIGNAL_HISTORY) -> None:
        self._history: deque[SignalReading] = deque(maxlen=max_history)

    def emit(self, signal_type: str, value: float, detail: str = "") -> None:
        self._history.append(SignalReading(
            timestamp=time.time(),
            signal_type=signal_type,
            value=value,
            detail=detail,
        ))

    def latest(self, signal_type: str, default: float = 0.0) -> float:
        for s in reversed(self._history):
            if s.signal_type == signal_type:
                return s.value
        return default

    def window(self, signal_type: str, n: int = 5) -> list[SignalReading]:
        return [s for s in self._history if s.signal_type == signal_type][-n:]

    def average(self, signal_type: str, n: int = 5, default: float = 0.0) -> float:
        readings = self.window(signal_type, n)
        if not readings:
            return default
        return sum(r.value for r in readings) / len(readings)

    def all_signals(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for s in reversed(self._history):
            if s.signal_type not in result:
                result[s.signal_type] = s.value
        return result

    def summary(self) -> dict:
        return {
            "memory_quality": self.average("memory_recall_quality", n=3),
            "budget_pressure": self.latest("budget_pressure"),
            "degradation_status": self.latest("degradation_status"),
            "tool_failure_rate": self.average("tool_failure_rate", n=5),
            "diminishing_returns": self.latest("diminishing_returns"),
            "total_signals": len(self._history),
        }


# Module-level singleton
_bus: SignalBus | None = None


def get_signal_bus() -> SignalBus:
    global _bus
    if _bus is None:
        _bus = SignalBus()
    return _bus


def emit_signal(signal_type: str, value: float, detail: str = "") -> None:
    get_signal_bus().emit(signal_type, value, detail)


def get_signal_summary() -> dict:
    return get_signal_bus().summary()
