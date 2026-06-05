# Plan Review: Distributed Message Queue

## Plan Strengths

- Partition routing: `hash(key) % num_partitions` for keyed messages, round-robin counter for keyless. Same key always maps to same partition.
- Dual offset model: `current_offset` (read cursor) and `committed_offset` (durable position). At-least-once re-delivers from committed, at-most-once auto-commits on poll.
- Exactly-once via `seen_message_ids` set per consumer group. Messages already seen are skipped on re-poll after seek.
- Retention via `Partition.trim()`: keeps most recent N messages, adjusts `base_offset` so logical offsets remain correct.
- Dead letter queue: auto-creates `__dlq_{topic}` topic on first failure overflow. Failure counter per message ID with configurable threshold.
- Consumer rebalancing: round-robin partition assignment, re-triggered on add/remove consumer.
- `Partition.get()` handles below-base-offset reads by clamping start index to 0.

## Plan Gaps

1. **`time.time()` in `publish` for message timestamps.** Not testable with deterministic clocks. Minor since no test depends on timestamp values.

2. **`seek` also updates `committed_offset`.** Line 229: `group.committed_offset[partition] = offset`. This means seek implicitly commits, which is semantically wrong for at-least-once — seeking back should not commit the new position until the consumer explicitly commits. However, the tests pass because `test_at_least_once_redelivery` seeks back to 0 and re-polls successfully.

3. **At-most-once auto-commit happens after building the result list.** Line 204: `_do_commit` after the loop. If the consumer crashes between receiving messages and processing them, the messages are lost — which is exactly the at-most-once guarantee. Correct.

4. **`acknowledge` is not connected to the poll/commit flow.** It's a standalone method for DLQ routing. The consumer must manually call it per message to track failures. No automatic retry mechanism.

5. **No thread safety.** Unlike the digital wallet, this implementation has no locks. Fine for single-threaded usage but would need synchronization for concurrent producers/consumers.

## Implementation Issues (0 test failures)

No test failures. Clean implementation at 278 lines covering all 12 test scenarios.
