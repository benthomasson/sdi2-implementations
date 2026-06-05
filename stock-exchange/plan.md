# Plan (Iteration 1)

Task: Stock Exchange Matching Engine
================================
SDI Vol 2 Reference: Chapter 13 - Stock Exchange

Overview
--------
Build a stock exchange matching engine with a limit order book. The matching
engine is the core of any exchange — it matches buy orders with sell orders
using price-time priority (best price first, then earliest order at that price).
Supports limit orders, market orders, order cancellation, and provides a
real-time view of the order book depth (L2 data).

Requirements
------------
1. Order types:
   - Limit order: buy/sell at a specific price or better.
   - Market order: buy/sell immediately at the best available price.
     Partial fills are allowed.
2. Price-time priority: orders at the same price are filled in FIFO order
   (earliest first).
3. Order matching:
   - A buy limit order matches with sell orders at or below the buy price.
   - A sell limit order matches with buy orders at or above the sell price.
   - Market buy orders match with the lowest sell price.
   - Market sell orders match with the highest buy price.
4. Partial fills: if an order can only be partially filled, the remaining
   quantity stays in the order book.
5. Order book: maintain separate buy (bid) and sell (ask) sides.
   - Bids sorted by price descending (highest first).
   - Asks sorted by price ascending (lowest first).
6. Trade execution: when orders match, create a Trade record with buyer,
   seller, price, quantity, and timestamp.
7. Order cancellation: cancel an open order, removing it from the book.
8. Order status: NEW → PARTIALLY_FILLED → FILLED / CANCELLED.
9. L2 order book depth: aggregate quantities at each price level.
   Return top N levels for bids and asks.
10. Best bid/ask (BBO): return the current best bid and best ask prices.
11. Spread: difference between best ask and best bid.
12. Trade history: ordered list of executed trades.
13. Multiple symbols: support order books for different stock symbols.

Interface
---------
class Order:
    def __init__(self, order_id: str, symbol: str, side: str,
                 order_type: str, quantity: int,
                 price: float = None):
        """An order. side: 'BUY'|'SELL'. order_type: 'LIMIT'|'MARKET'."""

class Trade:
    def __init__(self, trade_id: str, symbol: str, buy_order_id: str,
                 sell_order_id: str, price: float, quantity: int,
                 timestamp: float):
        """An executed trade."""

class OrderBook:
    def __init__(self, symbol: str):
        """An order book for a single symbol."""

    def place_order(self, order: Order) -> list[Trade]:
        """Place an order. Attempts to match immediately.
        Returns list of trades executed."""

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True if cancelled."""

    def get_order(self, order_id: str) -> Order | None:
        """Look up an order."""

    def get_book_depth(self, levels: int = 10) -> dict:
        """Return L2 order book: {bids: [(price, qty)], asks: [(price, qty)]}
        Aggregated by price level, sorted best-first."""

    def get_bbo(self) -> dict:
        """Return best bid and best ask: {bid: float, ask: float, spread: float}."""

    def get_trades(self, limit: int = 50) -> list[Trade]:
        """Recent trade history."""

    def get_open_orders(self, side: str = None) -> list[Order]:
        """List open orders, optionally filtered by side."""

class Exchange:
    def __init__(self):
        """Initialize the exchange with multiple order books."""

    def place_order(self, order: Order) -> list[Trade]:
        """Route order to the correct order book."""

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order."""

    def get_book(self, symbol: str) -> OrderBook:
        """Get order book for a symbol."""

    def get_symbols(self) -> list[str]:
        """List all symbols with active order books."""

Example Usage
-------------
    exchange = Exchange()
    book = exchange.get_book("AAPL")

    # Place sell limit orders
    exchange.place_order(Order("s1", "AAPL", "SELL", "LIMIT", 100, price=150.0))
    exchange.place_order(Order("s2", "AAPL", "SELL", "LIMIT", 50, price=151.0))

    # Place buy limit order that matches
    trades = exchange.place_order(
        Order("b1", "AAPL", "BUY", "LIMIT", 80, price=150.0))
    assert len(trades) == 1
    assert trades[0].price == 150.0
    assert trades[0].quantity == 80

    # Remaining sell quantity at 150
    depth = book.get_book_depth()
    assert depth["asks"][0] == (150.0, 20)  # 100 - 80 = 20 remaining

    # Market buy
    trades = exchange.place_order(
        Order("b2", "AAPL", "BUY", "MARKET", 30))
    assert trades[0].price == 150.0  # fills remaining 20 at 150
    assert trades[0].quantity == 20
    assert trades[1].price == 151.0  # fills 10 at 151
    assert trades[1].quantity == 10

    # BBO
    bbo = book.get_bbo()
    assert bbo["ask"] == 151.0
    assert bbo["bid"] is None  # no buy orders remaining

    # Cancel
    exchange.place_order(Order("b3", "AAPL", "BUY", "LIMIT", 50, price=149.0))
    assert exchange.cancel_order("AAPL", "b3") == True
    assert book.get_bbo()["bid"] is None

Constraints
-----------
- Prices are positive floats (2 decimal precision).
- Quantities are positive integers.
- Order IDs are unique strings.
- Matching must be deterministic: same orders in same sequence produce
  same trades.
- Order book operations (place, cancel) should be efficient: O(log N)
  for matching, O(1) for BBO.
- Handle up to 100,000 orders per symbol.
- Market orders that can't be fully filled are partially filled (remaining
  quantity is cancelled, not kept in book).
- Target: 250-400 lines of Python.

Testing Requirements
--------------------
1. Limit buy matches with limit sell at compatible price.
2. Price-time priority: earlier order fills first at same price.
3. Partial fill leaves remainder in book.
4. Market buy fills at best ask price.
5. Market sell fills at best bid price.
6. Market order across multiple price levels.
7. No match: limit order rests in book.
8. Cancel removes order from book.
9. Cancel non-existent order returns False.
10. Order book depth aggregates correctly.
11. BBO reflects current best prices.
12. Spread calculation is correct.
13. Trade history records all executions.
14. Multiple symbols have independent order books.
15. Market order with insufficient liquidity partially fills.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `PLAN.md`. The key insight is that this is a well-understood data structure problem — a sorted dict (or bisect-maintained list) of price levels, each holding a FIFO queue of orders, with greedy matching against the opposite side. No complex architectural decisions needed.

[Committed changes to planner branch]