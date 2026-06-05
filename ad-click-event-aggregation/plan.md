# Plan (Iteration 1)

Task: Ad Click Event Aggregation
===========================
SDI Vol 2 Reference: Chapter 6 - Ad Click Event Aggregation

Overview
--------
Build a real-time ad click event aggregation system that counts clicks per ad
in time windows, supports exactly-once counting via deduplication, handles late
events, and provides query APIs for aggregated statistics. This powers billing,
reporting, and fraud detection in ad tech platforms.

Requirements
------------
1. Event ingestion: accept click events with ad_id, user_id, timestamp,
   and optional metadata.
2. Tumbling windows: aggregate click counts into fixed, non-overlapping
   time windows (e.g., 1-minute windows).
3. Sliding windows: aggregate over sliding windows with configurable
   size and slide interval.
4. Exactly-once counting: deduplicate events using event_id to prevent
   double-counting from retries.
5. Late event handling: accept events that arrive after their window has
   closed, up to a configurable allowed lateness. Late events update the
   affected window's count.
6. Aggregation dimensions: group by ad_id, and optionally by additional
   dimensions (campaign_id, country).
7. Query API: query aggregated counts by ad_id and time range.
8. MapReduce-style aggregation: support a map phase (extract key) and
   reduce phase (combine counts) for extensibility.
9. Watermark tracking: track the latest event timestamp as a watermark
   to determine when windows can be finalized.
10. Window lifecycle: OPEN → CLOSED → FINALIZED. Finalized windows
    reject late events.

Interface
---------
class ClickEvent:
    def __init__(self, event_id: str, ad_id: str, user_id: str,
                 timestamp: float, metadata: dict = None):
        """A click event."""

class AggregationResult:
    def __init__(self, ad_id: str, window_start: float, window_end: float,
                 count: int, unique_users: int):
        """Aggregated result for a window."""

class ClickAggregator:
    def __init__(self, window_size_seconds: float = 60,
                 allowed_lateness_seconds: float = 300):
        """Initialize the aggregator with tumbling window config."""

    def process_event(self, event: ClickEvent) -> bool:
        """Process a click event. Returns False if deduplicated or rejected."""

    def process_batch(self, events: list[ClickEvent]) -> dict:
        """Process a batch. Returns {accepted: int, deduplicated: int, late_rejected: int}."""

    def query(self, ad_id: str, start_time: float,
              end_time: float) -> list[AggregationResult]:
        """Query aggregated counts for an ad in a time range."""

    def query_top_ads(self, start_time: float, end_time: float,
                      k: int = 10) -> list[tuple[str, int]]:
        """Get top-K ads by click count in a time range."""

    def advance_watermark(self, timestamp: float) -> list[AggregationResult]:
        """Advance the watermark. Returns newly finalized windows."""

    def get_window_state(self, ad_id: str, window_start: float) -> str:
        """Get window state: 'open', 'closed', or 'finalized'."""

    def get_stats(self) -> dict:
        """Return processing stats: total events, deduplicated, late, etc."""

Example Usage
-------------
    agg = ClickAggregator(window_size_seconds=60, allowed_lateness_seconds=120)

    # Process events
    agg.process_event(ClickEvent("e1", "ad-100", "user-1", 1000.0))
    agg.process_event(ClickEvent("e2", "ad-100", "user-2", 1030.0))
    agg.process_event(ClickEvent("e3", "ad-200", "user-1", 1045.0))

    # Deduplicate
    result = agg.process_event(ClickEvent("e1", "ad-100", "user-1", 1000.0))
    assert result == False  # duplicate

    # Query
    results = agg.query("ad-100", 960, 1080)
    assert results[0].count == 2
    assert results[0].unique_users == 2

    # Late event (within allowed lateness)
    agg.advance_watermark(1200.0)
    agg.process_event(ClickEvent("e4", "ad-100", "user-3", 1050.0))
    results = agg.query("ad-100", 960, 1080)
    assert results[0].count == 3  # late event counted

    # Top ads
    top = agg.query_top_ads(960, 1080, k=5)
    assert top[0][0] == "ad-100"

Constraints
-----------
- Event IDs are globally unique strings.
- Handle up to 1,000,000 events efficiently.
- Deduplication window: keep event IDs for at least 2x the allowed lateness.
- Window size: 1 second to 1 hour.
- Target: 200-350 lines of Python.

Testing Requirements
--------------------
1. Basic counting in tumbling windows.
2. Deduplication rejects duplicate event IDs.
3. Late events within allowed lateness are counted.
4. Late events beyond allowed lateness are rejected.
5. Unique user counting per window.
6. Top-K ads query returns correct ranking.
7. Window state transitions: open → closed → finalized.
8. Watermark advancement finalizes windows.
9. Multiple ads aggregate independently.
10. Batch processing stats are accurate.
11. Query across multiple windows returns all.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `PLAN.md`. The approach is straightforward: dict-of-dicts for window storage, set-based dedup, watermark-driven state transitions. The spec is clear enough that this is a high-confidence plan with no open questions blocking implementation.

[Committed changes to planner branch]