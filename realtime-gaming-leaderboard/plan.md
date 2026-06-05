# Plan (Iteration 1)

Task: Real-time Gaming Leaderboard
==============================
SDI Vol 2 Reference: Chapter 10 - Real-time Gaming Leaderboard

Overview
--------
Build a real-time leaderboard system that supports score updates, top-K
queries, rank lookups, and percentile calculations. The core data structure
is a sorted set (implemented as a skip list or balanced BST) that maintains
scores in sorted order with O(log N) updates and rank queries. Used in
competitive games, fitness apps, and contest platforms.

Requirements
------------
1. Score updates: set or increment a player's score. If the player doesn't
   exist, create them.
2. Top-K: retrieve the top K players sorted by score (descending), with
   rank numbers.
3. Rank lookup: given a player ID, return their current rank (1-based).
4. Score lookup: given a player ID, return their current score.
5. Range query: get all players with scores between min and max.
6. Percentile: given a player ID, return their percentile (% of players
   they score higher than).
7. Around-me: given a player ID, return N players above and below them.
8. Leaderboard reset: clear all scores.
9. Multiple leaderboards: support named leaderboards (daily, weekly, etc.).
10. Score history: track the last N score changes per player with timestamps.
11. Tie-breaking: players with equal scores are ordered by who achieved
    the score first (earlier timestamp ranks higher).

Interface
---------
class Leaderboard:
    def __init__(self, name: str = "default"):
        """Create a named leaderboard."""

    def update_score(self, player_id: str, score: float,
                     timestamp: float = None) -> dict:
        """Set a player's score. Returns {rank, previous_score, new_score}."""

    def increment_score(self, player_id: str, delta: float,
                        timestamp: float = None) -> dict:
        """Increment a player's score. Returns {rank, new_score}."""

    def get_rank(self, player_id: str) -> int | None:
        """Get 1-based rank. Returns None if player not found."""

    def get_score(self, player_id: str) -> float | None:
        """Get current score."""

    def top_k(self, k: int = 10) -> list[dict]:
        """Get top K players: [{rank, player_id, score}]."""

    def bottom_k(self, k: int = 10) -> list[dict]:
        """Get bottom K players."""

    def around_me(self, player_id: str, count: int = 5) -> list[dict]:
        """Get count players above and below the given player."""

    def range_by_score(self, min_score: float,
                       max_score: float) -> list[dict]:
        """Get all players with scores in [min, max]."""

    def percentile(self, player_id: str) -> float | None:
        """Get percentile (0-100). 95th percentile means better than 95%."""

    def get_history(self, player_id: str, limit: int = 10) -> list[dict]:
        """Get recent score changes: [{score, timestamp}]."""

    def remove_player(self, player_id: str) -> bool:
        """Remove a player from the leaderboard."""

    def reset(self) -> None:
        """Clear all scores."""

    @property
    def size(self) -> int:
        """Number of players."""

class LeaderboardManager:
    def __init__(self):
        """Manage multiple named leaderboards."""

    def get_or_create(self, name: str) -> Leaderboard:
        """Get or create a named leaderboard."""

    def delete(self, name: str) -> None:
        """Delete a leaderboard."""

    def list_leaderboards(self) -> list[str]:
        """List all leaderboard names."""

Example Usage
-------------
    lb = Leaderboard("weekly")

    lb.update_score("alice", 1500)
    lb.update_score("bob", 2000)
    lb.update_score("charlie", 1800)

    assert lb.get_rank("bob") == 1
    assert lb.get_rank("charlie") == 2
    assert lb.get_rank("alice") == 3

    top = lb.top_k(2)
    assert top[0]["player_id"] == "bob"
    assert top[1]["player_id"] == "charlie"

    lb.increment_score("alice", 700)  # alice now 2200
    assert lb.get_rank("alice") == 1

    around = lb.around_me("charlie", count=1)
    # Returns alice (above) and bob (below) relative to charlie

    pct = lb.percentile("bob")
    # bob is rank 2 of 3, better than 1/3 = ~33rd percentile

Constraints
-----------
- Scores are floating point numbers.
- Player IDs are unique strings.
- Rank queries must be O(log N) or better.
- Handle up to 1,000,000 players.
- Tie-breaking by earliest timestamp.
- Target: 200-350 lines of Python.

Testing Requirements
--------------------
1. Update score and verify rank.
2. Top-K returns correct ordering.
3. Rank lookup is accurate after updates.
4. Increment score changes rank correctly.
5. Tie-breaking: equal scores ordered by time.
6. Around-me returns correct neighbors.
7. Percentile calculation is accurate.
8. Range query returns correct players.
9. Remove player adjusts ranks.
10. Reset clears everything.
11. Score history tracks changes.
12. Large dataset (100K players) performs well.
13. Multiple leaderboards are independent.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `PLAN.md`. 

**Summary:** Use `sortedcontainers.SortedList` with `(-score, timestamp, player_id)` tuples — this single trick handles descending sort order and tie-breaking simultaneously, giving O(log N) for all rank operations. A side `dict` maps player IDs to current state, and per-player `deque`s track score history. The whole thing should fit comfortably in ~250 lines plus tests.

[Committed changes to planner branch]