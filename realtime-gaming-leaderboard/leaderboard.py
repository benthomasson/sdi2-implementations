"""Real-time Gaming Leaderboard using sorted containers."""

import time
from collections import defaultdict, deque
from sortedcontainers import SortedList


class Leaderboard:
    """A real-time leaderboard with O(log N) rank operations."""

    def __init__(self, name: str = "default", history_size: int = 10):
        self.name = name
        self._history_size = history_size
        # SortedList of (-score, timestamp, player_id) for descending score order
        self._entries = SortedList()
        # player_id -> (score, timestamp)
        self._players = {}
        # player_id -> deque of {score, timestamp}
        self._history = defaultdict(lambda: deque(maxlen=self._history_size))

    def update_score(self, player_id: str, score: float, timestamp: float = None) -> dict:
        """Set a player's score. Returns {rank, previous_score, new_score}."""
        if timestamp is None:
            timestamp = time.time()
        previous_score = None
        if player_id in self._players:
            old_score, old_ts = self._players[player_id]
            previous_score = old_score
            self._entries.remove((-old_score, old_ts, player_id))
        entry = (-score, timestamp, player_id)
        self._entries.add(entry)
        self._players[player_id] = (score, timestamp)
        self._history[player_id].append({"score": score, "timestamp": timestamp})
        rank = self._entries.index(entry) + 1
        return {"rank": rank, "previous_score": previous_score, "new_score": score}

    def increment_score(self, player_id: str, delta: float, timestamp: float = None) -> dict:
        """Increment a player's score. Returns {rank, new_score}."""
        current = self._players.get(player_id)
        old_score = current[0] if current else 0.0
        result = self.update_score(player_id, old_score + delta, timestamp)
        return {"rank": result["rank"], "new_score": result["new_score"]}

    def get_rank(self, player_id: str) -> int | None:
        """Get 1-based rank. Returns None if player not found."""
        if player_id not in self._players:
            return None
        score, ts = self._players[player_id]
        return self._entries.index((-score, ts, player_id)) + 1

    def get_score(self, player_id: str) -> float | None:
        """Get current score."""
        if player_id not in self._players:
            return None
        return self._players[player_id][0]

    def _entry_to_dict(self, idx, entry):
        """Convert an internal entry to a result dict."""
        return {"rank": idx + 1, "player_id": entry[2], "score": -entry[0]}

    def top_k(self, k: int = 10) -> list[dict]:
        """Get top K players: [{rank, player_id, score}]."""
        return [self._entry_to_dict(i, e) for i, e in enumerate(self._entries[:k])]

    def bottom_k(self, k: int = 10) -> list[dict]:
        """Get bottom K players."""
        total = len(self._entries)
        start = max(0, total - k)
        return [self._entry_to_dict(start + i, e)
                for i, e in enumerate(self._entries[start:])]

    def around_me(self, player_id: str, count: int = 5) -> list[dict]:
        """Get count players above and below the given player."""
        if player_id not in self._players:
            return []
        score, ts = self._players[player_id]
        idx = self._entries.index((-score, ts, player_id))
        start = max(0, idx - count)
        end = min(len(self._entries), idx + count + 1)
        return [self._entry_to_dict(start + i, e)
                for i, e in enumerate(self._entries[start:end])]

    def range_by_score(self, min_score: float, max_score: float) -> list[dict]:
        """Get all players with scores in [min, max], descending."""
        # Negated scores: -max_score <= -score <= -min_score
        # irange with inclusive bounds on the negated values
        results = []
        for entry in self._entries.irange((-max_score,), (-min_score, float('inf'), '')):
            neg_score, ts, pid = entry
            idx = self._entries.index(entry)
            results.append(self._entry_to_dict(idx, entry))
        return results

    def percentile(self, player_id: str) -> float | None:
        """Get percentile (0-100). 95th percentile means better than 95%."""
        if player_id not in self._players:
            return None
        total = len(self._entries)
        if total <= 1:
            return 0.0
        rank = self.get_rank(player_id)
        # Players beaten = total - rank
        return (total - rank) / total * 100

    def get_history(self, player_id: str, limit: int = 10) -> list[dict]:
        """Get recent score changes: [{score, timestamp}]."""
        history = self._history.get(player_id, [])
        return list(history)[-limit:]

    def remove_player(self, player_id: str) -> bool:
        """Remove a player from the leaderboard."""
        if player_id not in self._players:
            return False
        score, ts = self._players.pop(player_id)
        self._entries.remove((-score, ts, player_id))
        if player_id in self._history:
            del self._history[player_id]
        return True

    def reset(self) -> None:
        """Clear all scores."""
        self._entries.clear()
        self._players.clear()
        self._history.clear()

    @property
    def size(self) -> int:
        """Number of players."""
        return len(self._players)


