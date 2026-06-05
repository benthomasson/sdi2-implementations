"""Tests for Real-time Gaming Leaderboard."""

import sys
import time

sys.path.insert(0, "../implementer")
from leaderboard import Leaderboard, LeaderboardManager


def test_basic_ranking():
    """Example from problem: update scores and verify ranks."""
    lb = Leaderboard("weekly")
    lb.update_score("alice", 1500, timestamp=1.0)
    lb.update_score("bob", 2000, timestamp=2.0)
    lb.update_score("charlie", 1800, timestamp=3.0)

    assert lb.get_rank("bob") == 1
    assert lb.get_rank("charlie") == 2
    assert lb.get_rank("alice") == 3

    top = lb.top_k(2)
    assert top[0]["player_id"] == "bob"
    assert top[1]["player_id"] == "charlie"

    # Increment moves alice to #1
    lb.increment_score("alice", 700, timestamp=4.0)
    assert lb.get_rank("alice") == 1
    assert lb.get_score("alice") == 2200


def test_tie_breaking():
    """Equal scores ordered by earliest timestamp."""
    lb = Leaderboard("ties")
    lb.update_score("first", 1000, timestamp=1.0)
    lb.update_score("second", 1000, timestamp=2.0)
    lb.update_score("third", 1000, timestamp=3.0)

    assert lb.get_rank("first") == 1
    assert lb.get_rank("second") == 2
    assert lb.get_rank("third") == 3

    top = lb.top_k(3)
    assert [e["player_id"] for e in top] == ["first", "second", "third"]


def test_around_me():
    """Around-me returns correct neighbors."""
    lb = Leaderboard("around")
    for i in range(10):
        lb.update_score(f"p{i}", (i + 1) * 100, timestamp=float(i))

    around = lb.around_me("p5", count=2)
    pids = [e["player_id"] for e in around]
    assert len(around) == 5
    assert "p5" in pids
    # p5 has score 600, so p6(700) and p7(800) are above, p4(500) is below
    assert "p6" in pids
    assert "p4" in pids


def test_percentile():
    """Percentile calculation."""
    lb = Leaderboard("pct")
    for i in range(100):
        lb.update_score(f"p{i}", float(i), timestamp=float(i))

    assert lb.percentile("p99") == 99.0  # rank 1, best
    assert lb.percentile("p0") == 0.0    # rank 100, worst
    assert lb.percentile("nonexistent") is None


def test_range_query():
    """Range query returns correct players."""
    lb = Leaderboard("range")
    lb.update_score("a", 100, timestamp=1.0)
    lb.update_score("b", 200, timestamp=2.0)
    lb.update_score("c", 300, timestamp=3.0)
    lb.update_score("d", 400, timestamp=4.0)

    rng = lb.range_by_score(150, 350)
    pids = {e["player_id"] for e in rng}
    assert pids == {"b", "c"}


def test_remove_and_reset():
    """Remove player adjusts ranks; reset clears everything."""
    lb = Leaderboard("rm")
    lb.update_score("a", 100, timestamp=1.0)
    lb.update_score("b", 200, timestamp=2.0)
    lb.update_score("c", 300, timestamp=3.0)

    assert lb.remove_player("b") is True
    assert lb.get_rank("b") is None
    assert lb.get_rank("c") == 1
    assert lb.get_rank("a") == 2
    assert lb.size == 2
    assert lb.remove_player("nonexistent") is False

    lb.reset()
    assert lb.size == 0
    assert lb.get_rank("a") is None


def test_score_history():
    """Score history tracks changes."""
    lb = Leaderboard("hist")
    lb.update_score("a", 100, timestamp=1.0)
    lb.update_score("a", 200, timestamp=2.0)
    lb.update_score("a", 300, timestamp=3.0)

    hist = lb.get_history("a")
    assert len(hist) == 3
    assert hist[0]["score"] == 100
    assert hist[-1]["score"] == 300

    # Nonexistent player
    assert lb.get_history("zzz") == []


def test_multiple_leaderboards():
    """Multiple leaderboards are independent."""
    mgr = LeaderboardManager()
    daily = mgr.get_or_create("daily")
    weekly = mgr.get_or_create("weekly")

    daily.update_score("alice", 100, timestamp=1.0)
    weekly.update_score("alice", 500, timestamp=1.0)

    assert daily.get_score("alice") == 100
    assert weekly.get_score("alice") == 500
    assert set(mgr.list_leaderboards()) == {"daily", "weekly"}

    mgr.delete("daily")
    assert mgr.list_leaderboards() == ["weekly"]


def test_edge_cases():
    """Edge cases: empty leaderboard, single player, missing players."""
    lb = Leaderboard("edge")

    assert lb.top_k(5) == []
    assert lb.get_rank("nobody") is None
    assert lb.get_score("nobody") is None
    assert lb.around_me("nobody") == []

    # Single player percentile
    lb.update_score("solo", 100, timestamp=1.0)
    assert lb.percentile("solo") == 0.0
    assert lb.size == 1


def test_performance():
    """100K players: rank operations complete quickly."""
    lb = Leaderboard("perf")

    start = time.time()
    for i in range(100_000):
        lb.update_score(f"player_{i}", float(i), timestamp=float(i))
    insert_time = time.time() - start

    start = time.time()
    for _ in range(1000):
        lb.get_rank("player_50000")
    rank_time = time.time() - start

    assert rank_time < 1.0, f"1000 rank lookups took {rank_time:.2f}s"
    assert insert_time < 30.0, f"100K inserts took {insert_time:.2f}s"
    print(f"  Perf: insert={insert_time:.2f}s, 1000 ranks={rank_time:.2f}s")


if __name__ == "__main__":
    tests = [
        test_basic_ranking,
        test_tie_breaking,
        test_around_me,
        test_percentile,
        test_range_query,
        test_remove_and_reset,
        test_score_history,
        test_multiple_leaderboards,
        test_edge_cases,
        test_performance,
    ]

    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  PASS: {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL: {t.__name__}: {e}")

    print(f"\nResults: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
