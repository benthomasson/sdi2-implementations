# Plan Review: Metrics Monitoring and Alerting

## Plan Strengths

- Time-series storage indexed by `(metric, frozenset(tags))` with bisect-sorted lists. O(log n) range queries via `bisect_left`/`bisect_right`.
- Full aggregation suite: sum, avg, min, max, count, and percentile (linear interpolation between nearest ranks). Percentile uses sorted values with fractional index interpolation.
- Alert state machine: OK -> PENDING -> ALERTING -> RESOLVED. PENDING requires condition to persist for `duration_seconds` before firing. PENDING reverts to OK if condition clears.
- Rate-of-change alert: `abs((last - first) / first) * 100` over the lookback window. Handles division by zero.
- Downsampling with two tiers: 1-7 days old -> 5-min buckets, >7 days -> 1-hour buckets. Averages values within each bucket.
- Retention via bisect: finds the cutoff index and slices, O(log n) per series.
- Group-by queries merge matching series, then split by group key tag values.

## Plan Gaps

1. **`_bucketize` does a linear scan of all points per bucket.** Line 165: `[v for t, v in points if bucket_start <= t < bucket_end]` iterates all points for every bucket. Should use bisect on the sorted points to find bucket boundaries in O(log n) instead of O(n) per bucket.

2. **`_check_condition` uses `max(rule.duration_seconds, 60)` as lookback window.** This means a rule with `duration_seconds=0` still looks back 60 seconds. The window is used to collect data for evaluation, not for the duration gate. This conflates two concerns.

3. **Downsampling doesn't handle `max_age=float('inf')` cleanly.** `cutoff_start = current_time - float('inf')` is `-inf`, which works with the slice function but is semantically odd.

4. **`get_active_alerts` sets `triggered_at=0` for returned alerts.** It doesn't track when the alert actually fired, only the current value.

## Implementation Issues (1 test fix)

1. **`test_smoke.py` rate-of-change test failed.** Data points at timestamps 1000-1540 (step 60) were outside the 60-second lookback window when evaluating at 1600. Only one point was in range, giving rate=0%. **Fix:** Changed to two points (100 at t=1550, 500 at t=1600) within the window, eval at 1610. 10/10 pytest tests pass; smoke script passes.
