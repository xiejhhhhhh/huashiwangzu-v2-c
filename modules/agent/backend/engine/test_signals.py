"""Tests for signal bus."""
import pytest

from .signals import SignalBus, emit_signal, get_signal_bus, get_signal_summary


class TestSignalBus:
    def test_emit_and_latest(self):
        bus = SignalBus(max_history=10)
        bus.emit("memory_recall_quality", 0.85, "good recall")
        assert bus.latest("memory_recall_quality") == 0.85
        assert bus.latest("nonexistent", default=-1.0) == -1.0

    def test_average(self):
        bus = SignalBus(max_history=10)
        bus.emit("budget_pressure", 0.3)
        bus.emit("budget_pressure", 0.5)
        bus.emit("budget_pressure", 0.7)
        assert bus.average("budget_pressure", n=3) == pytest.approx(0.5)

    def test_average_with_insufficient_data(self):
        bus = SignalBus(max_history=10)
        bus.emit("tool_failure_rate", 1.0)
        avg = bus.average("tool_failure_rate", n=5)
        assert avg == 1.0

    def test_window_returns_recent(self):
        bus = SignalBus(max_history=10)
        bus.emit("test_sig", 1.0)
        bus.emit("test_sig", 2.0)
        bus.emit("other", 99.0)
        window = bus.window("test_sig", n=2)
        assert len(window) == 2
        assert [r.value for r in window] == [1.0, 2.0]

    def test_window_with_gap(self):
        bus = SignalBus(max_history=10)
        bus.emit("a", 1.0)
        bus.emit("b", 2.0)
        bus.emit("a", 3.0)
        assert len(bus.window("a", n=10)) == 2

    def test_all_signals_returns_latest_per_type(self):
        bus = SignalBus(max_history=10)
        bus.emit("x", 1.0)
        bus.emit("y", 2.0)
        bus.emit("x", 3.0)
        all_s = bus.all_signals()
        assert all_s["x"] == 3.0
        assert all_s["y"] == 2.0

    def test_summary_shape(self):
        bus = SignalBus(max_history=10)
        bus.emit("memory_recall_quality", 0.9)
        bus.emit("budget_pressure", 0.4)
        bus.emit("tool_failure_rate", 0.0)
        s = bus.summary()
        assert "memory_quality" in s
        assert "budget_pressure" in s
        assert "tool_failure_rate" in s
        assert "total_signals" in s

    def test_ring_buffer_eviction(self):
        bus = SignalBus(max_history=3)
        for i in range(5):
            bus.emit("evict", float(i))
        assert len(bus._history) == 3
        assert bus.latest("evict") == 4.0


class TestSingleton:
    def test_get_signal_bus_returns_same_instance(self):
        b1 = get_signal_bus()
        b2 = get_signal_bus()
        assert b1 is b2

    def test_emit_signal_function(self):
        bus = get_signal_bus()
        reset_history = bus._history
        bus._history.clear()
        emit_signal("degradation_status", 1.0, "test fallback")
        assert bus.latest("degradation_status") == 1.0
        bus._history = reset_history

    def test_get_signal_summary(self):
        summary = get_signal_summary()
        assert isinstance(summary, dict)
        assert "memory_quality" in summary
