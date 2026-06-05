"""Ad click event aggregation with tumbling windows, deduplication, and late event handling."""

import math
from dataclasses import dataclass, field
from enum import Enum


class WindowState(Enum):
    OPEN = "open"
    CLOSED = "closed"
    FINALIZED = "finalized"


@dataclass
class ClickEvent:
    """A click event."""
    event_id: str
    ad_id: str
    user_id: str
    timestamp: float
    metadata: dict = field(default_factory=dict)


@dataclass
class AggregationResult:
    """Aggregated result for a window."""
    ad_id: str
    window_start: float
    window_end: float
    count: int
    unique_users: int


@dataclass
class _Window:
    """Internal window state."""
    ad_id: str
    start: float
    end: float
    count: int = 0
    users: set = field(default_factory=set)
    state: WindowState = WindowState.OPEN


class ClickAggregator:
    """Tumbling-window click aggregator with dedup, late events, and watermark."""

    def __init__(self, window_size_seconds: float = 60, allowed_lateness_seconds: float = 300):
        self.window_size = window_size_seconds
        self.allowed_lateness = allowed_lateness_seconds
        self.watermark = 0.0
        # windows[ad_id][window_start] -> _Window
        self.windows: dict[str, dict[float, _Window]] = {}
        # dedup: event_id -> timestamp
        self.seen_events: dict[str, float] = {}
        # stats
        self.stats = {"total": 0, "accepted": 0, "deduplicated": 0, "late_rejected": 0, "late_accepted": 0}

    def _window_start(self, timestamp: float) -> float:
        return math.floor(timestamp / self.window_size) * self.window_size

    def _get_or_create_window(self, ad_id: str, window_start: float) -> _Window:
        if ad_id not in self.windows:
            self.windows[ad_id] = {}
        if window_start not in self.windows[ad_id]:
            self.windows[ad_id][window_start] = _Window(
                ad_id=ad_id, start=window_start, end=window_start + self.window_size
            )
        return self.windows[ad_id][window_start]

    def process_event(self, event: ClickEvent) -> bool:
        """Process a click event. Returns False if deduplicated or rejected."""
        self.stats["total"] += 1

        # Dedup check
        if event.event_id in self.seen_events:
            self.stats["deduplicated"] += 1
            return False

        ws = self._window_start(event.timestamp)
        window = self._get_or_create_window(event.ad_id, ws)

        # Check window state
        if window.state == WindowState.FINALIZED:
            self.stats["late_rejected"] += 1
            return False

        if window.state == WindowState.CLOSED:
            # Check if within allowed lateness
            if self.watermark - window.end > self.allowed_lateness:
                window.state = WindowState.FINALIZED
                self.stats["late_rejected"] += 1
                return False
            self.stats["late_accepted"] += 1

        # Record event
        self.seen_events[event.event_id] = event.timestamp
        window.count += 1
        window.users.add(event.user_id)
        self.stats["accepted"] += 1
        return True

    def process_batch(self, events: list[ClickEvent]) -> dict:
        """Process a batch. Returns {accepted, deduplicated, late_rejected}."""
        result = {"accepted": 0, "deduplicated": 0, "late_rejected": 0}
        for event in events:
            before_dedup = self.stats["deduplicated"]
            before_rejected = self.stats["late_rejected"]
            if self.process_event(event):
                result["accepted"] += 1
            elif self.stats["deduplicated"] > before_dedup:
                result["deduplicated"] += 1
            elif self.stats["late_rejected"] > before_rejected:
                result["late_rejected"] += 1
        return result

    def advance_watermark(self, timestamp: float) -> list[AggregationResult]:
        """Advance watermark. Returns newly finalized windows."""
        if timestamp <= self.watermark:
            return []
        self.watermark = timestamp
        finalized = []

        # Prune old dedup entries (older than 2x allowed lateness)
        cutoff = timestamp - 2 * self.allowed_lateness
        self.seen_events = {eid: ts for eid, ts in self.seen_events.items() if ts >= cutoff}

        for ad_id, ad_windows in self.windows.items():
            for ws, window in ad_windows.items():
                if window.state == WindowState.FINALIZED:
                    continue
                if window.end <= timestamp - self.allowed_lateness:
                    window.state = WindowState.FINALIZED
                    finalized.append(AggregationResult(
                        ad_id=ad_id, window_start=window.start, window_end=window.end,
                        count=window.count, unique_users=len(window.users)
                    ))
                elif window.end <= timestamp:
                    window.state = WindowState.CLOSED

        return finalized

    def query(self, ad_id: str, start_time: float, end_time: float) -> list[AggregationResult]:
        """Query aggregated counts for an ad in a time range."""
        results = []
        if ad_id not in self.windows:
            return results
        for ws, window in sorted(self.windows[ad_id].items()):
            if window.end > start_time and window.start < end_time:
                results.append(AggregationResult(
                    ad_id=ad_id, window_start=window.start, window_end=window.end,
                    count=window.count, unique_users=len(window.users)
                ))
        return results

    def query_top_ads(self, start_time: float, end_time: float, k: int = 10) -> list[tuple[str, int]]:
        """Get top-K ads by click count in a time range."""
        counts: dict[str, int] = {}
        for ad_id, ad_windows in self.windows.items():
            for ws, window in ad_windows.items():
                if window.end > start_time and window.start < end_time:
                    counts[ad_id] = counts.get(ad_id, 0) + window.count
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:k]

    def get_window_state(self, ad_id: str, window_start: float) -> str:
        """Get window state: 'open', 'closed', or 'finalized'."""
        if ad_id in self.windows and window_start in self.windows[ad_id]:
            return self.windows[ad_id][window_start].state.value
        return "unknown"

    def get_stats(self) -> dict:
        """Return processing stats."""
        return dict(self.stats)
