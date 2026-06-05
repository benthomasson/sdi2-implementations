# Plan Review: Hotel Reservation System

## Plan Strengths

- Per-date inventory tracking: `(hotel_id, type_id, date) -> {booked, version}`. Availability is `total_rooms - booked` with minimum across all dates in range.
- Optimistic concurrency: snapshots versions in phase 1, verifies unchanged in phase 2, then commits. Prevents double-booking if another reservation modifies the same inventory between phases.
- Three-tier cancellation refund policy: full (>24h before check-in), partial (<24h), none (after check-in). `cancel_time` parameter enables deterministic testing.
- Dynamic pricing: occupancy-based multipliers (1.1x at 50%, 1.3x at 70%, 1.5x at 90%) stack with seasonal multipliers.
- Idempotency key maps to reservation ID — duplicate requests return the same reservation without side effects.
- Search filters by city, room type, max price. Returns minimum availability and average price across the date range.

## Plan Gaps

1. **Optimistic locking phases 1 and 2 execute in the same thread with no interleaving.** In a single-threaded in-memory system, the version can never change between the two phases. The locking mechanism is structurally correct but never actually detects a conflict. The test for "concurrent booking" (test 10 in hotel_reservation.py) only verifies version bumps, not actual conflict detection.

2. **`cancel()` uses `datetime.now()` when no `cancel_time` is provided.** This makes the refund calculation non-deterministic in production use. All tests pass explicit cancel times, so this doesn't cause failures.

3. **No PENDING -> CONFIRMED status transition.** Reservations go directly to CONFIRMED on creation. The plan mentions PENDING as a status but it's never used.

4. **`_get_price` computes dynamic pricing at query time.** This means the price shown in search results may differ from the price charged at reservation time if other bookings change occupancy between search and reserve. The `reserve` method computes price after committing inventory changes, so the price reflects the post-booking occupancy — which charges the booker for their own occupancy increase.

## Implementation Issues (0 test failures)

No test failures. Clean implementation at 253 lines (plus inline test_all). All 9 pytest test cases pass.