class LeaderboardManager:
    """Manage multiple named leaderboards."""

    def __init__(self):
        self._boards = {}

    def get_or_create(self, name: str) -> Leaderboard:
        """Get or create a named leaderboard."""
        if name not in self._boards:
            self._boards[name] = Leaderboard(name)
        return self._boards[name]

    def delete(self, name: str) -> None:
        """Delete a leaderboard."""
        self._boards.pop(name, None)

    def list_leaderboards(self) -> list[str]:
        """List all leaderboard names."""
        return list(self._boards.keys())


# === Tests ===
if __name__ == "__main__":
    import sys

    passed = 0
    failed = 0

    def check(name, condition):
        global passed, failed
        if condition:
            passed += 1
            print(f"  PASS: {name}")
        else:
            failed += 1
            print(f"  FAIL: {name}")

    # 1. Update score and verify rank
    print("Test 1: Update score and verify rank")
    lb = Leaderboard("test1")
    lb.update_score("alice", 1500, timestamp=1.0)
    lb.update_score("bob", 2000, timestamp=2.0)
    lb.update_score("charlie", 1800, timestamp=3.0)
    check("bob is rank 1", lb.get_rank("bob") == 1)
    check("charlie is rank 2", lb.get_rank("charlie") == 2)
    check("alice is rank 3", lb.get_rank("alice") == 3)

    # 2. Top-K returns correct ordering
    print("Test 2: Top-K ordering")
    top = lb.top_k(2)
    check("top[0] is bob", top[0]["player_id"] == "bob")
    check("top[1] is charlie", top[1]["player_id"] == "charlie")
    check("top has 2 entries", len(top) == 2)

    # 3. Rank lookup is accurate after updates
    print("Test 3: Rank after updates")
    lb.update_score("alice", 2500, timestamp=4.0)
    check("alice now rank 1", lb.get_rank("alice") == 1)
    check("bob now rank 2", lb.get_rank("bob") == 2)

    # 4. Increment score changes rank
    print("Test 4: Increment score")
    lb2 = Leaderboard("test4")
    lb2.update_score("a", 100, timestamp=1.0)
    lb2.update_score("b", 200, timestamp=2.0)
    result = lb2.increment_score("a", 150, timestamp=3.0)
    check("a score is 250", result["new_score"] == 250)
    check("a is rank 1", result["rank"] == 1)

    # 5. Tie-breaking: equal scores ordered by earlier timestamp
    print("Test 5: Tie-breaking")
    lb3 = Leaderboard("test5")
    lb3.update_score("first", 1000, timestamp=1.0)
    lb3.update_score("second", 1000, timestamp=2.0)
    lb3.update_score("third", 1000, timestamp=3.0)
    check("first is rank 1", lb3.get_rank("first") == 1)
    check("second is rank 2", lb3.get_rank("second") == 2)
    check("third is rank 3", lb3.get_rank("third") == 3)

    # 6. Around-me returns correct neighbors
    print("Test 6: Around-me")
    lb4 = Leaderboard("test6")
    for i in range(10):
        lb4.update_score(f"p{i}", (i + 1) * 100, timestamp=float(i))
    around = lb4.around_me("p5", count=2)
    pids = [e["player_id"] for e in around]
    check("around p5 has 5 entries", len(around) == 5)
    check("p5 in results", "p5" in pids)
    check("p6 above p5", "p6" in pids)
    check("p7 above p5", "p7" in pids)
    check("p4 below p5", "p4" in pids)

    # 7. Percentile calculation
    print("Test 7: Percentile")
    lb5 = Leaderboard("test7")
    for i in range(100):
        lb5.update_score(f"p{i}", float(i), timestamp=float(i))
    pct = lb5.percentile("p99")  # rank 1, best
    check("top player ~99th percentile", pct == 99.0)
    pct_low = lb5.percentile("p0")  # rank 100, worst
    check("bottom player 0th percentile", pct_low == 0.0)

    # 8. Range query
    print("Test 8: Range query")
    lb6 = Leaderboard("test8")
    lb6.update_score("a", 100, timestamp=1.0)
    lb6.update_score("b", 200, timestamp=2.0)
    lb6.update_score("c", 300, timestamp=3.0)
    lb6.update_score("d", 400, timestamp=4.0)
    rng = lb6.range_by_score(150, 350)
    pids = [e["player_id"] for e in rng]
    check("range has b and c", set(pids) == {"b", "c"})

    # 9. Remove player adjusts ranks
    print("Test 9: Remove player")
    lb7 = Leaderboard("test9")
    lb7.update_score("a", 100, timestamp=1.0)
    lb7.update_score("b", 200, timestamp=2.0)
    lb7.update_score("c", 300, timestamp=3.0)
    lb7.remove_player("b")
    check("b removed", lb7.get_rank("b") is None)
    check("a is rank 2", lb7.get_rank("a") == 2)
    check("c is rank 1", lb7.get_rank("c") == 1)
    check("size is 2", lb7.size == 2)

    # 10. Reset clears everything
    print("Test 10: Reset")
    lb8 = Leaderboard("test10")
    lb8.update_score("a", 100, timestamp=1.0)
    lb8.reset()
    check("size is 0 after reset", lb8.size == 0)
    check("player not found after reset", lb8.get_rank("a") is None)

    # 11. Score history tracks changes
    print("Test 11: Score history")
    lb9 = Leaderboard("test11")
    lb9.update_score("a", 100, timestamp=1.0)
    lb9.update_score("a", 200, timestamp=2.0)
    lb9.update_score("a", 300, timestamp=3.0)
    hist = lb9.get_history("a")
    check("3 history entries", len(hist) == 3)
    check("latest score is 300", hist[-1]["score"] == 300)
    check("first score is 100", hist[0]["score"] == 100)

    # 12. Large dataset performance
    print("Test 12: Performance (100K players)")
    lb10 = Leaderboard("perf")
    import time as _time
    start = _time.time()
    for i in range(100_000):
        lb10.update_score(f"player_{i}", float(i), timestamp=float(i))
    insert_time = _time.time() - start
    print(f"  Insert 100K: {insert_time:.2f}s")

    start = _time.time()
    for _ in range(1000):
        lb10.get_rank("player_50000")
    rank_time = _time.time() - start
    print(f"  1000 rank lookups: {rank_time:.2f}s")

    start = _time.time()
    lb10.top_k(100)
    top_time = _time.time() - start
    print(f"  Top-100: {top_time:.4f}s")

    check("rank operations under 1s", rank_time < 1.0)
    check("insert 100K under 30s", insert_time < 30.0)

    # 13. Multiple leaderboards are independent
    print("Test 13: Multiple leaderboards")
    mgr = LeaderboardManager()
    daily = mgr.get_or_create("daily")
    weekly = mgr.get_or_create("weekly")
    daily.update_score("alice", 100, timestamp=1.0)
    weekly.update_score("alice", 500, timestamp=1.0)
    check("daily score is 100", daily.get_score("alice") == 100)
    check("weekly score is 500", weekly.get_score("alice") == 500)
    check("2 leaderboards", len(mgr.list_leaderboards()) == 2)
    mgr.delete("daily")
    check("1 leaderboard after delete", len(mgr.list_leaderboards()) == 1)

    # Bottom-K test
    print("Test 14: Bottom-K")
    lb11 = Leaderboard("bottom")
    lb11.update_score("a", 100, timestamp=1.0)
    lb11.update_score("b", 200, timestamp=2.0)
    lb11.update_score("c", 300, timestamp=3.0)
    bottom = lb11.bottom_k(2)
    check("bottom[0] is b (rank 2)", bottom[0]["player_id"] == "b")
    check("bottom[1] is a (rank 3)", bottom[1]["player_id"] == "a")

    # Score lookup
    print("Test 15: Score lookup")
    check("get_score works", lb11.get_score("b") == 200)
    check("get_score None for missing", lb11.get_score("zzz") is None)

    print(f"\nResults: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
