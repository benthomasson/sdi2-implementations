# Plan Review: Ad Click Event Aggregation

## Plan Strengths

- Tumbling windows correctly computed via `floor(timestamp / window_size) * window_size`. Clean O(1) window assignment.
- Deduplication via `seen_events` dict keyed by `event_id`. Pruned on watermark advance (cutoff at 2x allowed lateness).
- Window lifecycle (OPEN -> CLOSED -> FINALIZED) driven by watermark: `end <= watermark` triggers CLOSED, `end <= watermark - allowed_lateness` triggers FINALIZED.
- Late events accepted into CLOSED windows, rejected from FINALIZED. The transition from CLOSED to FINALIZED on late event arrival (line 90-93) is a nice lazy-finalization optimization.
- `query_top_ads` aggregates across all ads and windows in range, sorts descending, returns top-k. Correct.
- Batch processing correctly tracks per-batch stats by diffing global stats before/after each event.

## Plan Gaps

1. **No sliding window support.** The plan mentions sliding windows (requirement 3) but the implementation only has tumbling windows. This is acceptable for the scope — sliding windows would add significant complexity with overlapping window management.

2. **No multi-dimension aggregation.** Requirement 6 asks for grouping by campaign_id/country in addition to ad_id. The metadata field is accepted but never used for aggregation.

3. **No MapReduce-style extensibility.** Requirement 8 mentions map/reduce phases. The current design is a single-stage aggregator — fine for the core use case.

4. **Dedup set grows unbounded between watermark advances.** If `advance_watermark` is never called, `seen_events` accumulates indefinitely. In practice watermark is advanced regularly, but there's no time-based eviction without it.

5. **`_get_or_create_window` creates windows for rejected events.** When a late event arrives for a FINALIZED window, the window already exists. But if an event arrives for a *new* window that would immediately be finalized (timestamp far in the past), a new window is created, then immediately finalized on the next watermark advance. Wasted allocation, but not a correctness bug.

## Implementation Issues (0 test failures)

No test failures. The implementation is clean at 174 lines with correct behavior across all 10 test cases.
