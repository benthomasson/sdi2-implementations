# Plan Review: Real-time Gaming Leaderboard

## Plan Strengths

- `SortedList` with `(-score, timestamp, player_id)` tuples: single trick handles descending sort and tie-breaking (earlier timestamp wins) simultaneously. O(log N) insert, remove, and rank lookup.
- Side dict `_players: {player_id: (score, timestamp)}` for O(1) score lookup and O(log N) rank via `_entries.index()`.
- `increment_score` delegates to `update_score` with `old_score + delta`, correctly handling the case where the player doesn't exist yet (defaults to 0.0).
- Score history via per-player `deque(maxlen=history_size)` — bounded memory, no manual truncation needed.
- `range_by_score` uses `SortedList.irange()` with negated bounds for efficient range queries on the sorted structure.
- `around_me` computes `idx - count` to `idx + count + 1` with boundary clamping.
- `LeaderboardManager` provides named leaderboard isolation with get-or-create semantics.
- `remove_player` cleans up both `_entries`, `_players`, and `_history`.

## Plan Gaps

1. **`range_by_score` calls `self._entries.index(entry)` per result.** Line 90: inside the loop over `irange` results, each `index()` is O(log N). For a range returning k results, this is O(k log N). The rank could be computed incrementally from the start index of the irange.

2. **`time.time()` fallback for timestamps.** Multiple rapid `update_score` calls without explicit timestamps could get identical `time.time()` values, making tie-breaking nondeterministic. All tests pass explicit timestamps, avoiding this in practice.

3. **`percentile` returns 0.0 for a single-player leaderboard.** Line 99: `if total <= 1: return 0.0`. This is a design choice — the sole player beats 0% of other players — but could also be argued as 100th percentile (better than nobody, but also the best).

4. **`defaultdict` with lambda captures `self._history_size` at closure time.** Line 19: `defaultdict(lambda: deque(maxlen=self._history_size))`. If `_history_size` were changed after construction, new deques would use the new value while existing ones retain the old. Not a practical issue since `_history_size` is never mutated.

5. **`bottom_k` returns ranks from the bottom of the sorted list.** The bottom 2 of a 3-player leaderboard returns rank 2 and rank 3 (not rank 3 and rank 2). This is ascending rank order within the bottom slice, which is consistent but arguably the "bottom K" could be ordered worst-first.

## Implementation Issues (0 test failures)

No test failures. Clean implementation at 151 lines (leaderboard) + 197 lines (tests). 10/10 tests pass including 100K player performance test (insert + rank lookups well under time limits).
