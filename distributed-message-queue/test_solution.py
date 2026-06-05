"""Tests for Distributed Message Queue implementation."""
import pytest
from solution import Message, StoredMessage, MessageQueue


@pytest.fixture
def mq():
    return MessageQueue()


def test_key_based_partitioning(mq):
    """1. Messages with same key go to same partition; different keys may differ."""
    mq.create_topic("t", num_partitions=4)
    msgs = [mq.publish("t", Message(key="user:1", value=i)) for i in range(5)]
    # All same key -> same partition
    assert all(m.partition == msgs[0].partition for m in msgs)
    # Partition is valid
    assert msgs[0].partition in range(4)


def test_offset_increment(mq):
    """2. Offsets increment correctly within each partition."""
    mq.create_topic("t", num_partitions=1)
    m1 = mq.publish("t", Message(key="k", value="a"))
    m2 = mq.publish("t", Message(key="k", value="b"))
    m3 = mq.publish("t", Message(key="k", value="c"))
    assert m1.offset == 0
    assert m2.offset == 1
    assert m3.offset == 2


def test_consumer_group_balanced(mq):
    """3. Consumer group partitions are balanced across consumers."""
    mq.create_topic("t", num_partitions=6)
    mq.create_consumer_group("g", "t")
    mq.add_consumer("g", "c1")
    mq.add_consumer("g", "c2")
    assignments = mq.add_consumer("g", "c3")
    # 6 partitions / 3 consumers = 2 each
    assert len(assignments["c1"]) == 2
    assert len(assignments["c2"]) == 2
    assert len(assignments["c3"]) == 2
    # All partitions assigned
    all_parts = sorted(sum(assignments.values(), []))
    assert all_parts == [0, 1, 2, 3, 4, 5]


def test_rebalance_on_leave(mq):
    """4. Rebalancing when a consumer leaves."""
    mq.create_topic("t", num_partitions=3)
    mq.create_consumer_group("g", "t")
    mq.add_consumer("g", "c1")
    mq.add_consumer("g", "c2")
    mq.add_consumer("g", "c3")
    mq.remove_consumer("g", "c3")
    g = mq.consumer_groups["g"]
    total = sum(len(v) for v in g.assignments.values())
    assert total == 3
    assert "c3" not in g.assignments


def test_commit_and_seek(mq):
    """5. Commit and seek work correctly."""
    mq.create_topic("t", num_partitions=1)
    mq.publish("t", Message(key="k", value="v1"))
    mq.publish("t", Message(key="k", value="v2"))
    mq.create_consumer_group("g", "t")
    mq.add_consumer("g", "c1")
    msgs = mq.poll("g", "c1")
    assert len(msgs) == 2
    mq.commit("g", "c1")
    # After commit, no new messages
    assert mq.poll("g", "c1") == []
    # Seek back to beginning
    mq.seek("g", 0, -1)
    msgs2 = mq.poll("g", "c1")
    assert len(msgs2) == 2


def test_independent_consumer_groups(mq):
    """6. Multiple consumer groups consume independently."""
    mq.create_topic("t", num_partitions=1)
    mq.publish("t", Message(key="k", value="v"))
    mq.create_consumer_group("g1", "t")
    mq.create_consumer_group("g2", "t")
    mq.add_consumer("g1", "c1")
    mq.add_consumer("g2", "c2")
    m1 = mq.poll("g1", "c1")
    m2 = mq.poll("g2", "c2")
    assert len(m1) == 1 and len(m2) == 1


def test_retention(mq):
    """7. Message retention removes old messages."""
    mq.create_topic("t", num_partitions=1, retention_count=5)
    for i in range(10):
        mq.publish("t", Message(key="k", value=i))
    info = mq.get_topic_info("t")
    assert info["partitions"][0]["message_count"] == 5
    assert info["partitions"][0]["base_offset"] == 5


def test_dead_letter_queue(mq):
    """8. Dead letter queue receives failed messages."""
    mq.create_topic("t", num_partitions=1)
    msg = mq.publish("t", Message(key="k", value="bad"))
    mq.create_consumer_group("g", "t")
    mq.add_consumer("g", "c1")
    for _ in range(3):
        mq.acknowledge("g", msg, success=False, max_failures=3)
    assert "__dlq_t" in mq.topics
    dlq_info = mq.get_topic_info("__dlq_t")
    assert dlq_info["partitions"][0]["message_count"] == 1


def test_at_least_once_redelivery(mq):
    """9. At-least-once: uncommitted messages re-delivered on seek back."""
    mq.create_topic("t", num_partitions=1)
    mq.publish("t", Message(key="k", value="v"))
    mq.create_consumer_group("g", "t", delivery="at_least_once")
    mq.add_consumer("g", "c1")
    msgs = mq.poll("g", "c1")
    assert len(msgs) == 1
    # Don't commit — seek back
    mq.seek("g", 0, 0)
    msgs2 = mq.poll("g", "c1")
    assert len(msgs2) == 1


def test_exactly_once_dedup(mq):
    """10. Exactly-once deduplicates by message ID."""
    mq.create_topic("t", num_partitions=1)
    mq.publish("t", Message(key="k", value="v"))
    mq.create_consumer_group("g", "t", delivery="exactly_once")
    mq.add_consumer("g", "c1")
    msgs1 = mq.poll("g", "c1")
    assert len(msgs1) == 1
    # Seek back — should not get same message again
    mq.seek("g", 0, 0)
    msgs2 = mq.poll("g", "c1")
    assert len(msgs2) == 0


def test_round_robin_no_key(mq):
    """11. Round-robin assignment when no key provided."""
    mq.create_topic("t", num_partitions=3)
    partitions = set()
    for _ in range(3):
        m = mq.publish("t", Message(key=None, value="x"))
        partitions.add(m.partition)
    assert len(partitions) == 3  # Each went to a different partition


def test_consumer_lag(mq):
    """12. Consumer lag is accurately reported."""
    mq.create_topic("t", num_partitions=1)
    for i in range(5):
        mq.publish("t", Message(key="k", value=i))
    mq.create_consumer_group("g", "t")
    mq.add_consumer("g", "c1")
    lag = mq.get_consumer_lag("g")
    assert lag[0] == 5
    mq.poll("g", "c1")
    mq.commit("g", "c1")
    lag2 = mq.get_consumer_lag("g")
    assert lag2[0] == 0
