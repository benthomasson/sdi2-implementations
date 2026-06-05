"""Tests for ad click event aggregation system."""

import time
from click_aggregator import ClickEvent, ClickAggregator, AggregationResult


def test_basic_tumbling_window():
    """Basic counting: 3 events in same window produce count=3."""
    agg = ClickAggregator(window_size_seconds=60)
    # All 3 events in window [960, 1020): timestamps 961, 970, 1010
    agg.process_event(ClickEvent("e1", "ad-100", "user-1", 961.0))
    agg.process_event(ClickEvent("e2", "ad-100", "user-2", 970.0))
    agg.process_event(ClickEvent("e3", "ad-100", "user-3", 1010.0))
    results = agg.query("ad-100", 960, 1020)
    assert len(results) == 1
    assert results[0].count == 3
    assert results[0].unique_users == 3
    assert results[0].window_start == 960.0
    assert results[0].window_end == 1020.0


def test_deduplication():
    """Duplicate event_id is rejected, count stays at 1."""
    agg = ClickAggregator(window_size_seconds=60)
    assert agg.process_event(ClickEvent("e1", "ad-100", "user-1", 1000.0)) is True
    assert agg.process_event(ClickEvent("e1", "ad-100", "user-1", 1000.0)) is False
    assert agg.process_event(ClickEvent("e1", "ad-200", "user-2", 1005.0)) is False  # same ID, different ad
    results = agg.query("ad-100", 960, 1080)
    assert results[0].count == 1
    stats = agg.get_stats()
    assert stats["deduplicated"] == 2


def test_late_event_accepted_within_lateness():
    """Late event within allowed lateness updates closed window."""
    agg = ClickAggregator(window_size_seconds=60, allowed_lateness_seconds=120)
    agg.process_event(ClickEvent("e1", "ad-100", "user-1", 1000.0))
    agg.advance_watermark(1100.0)  # window [960,1020) -> CLOSED
    assert agg.get_window_state("ad-100", 960.0) == "closed"
    # Late event still accepted
    assert agg.process_event(ClickEvent("e2", "ad-100", "user-2", 1010.0)) is True
    results = agg.query("ad-100", 960, 1080)
    assert results[0].count == 2


def test_late_event_rejected_beyond_lateness():
    """Late event beyond allowed lateness is rejected from finalized window."""
    agg = ClickAggregator(window_size_seconds=60, allowed_lateness_seconds=120)
    agg.process_event(ClickEvent("e1", "ad-100", "user-1", 1000.0))
    agg.advance_watermark(1200.0)  # window [960,1020) -> FINALIZED (1020 <= 1200-120)
    assert agg.get_window_state("ad-100", 960.0) == "finalized"
    assert agg.process_event(ClickEvent("e2", "ad-100", "user-2", 1010.0)) is False
    stats = agg.get_stats()
    assert stats["late_rejected"] >= 1


def test_window_lifecycle():
    """Window transitions: OPEN -> CLOSED -> FINALIZED."""
    agg = ClickAggregator(window_size_seconds=60, allowed_lateness_seconds=120)
    agg.process_event(ClickEvent("e1", "ad-100", "user-1", 1000.0))
    assert agg.get_window_state("ad-100", 960.0) == "open"
    agg.advance_watermark(1050.0)
    assert agg.get_window_state("ad-100", 960.0) == "closed"
    agg.advance_watermark(1200.0)
    assert agg.get_window_state("ad-100", 960.0) == "finalized"


def test_watermark_returns_finalized():
    """advance_watermark returns newly finalized AggregationResults."""
    agg = ClickAggregator(window_size_seconds=60, allowed_lateness_seconds=60)
    agg.process_event(ClickEvent("e1", "ad-100", "user-1", 1000.0))
    agg.process_event(ClickEvent("e2", "ad-200", "user-2", 1000.0))
    finalized = agg.advance_watermark(1200.0)
    assert len(finalized) == 2
    assert all(isinstance(r, AggregationResult) for r in finalized)
    ad_ids = {r.ad_id for r in finalized}
    assert ad_ids == {"ad-100", "ad-200"}


def test_batch_processing():
    """Batch processing returns correct accepted/deduplicated/late_rejected counts."""
    agg = ClickAggregator(window_size_seconds=60, allowed_lateness_seconds=60)
    agg.process_event(ClickEvent("e0", "ad-100", "user-1", 1000.0))
    agg.advance_watermark(1200.0)  # finalize window [960,1020)

    events = [
        ClickEvent("e1", "ad-100", "user-1", 1500.0),  # accepted
        ClickEvent("e2", "ad-100", "user-2", 1510.0),  # accepted
        ClickEvent("e1", "ad-100", "user-1", 1500.0),  # duplicate
        ClickEvent("e3", "ad-100", "user-3", 1005.0),  # late rejected
    ]
    result = agg.process_batch(events)
    assert result["accepted"] == 2
    assert result["deduplicated"] == 1
    assert result["late_rejected"] == 1


def test_top_k_ads():
    """Top-K query returns ads ranked by total clicks."""
    agg = ClickAggregator(window_size_seconds=60)
    for i in range(5):
        agg.process_event(ClickEvent(f"a{i}", "ad-100", f"u{i}", 1000.0 + i))
    for i in range(3):
        agg.process_event(ClickEvent(f"b{i}", "ad-200", f"u{i}", 1000.0 + i))
    for i in range(1):
        agg.process_event(ClickEvent(f"c{i}", "ad-300", f"u{i}", 1000.0 + i))
    top = agg.query_top_ads(960, 1080, k=2)
    assert len(top) == 2
    assert top[0] == ("ad-100", 5)
    assert top[1] == ("ad-200", 3)


def test_query_multiple_windows():
    """Query spanning multiple windows returns all matching."""
    agg = ClickAggregator(window_size_seconds=60)
    agg.process_event(ClickEvent("e1", "ad-100", "user-1", 1000.0))   # [960, 1020)
    agg.process_event(ClickEvent("e2", "ad-100", "user-2", 1050.0))   # [1020, 1080)
    agg.process_event(ClickEvent("e3", "ad-100", "user-3", 1100.0))   # [1080, 1140)
    results = agg.query("ad-100", 960, 1140)
    assert len(results) == 3
    assert sum(r.count for r in results) == 3


def test_query_empty_and_unknown():
    """Querying unknown ad or empty range returns empty list."""
    agg = ClickAggregator(window_size_seconds=60)
    assert agg.query("nonexistent", 0, 9999) == []
    assert agg.get_window_state("nonexistent", 0.0) == "unknown"


if __name__ == "__main__":
    tests = [
        test_basic_tumbling_window,
        test_deduplication,
        test_late_event_accepted_within_lateness,
        test_late_event_rejected_beyond_lateness,
        test_window_lifecycle,
        test_watermark_returns_finalized,
        test_batch_processing,
        test_top_k_ads,
        test_query_multiple_windows,
        test_query_empty_and_unknown,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__doc__}")
            passed += 1
        except Exception as e:
            print(f"FAIL: {t.__doc__} - {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} tests passed")
