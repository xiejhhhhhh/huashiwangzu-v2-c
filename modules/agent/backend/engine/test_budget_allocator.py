"""Tests for budget_allocator.py — diminishing returns tracker + context assembly."""
from .budget_allocator import DiminishingBudgetTracker, DiminishingReturnRecord


class TestDiminishingBudgetTracker:
    def test_no_stop_before_min_rounds(self):
        tracker = DiminishingBudgetTracker()
        should_stop, reason = tracker.should_stop("test_1")
        assert should_stop is False
        assert reason == ""

    def test_no_stop_with_high_gains(self):
        tracker = DiminishingBudgetTracker()
        for i in range(5):
            tracker.record_round("test_2", tokens_before=i * 1000, tokens_after=(i + 1) * 1000)
        should_stop, reason = tracker.should_stop("test_2")
        assert should_stop is False

    def test_stop_on_low_gains(self):
        tracker = DiminishingBudgetTracker()
        for i in range(5):
            tracker.record_round("test_3", tokens_before=i * 1000, tokens_after=i * 1000 + 100)
        should_stop, reason = tracker.should_stop("test_3")
        assert should_stop is True
        assert "收益递减" in reason
        assert "净增" in reason

    def test_stop_on_monotonic_decline(self):
        tracker = DiminishingBudgetTracker()
        tracker.record_round("test_4", tokens_before=0, tokens_after=2000)
        tracker.record_round("test_4", tokens_before=2000, tokens_after=3000)
        tracker.record_round("test_4", tokens_before=3000, tokens_after=3400)
        tracker.record_round("test_4", tokens_before=3400, tokens_after=3600)
        should_stop, reason = tracker.should_stop("test_4")
        assert should_stop is True
        assert "单调下降" in reason

    def test_reset_clears_state(self):
        tracker = DiminishingBudgetTracker()
        tracker.record_round("test_5", tokens_before=0, tokens_after=100)
        tracker.record_round("test_5", tokens_before=100, tokens_after=150)
        tracker.record_round("test_5", tokens_before=150, tokens_after=180)
        tracker.reset("test_5")
        should_stop, reason = tracker.should_stop("test_5")
        assert should_stop is False
        assert reason == ""

    def test_get_diagnosis(self):
        tracker = DiminishingBudgetTracker()
        session_key = "test_6_isolated"
        tracker.reset(session_key)
        tracker.record_round(session_key, tokens_before=0, tokens_after=1000)
        tracker.record_round(session_key, tokens_before=1000, tokens_after=1500)
        diag = tracker.get_diagnosis(session_key)
        assert diag["total_rounds"] == 2
        assert diag["recent_gains"] == [1000, 500]
        tracker.reset(session_key)

    def test_net_gain_never_negative(self):
        tracker = DiminishingBudgetTracker()
        rec = tracker.record_round("test_7", tokens_before=1000, tokens_after=800)
        assert rec.net_gain_tokens >= 0
