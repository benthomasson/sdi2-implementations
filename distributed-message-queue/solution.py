"""Distributed Message Queue — in-memory Kafka-like message queue."""

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class Message:
    """A message to be published."""
    key: str | None
    value: object
    headers: dict = None


@dataclass
class StoredMessage:
    """A message stored in a partition."""
    key: str | None
    value: object
    topic: str
    partition: int
    offset: int
    timestamp: float
    headers: dict = None
    message_id: str = None


class Partition:
    """A single partition within a topic."""
    def __init__(self):
        self.messages: list[StoredMessage] = []
        self.base_offset: int = 0  # logical offset of first message after trimming

    @property
    def next_offset(self):
        return self.base_offset + len(self.messages)

    def append(self, msg: StoredMessage):
        self.messages.append(msg)

    def get(self, offset: int, count: int) -> list[StoredMessage]:
        start = offset - self.base_offset
        if start < 0:
            start = 0
        end = start + count
        return self.messages[start:end]

    def trim(self, retention_count: int):
        if len(self.messages) > retention_count:
            excess = len(self.messages) - retention_count
            self.messages = self.messages[excess:]
            self.base_offset += excess


class ConsumerGroup:
    """Tracks consumers, partition assignments, and offsets for a group."""
    def __init__(self, group_id: str, topic: str, num_partitions: int,
                 delivery: str = "at_least_once"):
        self.group_id = group_id
        self.topic = topic
        self.num_partitions = num_partitions
        self.delivery = delivery
        self.consumers: list[str] = []
        self.assignments: dict[str, list[int]] = {}  # consumer_id -> [partition_ids]
        self.committed_offset: dict[int, int] = {p: 0 for p in range(num_partitions)}
        self.current_offset: dict[int, int] = {p: 0 for p in range(num_partitions)}
        self.seen_message_ids: set[str] = set()  # for exactly-once
        self.failure_counts: dict[str, int] = defaultdict(int)  # message_id -> count

    def rebalance(self):
        self.assignments = {}
        if not self.consumers:
            return {}
        for c in self.consumers:
            self.assignments[c] = []
        for p in range(self.num_partitions):
            consumer = self.consumers[p % len(self.consumers)]
            self.assignments[consumer].append(p)
        return dict(self.assignments)

    def add_consumer(self, consumer_id: str) -> dict:
        if consumer_id not in self.consumers:
            self.consumers.append(consumer_id)
        return self.rebalance()

    def remove_consumer(self, consumer_id: str):
        if consumer_id in self.consumers:
            self.consumers.remove(consumer_id)
        self.rebalance()


