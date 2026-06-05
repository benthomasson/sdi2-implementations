"""Metrics Monitoring and Alerting System."""

import bisect
import math
from dataclasses import dataclass, field


@dataclass
class DataPoint:
    """A single metric data point."""
    metric: str
    value: float
    timestamp: float
    tags: dict = field(default_factory=dict)


@dataclass
class AlertRule:
    """An alerting rule. condition: 'gt', 'lt', 'gte', 'lte', 'rate_change'."""
    name: str
    metric: str
    condition: str
    threshold: float
    duration_seconds: float = 60
    tags_filter: dict = None


@dataclass
class Alert:
    """An active or resolved alert."""
    rule_name: str
    state: str
    triggered_at: float
    value: float


class MetricsService:
    """Time-series metrics monitoring with alerting and downsampling."""

    def __init__(self, retention_seconds: float = 86400 * 30):
        self.retention_seconds = retention_seconds
        # {(metric, frozenset(tags)): [(timestamp, value), ...]}
        self._data = {}
        # {rule_name: AlertRule}
        self._rules = {}
        # {rule_name: {"state": str, "pending_since": float|None, "value": float}}
        self._alert_states = {}
        self._callbacks = []

    def _key(self, metric, tags):
        return (metric, frozenset((tags or {}).items()))

    def ingest(self, data_point):
        """Record a data point."""
        key = self._key(data_point.metric, data_point.tags)
        if key not in self._data:
            self._data[key] = []
        series = self._data[key]
        entry = (data_point.timestamp, data_point.value)
        idx = bisect.bisect_right(series, entry)
        series.insert(idx, entry)

    def ingest_batch(self, data_points):
        """Record multiple data points."""
        for dp in data_points:
            self.ingest(dp)

    def _matching_keys(self, metric, tags_filter=None):
        """Find all keys matching metric name and optional tags filter."""
        for key in self._data:
            m, tag_set = key
            if m != metric:
                continue
            if tags_filter:
                tags_dict = dict(tag_set)
                if all(tags_dict.get(k) == v for k, v in tags_filter.items()):
                    yield key
            else:
                yield key

    def _slice(self, series, start, end):
        """Get values in [start, end] using bisect."""
        lo = bisect.bisect_left(series, (start,))
        hi = bisect.bisect_right(series, (end, float('inf')))
        return series[lo:hi]

    def _aggregate(self, values, aggregation):
        """Apply aggregation function to a list of values."""
        if not values:
            return None
        if aggregation == "sum":
            return sum(values)
        if aggregation == "avg":
            return sum(values) / len(values)
        if aggregation == "min":
            return min(values)
        if aggregation == "max":
            return max(values)
        if aggregation == "count":
            return len(values)
        if aggregation.startswith("p"):
            p = int(aggregation[1:]) / 100.0
            sorted_vals = sorted(values)
            idx = p * (len(sorted_vals) - 1)
            lo = int(math.floor(idx))
            hi = int(math.ceil(idx))
            if lo == hi:
                return sorted_vals[lo]
            frac = idx - lo
            return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac
        return sum(values) / len(values)

    def query(self, metric, start, end, aggregation="avg",
              interval_seconds=60, tags_filter=None, group_by=None):
        """Query aggregated metric data over a time range."""
        keys = list(self._matching_keys(metric, tags_filter))

        if group_by:
            # Group keys by the group_by tag values
            groups = {}
            for key in keys:
                tags_dict = dict(key[1])
                group_key = tuple(tags_dict.get(g, "") for g in group_by)
                groups.setdefault(group_key, []).append(key)

            results = []
            for group_vals, group_keys in groups.items():
                group_tags = {g: v for g, v in zip(group_by, group_vals)}
                merged = []
                for k in group_keys:
                    merged.extend(self._slice(self._data[k], start, end))
                merged.sort()
                buckets = self._bucketize(merged, start, end, interval_seconds)
                for bucket_start, values in buckets:
                    agg_val = self._aggregate(values, aggregation)
                    if agg_val is not None:
                        results.append({
                            "timestamp": bucket_start,
                            "value": agg_val,
                            "tags": group_tags,
                        })
            return results

        # No group_by: merge all matching series
        merged = []
        for k in keys:
            merged.extend(self._slice(self._data[k], start, end))
        merged.sort()

        buckets = self._bucketize(merged, start, end, interval_seconds)
        results = []
        for bucket_start, values in buckets:
            agg_val = self._aggregate(values, aggregation)
            if agg_val is not None:
                results.append({"timestamp": bucket_start, "value": agg_val})
        return results

    def _bucketize(self, points, start, end, interval_seconds):
        """Split points into time buckets."""
        buckets = []
        bucket_start = start
        while bucket_start < end:
            bucket_end = bucket_start + interval_seconds
            vals = [v for t, v in points if bucket_start <= t < bucket_end]
            if vals:
                buckets.append((bucket_start, vals))
            bucket_start = bucket_end
        return buckets

    def add_alert_rule(self, rule):
        """Add an alerting rule."""
        self._rules[rule.name] = rule
        if rule.name not in self._alert_states:
            self._alert_states[rule.name] = {
                "state": "OK", "pending_since": None, "value": 0
            }

    def remove_alert_rule(self, rule_name):
        """Remove an alerting rule."""
        self._rules.pop(rule_name, None)
        self._alert_states.pop(rule_name, None)

    def _check_condition(self, rule, current_time):
        """Check if alert condition is met. Returns (bool, value)."""
        window = max(rule.duration_seconds, 60)
        start = current_time - window
        keys = list(self._matching_keys(rule.metric, rule.tags_filter))
        all_points = []
        for k in keys:
            all_points.extend(self._slice(self._data[k], start, current_time))
        if not all_points:
            return False, 0

        all_points.sort()
        values = [v for _, v in all_points]

        if rule.condition == "rate_change":
            first_val = values[0]
            last_val = values[-1]
            if first_val == 0:
                rate = float('inf') if last_val != 0 else 0
            else:
                rate = abs((last_val - first_val) / first_val) * 100
            return rate > rule.threshold, rate

        current_val = sum(values) / len(values)
        if rule.condition == "gt":
            return current_val > rule.threshold, current_val
        if rule.condition == "lt":
            return current_val < rule.threshold, current_val
        if rule.condition == "gte":
            return current_val >= rule.threshold, current_val
        if rule.condition == "lte":
            return current_val <= rule.threshold, current_val
        return False, current_val

    def evaluate_alerts(self, current_time):
        """Evaluate all alert rules and return state changes."""
        changed = []
        for name, rule in self._rules.items():
            state = self._alert_states[name]
            condition_met, value = self._check_condition(rule, current_time)
            old_state = state["state"]

            if condition_met:
                if old_state == "OK":
                    state["state"] = "PENDING"
                    state["pending_since"] = current_time
                    state["value"] = value
                elif old_state == "PENDING":
                    elapsed = current_time - state["pending_since"]
                    if elapsed >= rule.duration_seconds:
                        state["state"] = "ALERTING"
                        state["value"] = value
                elif old_state == "RESOLVED":
                    state["state"] = "PENDING"
                    state["pending_since"] = current_time
                    state["value"] = value
                # ALERTING stays ALERTING
            else:
                if old_state in ("ALERTING", "PENDING"):
                    state["state"] = "RESOLVED" if old_state == "ALERTING" else "OK"
                    state["value"] = value

            if state["state"] != old_state:
                alert = Alert(
                    rule_name=name,
                    state=state["state"],
                    triggered_at=current_time,
                    value=state["value"],
                )
                changed.append(alert)
                for cb in self._callbacks:
                    cb(alert)

        return changed

    def get_active_alerts(self):
        """Return all currently firing alerts."""
        result = []
        for name, state in self._alert_states.items():
            if state["state"] == "ALERTING":
                result.append(Alert(
                    rule_name=name, state="ALERTING",
                    triggered_at=0, value=state["value"],
                ))
        return result

    def on_alert(self, callback):
        """Register a callback for alert state changes."""
        self._callbacks.append(callback)

    def downsample(self, current_time):
        """Run downsampling. Returns number of data points compacted."""
        compacted = 0
        one_day = 86400
        seven_days = 7 * one_day
        rules = [
            (one_day, seven_days, 300),      # 1-7 days old -> 5-min buckets
            (seven_days, float('inf'), 3600), # >7 days old -> 1-hour buckets
        ]
        for key in list(self._data.keys()):
            series = self._data[key]
            new_series = []
            for min_age, max_age, interval in rules:
                cutoff_start = current_time - max_age
                cutoff_end = current_time - min_age
                old_points = self._slice(series, cutoff_start, cutoff_end)
                if len(old_points) <= 1:
                    continue
                # Bucket and average
                buckets = {}
                for ts, val in old_points:
                    bucket = int(ts // interval) * interval
                    buckets.setdefault(bucket, []).append(val)
                downsampled = [(float(b), sum(v)/len(v)) for b, v in sorted(buckets.items())]
                compacted += len(old_points) - len(downsampled)
                # Remove old points and insert downsampled
                remaining = [p for p in series if not (cutoff_start <= p[0] <= cutoff_end)]
                remaining.extend(downsampled)
                remaining.sort()
                series = remaining
            self._data[key] = series
        return compacted

    def apply_retention(self, current_time):
        """Delete data older than retention period. Returns points removed."""
        cutoff = current_time - self.retention_seconds
        removed = 0
        for key in list(self._data.keys()):
            series = self._data[key]
            idx = bisect.bisect_left(series, (cutoff,))
            if idx > 0:
                removed += idx
                self._data[key] = series[idx:]
            if not self._data[key]:
                del self._data[key]
        return removed

    def get_metrics(self):
        """List all known metric names."""
        return list(set(m for m, _ in self._data.keys()))
