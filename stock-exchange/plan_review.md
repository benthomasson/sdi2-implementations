# Plan Review: Stock Exchange Matching Engine

## Plan Strengths

- Price-time priority matching: bids sorted descending, asks sorted ascending. FIFO `deque` per price level ensures earliest order at same price fills first.
- Greedy matching in `_match_order`: incoming order walks the opposite side from best price inward, filling against resting orders until exhausted, price limit hit, or no more liquidity.
- Trade creation records buyer and seller correctly: buy-side matching assigns `buy_order_id=incoming, sell_order_id=resting`; sell-side swaps them.
- Market orders with insufficient liquidity are partially filled, remainder cancelled (lines 168-170).
- `_remove_from_book` handles cleanup of empty price level deques and sorted price lists.
- L2 depth aggregation: sums `remaining` quantity across all orders at each price level.
- `Exchange` routes orders to per-symbol `OrderBook` instances with get-or-create semantics.
- Order status machine: NEW -> PARTIALLY_FILLED -> FILLED / CANCELLED.

## Plan Gaps

1. **`_bid_prices` and `_ask_prices` use `list.sort()` on every insert.** Lines 73, 80: O(N log N) per insert. `bisect.insort` would give O(N) (due to list shift) with O(log N) search. For the 100K order constraint this is adequate but not optimal.

2. **`Trade._counter` is a class variable shared across all tests.** Line 30: `_counter = 0`. The test helper `make_exchange()` resets it (line 12), but if tests run in parallel or out of order, trade IDs could collide. Tests handle this correctly by resetting in `make_exchange`.

3. **`place_order` adds to `_orders` before matching, then `_add_to_book` adds again.** Line 165: `self._orders[order.order_id] = order`, then line 172: `_add_to_book` also sets `self._orders[order.order_id] = order`. Redundant but harmless since same reference.

4. **No validation of order parameters.** Negative prices, zero quantities, unknown side/type values are all accepted without error. In a real exchange these would be rejected at the gateway.

5. **`_ask_prices.pop(0)` is O(N).** Line 131: popping from the front of a list. A `deque` for price levels or `SortedList` would avoid this, though the inner loop typically drains one price level per iteration so the amortized cost is acceptable.

6. **Market sell order matching.** Lines 132-153: sell-side matching creates trades with `buy_order_id=resting.order_id, sell_order_id=order.order_id`. Correct — the resting order on the bid side is the buyer, incoming sell is the seller.

## Implementation Issues (0 test failures)

No test failures. Clean implementation at 287 lines. 9/9 tests pass covering the full spec example, price-time priority, partial fills, market orders, cancellation, multi-symbol, trade history, and L2 depth aggregation.