class MessageQueue:
    """In-memory distributed message queue."""
    def __init__(self):
        self.topics: dict[str, list[Partition]] = {}
        self.topic_config: dict[str, dict] = {}
        self.consumer_groups: dict[str, ConsumerGroup] = {}
        self._rr_counters: dict[str, int] = {}  # round-robin counters per topic

    def create_topic(self, name: str, num_partitions: int = 3,
                     retention_count: int = 10000) -> None:
        """Create a topic with the given number of partitions."""
        if name in self.topics:
            raise ValueError(f"Topic '{name}' already exists")
        self.topics[name] = [Partition() for _ in range(num_partitions)]
        self.topic_config[name] = {
            "num_partitions": num_partitions,
            "retention_count": retention_count,
        }
        self._rr_counters[name] = 0

    def delete_topic(self, name: str) -> None:
        """Delete a topic and all its data."""
        if name not in self.topics:
            raise ValueError(f"Topic '{name}' does not exist")
        del self.topics[name]
        del self.topic_config[name]
        del self._rr_counters[name]
        to_remove = [gid for gid, g in self.consumer_groups.items() if g.topic == name]
        for gid in to_remove:
            del self.consumer_groups[gid]

    def publish(self, topic: str, message: Message) -> StoredMessage:
        """Publish a message to a topic."""
        if topic not in self.topics:
            raise ValueError(f"Topic '{topic}' does not exist")
        partitions = self.topics[topic]
        num_p = len(partitions)
        if message.key is not None:
            p_idx = hash(message.key) % num_p
        else:
            p_idx = self._rr_counters[topic] % num_p
            self._rr_counters[topic] += 1

        partition = partitions[p_idx]
        stored = StoredMessage(
            key=message.key,
            value=message.value,
            topic=topic,
            partition=p_idx,
            offset=partition.next_offset,
            timestamp=time.time(),
            headers=message.headers,
            message_id=str(uuid.uuid4()),
        )
        partition.append(stored)

        # Enforce retention
        retention = self.topic_config[topic]["retention_count"]
        partition.trim(retention)

        return stored

    def create_consumer_group(self, group_id: str, topic: str,
                              delivery: str = "at_least_once") -> None:
        """Create a consumer group for a topic."""
        if topic not in self.topics:
            raise ValueError(f"Topic '{topic}' does not exist")
        if group_id in self.consumer_groups:
            raise ValueError(f"Consumer group '{group_id}' already exists")
        num_p = self.topic_config[topic]["num_partitions"]
        self.consumer_groups[group_id] = ConsumerGroup(
            group_id, topic, num_p, delivery
        )

    def add_consumer(self, group_id: str, consumer_id: str) -> dict:
        """Add a consumer to a group. Returns partition assignments."""
        if group_id not in self.consumer_groups:
            raise ValueError(f"Consumer group '{group_id}' does not exist")
        return self.consumer_groups[group_id].add_consumer(consumer_id)

    def remove_consumer(self, group_id: str, consumer_id: str) -> None:
        """Remove a consumer and rebalance."""
        if group_id not in self.consumer_groups:
            raise ValueError(f"Consumer group '{group_id}' does not exist")
        self.consumer_groups[group_id].remove_consumer(consumer_id)

    def poll(self, group_id: str, consumer_id: str,
             max_messages: int = 10) -> list[StoredMessage]:
        """Fetch messages for a consumer from its assigned partitions."""
        group = self.consumer_groups[group_id]
        if consumer_id not in group.assignments:
            return []

        result = []
        for p_idx in group.assignments[consumer_id]:
            partition = self.topics[group.topic][p_idx]
            offset = group.current_offset[p_idx]
            msgs = partition.get(offset, max_messages - len(result))
            for msg in msgs:
                if group.delivery == "exactly_once" and msg.message_id in group.seen_message_ids:
                    group.current_offset[p_idx] = msg.offset + 1
                    continue
                result.append(msg)
                group.current_offset[p_idx] = msg.offset + 1
                if group.delivery == "exactly_once":
                    group.seen_message_ids.add(msg.message_id)
            if len(result) >= max_messages:
                break

        # At-most-once: auto-commit so messages won't be re-delivered
        if group.delivery == "at_most_once":
            self._do_commit(group, consumer_id)

        return result

    def _do_commit(self, group: ConsumerGroup, consumer_id: str):
        for p_idx in group.assignments.get(consumer_id, []):
            group.committed_offset[p_idx] = group.current_offset[p_idx]

    def commit(self, group_id: str, consumer_id: str) -> None:
        """Commit the current offset for the consumer."""
        group = self.consumer_groups[group_id]
        self._do_commit(group, consumer_id)

    def seek(self, group_id: str, partition: int, offset: int) -> None:
        """Seek to a specific offset in a partition."""
        group = self.consumer_groups[group_id]
        if partition < 0 or partition >= group.num_partitions:
            raise ValueError(f"Invalid partition {partition}")
        p = self.topics[group.topic][partition]
        if offset == -1:  # seek to beginning
            offset = p.base_offset
        elif offset == -2:  # seek to end
            offset = p.next_offset
        group.current_offset[partition] = offset
        group.committed_offset[partition] = offset

    def acknowledge(self, group_id: str, message: StoredMessage,
                    success: bool = True, max_failures: int = 3) -> None:
        """Acknowledge a message. On repeated failure, send to DLQ."""
        group = self.consumer_groups[group_id]
        if not success:
            group.failure_counts[message.message_id] += 1
            if group.failure_counts[message.message_id] >= max_failures:
                self._send_to_dlq(group.topic, message)
                del group.failure_counts[message.message_id]

    def _send_to_dlq(self, topic: str, message: StoredMessage):
        dlq_topic = f"__dlq_{topic}"
        if dlq_topic not in self.topics:
            self.create_topic(dlq_topic, num_partitions=1)
        self.publish(dlq_topic, Message(
            key=message.key, value=message.value, headers=message.headers
        ))

    def get_topic_info(self, topic: str) -> dict:
        """Return topic metadata."""
        if topic not in self.topics:
            raise ValueError(f"Topic '{topic}' does not exist")
        partitions = self.topics[topic]
        return {
            "name": topic,
            "num_partitions": len(partitions),
            "retention_count": self.topic_config[topic]["retention_count"],
            "partitions": [
                {
                    "id": i,
                    "message_count": len(p.messages),
                    "base_offset": p.base_offset,
                    "next_offset": p.next_offset,
                }
                for i, p in enumerate(partitions)
            ],
        }

    def get_consumer_lag(self, group_id: str) -> dict:
        """Return lag per partition for a consumer group."""
        group = self.consumer_groups[group_id]
        lag = {}
        for p_idx in range(group.num_partitions):
            partition = self.topics[group.topic][p_idx]
            committed = group.committed_offset[p_idx]
            lag[p_idx] = partition.next_offset - committed
        return lag
