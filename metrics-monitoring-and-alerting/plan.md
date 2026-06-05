# Plan (Iteration 1)

Task: Metrics Monitoring and Alerting System
=======================================
SDI Vol 2 Reference: Chapter 5 - Metrics Monitoring and Alerting System

Overview
--------
Build a time-series metrics monitoring system that collects, stores, aggregates,
and alerts on application metrics. Supports multiple aggregation functions,
downsampling for storage efficiency, configurable alerting rules with a state
machine, and retention policies. Similar to Prometheus, Datadog, or Grafana.

Requirements
------------
1. Metric ingestion: accept data points with metric name, value, timestamp,
   and tags (key-value labels).
2. Storage: store raw data points in a time-series structure indexed by
   metric name and tags.
3. Aggregation queries: support sum, avg, min, max, count, and percentile
   (p50, p90, p95, p99) over time ranges, optionally grouped by tags.
4. Downsampling: automatically downsample old data into coarser intervals
   (e.g., 1-min raw → 5-min after 1 day → 1-hour after 7 days).
5. Alerting rules: define threshold alerts (metric > X for Y duration)
   and rate-of-change alerts (metric changes by > Z% in W window).
6. Alert state machine: OK → PENDING → ALERTING → RESOLVED. Require the
   condition to persist for a configurable evaluation period before firing.
7. Alert notifications via callbacks.
8. Retention policies: auto-delete data older than configurable age.
9. Dashboard queries: query multiple metrics at once, return time-bucketed
   results for charting.

Interface
---------
class DataPoint:
    def __init__(self, metric: str, value: float, timestamp: float,
                 tags: dict = None):
        """A single metric data point."""

class AlertRule:
    def __init__(self, name: str, metric: str, condition: str,
                 threshold: float, duration_seconds: float = 60,
                 tags_filter: dict = None):
        """An alerting rule. condition: 'gt', 'lt', 'gte', 'lte', 'rate_change'."""

class Alert:
    def __init__(self, rule_name: str, state: str, triggered_at: float,
                 value: float):
        """An active or resolved alert."""

class MetricsService:
    def __init__(self, retention_seconds: float = 86400 * 30):
        """Initialize metrics service with retention policy."""

    def ingest(self, data_point: DataPoint) -> None:
        """Record a data point."""

    def ingest_batch(self, data_points: list[DataPoint]) -> None:
        """Record multiple data points."""

    def query(self, metric: str, start: float, end: float,
              aggregation: str = "avg", interval_seconds: float = 60,
              tags_filter: dict = None,
              group_by: list[str] = None) -> list[dict]:
        """Query aggregated metric data over a time range."""

    def add_alert_rule(self, rule: AlertRule) -> None:
        """Add an alerting rule."""

    def remove_alert_rule(self, rule_name: str) -> None:
        """Remove an alerting rule."""

    def evaluate_alerts(self, current_time: float) -> list[Alert]:
        """Evaluate all alert rules and return state changes."""

    def get_active_alerts(self) -> list[Alert]:
        """Return all currently firing alerts."""

    def on_alert(self, callback: callable) -> None:
        """Register a callback for alert state changes."""

    def downsample(self, current_time: float) -> int:
        """Run downsampling. Returns number of data points compacted."""

    def apply_retention(self, current_time: float) -> int:
        """Delete data older than retention period. Returns points removed."""

    def get_metrics(self) -> list[str]:
        """List all known metric names."""

Example Usage
-------------
    svc = MetricsService()

    # Ingest CPU metrics
    for i in range(60):
        svc.ingest(DataPoint("cpu.usage", 45 + i * 0.5, timestamp=1000 + i * 60,
                             tags={"host": "web-1"}))

    # Query average CPU over the full range
    results = svc.query("cpu.usage", start=1000, end=4600,
                        aggregation="avg", interval_seconds=300)
    assert len(results) > 0

    # Percentile query
    results = svc.query("cpu.usage", start=1000, end=4600,
                        aggregation="p99", interval_seconds=3600)

    # Alert rule
    svc.add_alert_rule(AlertRule("high_cpu", "cpu.usage", "gt", 70.0,
                                 duration_seconds=120))

    # Evaluate
    alerts = svc.evaluate_alerts(current_time=4600)

Constraints
-----------
- Handle up to 1,000,000 data points per metric.
- Aggregation queries should handle large ranges efficiently.
- Alert evaluation is pull-based (called periodically).
- Tags are string key-value pairs.
- Target: 250-400 lines of Python.

Testing Requirements
--------------------
1. Basic ingest and query returns correct values.
2. Aggregation functions: sum, avg, min, max, count, p99.
3. Tag filtering on queries works.
4. Group-by produces separate series per tag value.
5. Alert state machine transitions: OK → PENDING → ALERTING.
6. Alert resolves when condition clears: ALERTING → RESOLVED.
7. Alert requires duration before firing (not instant).
8. Rate-of-change alert detects spikes.
9. Downsampling reduces data point count.
10. Retention deletes old data.
11. Alert callback is invoked on state change.
12. Multiple metrics are independent.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `PLAN.md`. 

**Summary:** Use a dict keyed by `(metric, frozen_tags)` → sorted `(timestamp, value)` lists with bisect for fast range queries. Bucket and aggregate in query time. Alert state machine tracks per-rule state with `pending_since` for duration gating. Downsampling replaces old raw points with coarser pre-aggregated buckets. Straightforward, fits the 250-400 line target. High confidence.

[Committed changes to planner branch]