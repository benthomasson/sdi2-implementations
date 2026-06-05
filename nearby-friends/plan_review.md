# Plan Review: Nearby Friends

## Plan Strengths

- Grid-based spatial index: cell size scaled to distance threshold (`threshold_km / 111.0` degrees). 9-cell neighborhood search covers all possible nearby users.
- Grid index maintained incrementally on location update: old cell cleared, new cell populated. O(1) update.
- Haversine formula for great-circle distance calculation.
- Bidirectional friendship via dual set insertions. `remove_friendship` uses `discard` (no error on missing).
- Location TTL checked on both the querying user and each friend candidate.
- Location sharing toggle: disabled users excluded from both query results and notifications.
- Results sorted by distance (ascending).
- Location history capped at 100 entries via `deque(maxlen=100)`.
- Pub/sub notifications: `update_location` checks all friends, calls subscriber callback with `(user_id, distance)` for nearby ones.

## Plan Gaps

1. **`time.time()` fallback in `update_location` and `get_nearby_friends`.** Same pattern as other implementations — works but prevents deterministic testing without explicit timestamps.

2. **Grid cell size doesn't account for latitude compression.** At the equator, 1 degree longitude ~ 111 km. At 60N latitude, 1 degree longitude ~ 55 km. The cell size `threshold_km / 111.0` is calibrated for the equator — at higher latitudes, cells are wider than needed in the longitude dimension, which is conservative (won't miss nearby users) but could include more false positives.

3. **`get_nearby_friends` checks user's own location freshness.** If the querying user's location is stale, returns empty. This is correct — you can't find nearby friends if you don't know where you are.

4. **No deduplication in notification.** If a user moves from cell A to cell B and a friend is in both neighbor sets, the friend would be notified once (since `update_location` iterates the friend list, not the grid). Correct by design.

## Implementation Issues (0 test failures)

No test failures. Clean implementation at 176 lines. 20/20 tests pass across two test files.
