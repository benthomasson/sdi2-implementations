# Plan (Iteration 1)

Task: Distributed Message Queue
==========================
SDI Vol 2 Reference: Chapter 4 - Distributed Message Queue

Overview
--------
Build a message queue system similar to Apache Kafka. Messages are organized
into topics, each topic has multiple partitions, and consumer groups coordinate
to process messages. The system supports configurable delivery semantics,
offset tracking, message retention, and dead letter queues.

Requirements
------------
1. Topics: named message channels. Create and delete topics.
2. Partitions: each topic has configurable partitions. Messages are assigned
   to partitions by key hash (or round-robin if no key).
3. Producers: publish messages with optional key and headers.
4. Messages: contain key (optional), value, timestamp, headers, partition,
   offset within partition.
5. Consumer groups: multiple consumers in a group share partitions. Each
   partition is assigned to exactly one consumer in a group. Different
   groups consume independently.
6. Offset tracking: each consumer group tracks its offset per partition.
   Support commit (manual and auto), seek to offset, seek to beginning/end.
7. Delivery semantics:
   - At-most-once: commit before processing.
   - At-least-once: commit after processing (default).
   - Exactly-once: deduplication by message ID.
8. Dead letter queue: messages that fail processing N times are moved to
   a DLQ topic.
9. Message retention: configurable per topic (by count or age). Old
   messages are removed.
10. Consumer rebalancing: when consumers join/leave a group, partitions
    are reassigned.

Interface
---------
class Message:
    def __init__(self, key: str | None, value: any, headers: dict = None):
        """A message to be published."""

class StoredMessage:
    def __init__(self, key: str | None, value: any, topic: str,
                 partition: int, offset: int, timestamp: float,
                 headers: dict = None, message_id: str = None):
        """A message stored in a partition."""

class MessageQueue:
    def __init__(self):
        """Initialize the message queue system."""

    def create_topic(self, name: str, num_partitions: int = 3,
                     retention_count: int = 10000) -> None:
        """Create a topic with the given number of partitions."""

    def delete_topic(self, name: str) -> None:
        """Delete a topic and all its data."""

    def publish(self, topic: str, message: Message) -> StoredMessage:
        """Publish a message to a topic. Returns the stored message
        with partition and offset assigned."""

    def create_consumer_group(self, group_id: str, topic: str,
                              delivery: str = "at_least_once") -> None:
        """Create a consumer group for a topic."""

    def add_consumer(self, group_id: str, consumer_id: str) -> dict:
        """Add a consumer to a group. Returns partition assignments."""

    def remove_consumer(self, group_id: str, consumer_id: str) -> None:
        """Remove a consumer and rebalance."""

    def poll(self, group_id: str, consumer_id: str,
             max_messages: int = 10) -> list[StoredMessage]:
        """Fetch messages for a consumer from its assigned partitions."""

    def commit(self, group_id: str, consumer_id: str) -> None:
        """Commit the current offset for the consumer."""

    def seek(self, group_id: str, partition: int, offset: int) -> None:
        """Seek to a specific offset in a partition."""

    def get_topic_info(self, topic: str) -> dict:
        """Return topic metadata: partitions, message counts, etc."""

    def get_consumer_lag(self, group_id: str) -> dict:
        """Return lag per partition for a consumer group."""

Example Usage
-------------
    mq = MessageQueue()
    mq.create_topic("orders", num_partitions=3)

    # Publish
    msg = mq.publish("orders", Message(key="user:1", value={"item": "book", "qty": 2}))
    assert msg.partition in [0, 1, 2]
    assert msg.offset == 0

    # Same key always goes to same partition
    msg2 = mq.publish("orders", Message(key="user:1", value={"item": "pen", "qty": 1}))
    assert msg2.partition == msg.partition

    # Consumer group
    mq.create_consumer_group("order-processors", "orders")
    mq.add_consumer("order-processors", "worker-1")
    mq.add_consumer("order-processors", "worker-2")

    messages = mq.poll("order-processors", "worker-1", max_messages=10)
    mq.commit("order-processors", "worker-1")

    # Consumer lag
    lag = mq.get_consumer_lag("order-processors")

Constraints
-----------
- All in-memory, no disk persistence required.
- Partition assignment uses round-robin rebalancing.
- Message ordering guaranteed within a partition.
- Same key always maps to same partition (consistent hashing).
- Handle up to 100,000 messages per topic.
- Target: 250-450 lines of Python.

Testing Requirements
--------------------
1. Messages are assigned to correct partition by key.
2. Offsets increment correctly within each partition.
3. Consumer group partitions are balanced.
4. Rebalancing on consumer join/leave.
5. Commit and seek work correctly.
6. Multiple consumer groups consume independently.
7. Message retention removes old messages.
8. Dead letter queue receives failed messages.
9. At-least-once: uncommitted messages are re-delivered.
10. Exactly-once: duplicate messages are deduplicated.
11. Round-robin assignment when no key provided.
12. Consumer lag is accurately reported.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `PLAN.md`. The design is straightforward — the spec essentially defines the full interface, so the main decisions are:

- **Partition routing**: key hash mod N, with round-robin fallback
- **Offset model**: dual current/committed offsets per group per partition, with `base_offset` to handle retention trimming
- **Delivery semantics**: at-most-once via pre-commit, at-least-once via post-commit, exactly-once via message ID dedup set
- **DLQ**: failure counter per message, overflow to a synthetic `__dlq_{topic}` topic
- **Rebalancing**: simple round-robin partition distribution on consumer join/leave

Confidence is **HIGH** — no ambiguity in the spec, clean bounded problem.

[Committed changes to planner branch]