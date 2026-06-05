"""Stock Exchange Matching Engine with limit order book."""

import time
from collections import deque


class Order:
    """An order. side: 'BUY'|'SELL'. order_type: 'LIMIT'|'MARKET'."""

    def __init__(self, order_id: str, symbol: str, side: str,
                 order_type: str, quantity: int, price: float = None):
        self.order_id = order_id
        self.symbol = symbol
        self.side = side
        self.order_type = order_type
        self.quantity = quantity
        self.price = price
        self.filled_quantity = 0
        self.status = "NEW"
        self.timestamp = time.time()

    @property
    def remaining(self):
        return self.quantity - self.filled_quantity


class Trade:
    """An executed trade."""

    _counter = 0

    def __init__(self, trade_id: str, symbol: str, buy_order_id: str,
                 sell_order_id: str, price: float, quantity: int,
                 timestamp: float):
        self.trade_id = trade_id
        self.symbol = symbol
        self.buy_order_id = buy_order_id
        self.sell_order_id = sell_order_id
        self.price = price
        self.quantity = quantity
        self.timestamp = timestamp

    @classmethod
    def create(cls, symbol, buy_order_id, sell_order_id, price, quantity):
        cls._counter += 1
        return cls(f"t{cls._counter}", symbol, buy_order_id,
                   sell_order_id, price, quantity, time.time())


class OrderBook:
    """Order book for a single symbol using bisect-maintained price levels."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        # price -> deque of orders
        self._bids = {}  # buy side
        self._asks = {}  # sell side
        # sorted price lists (bids descending, asks ascending)
        self._bid_prices = []  # sorted descending
        self._ask_prices = []  # sorted ascending
        self._orders = {}  # order_id -> order
        self._trades = []

    def _add_to_book(self, order):
        """Add a resting order to the book."""
        self._orders[order.order_id] = order
        if order.side == "BUY":
            price = order.price
            if price not in self._bids:
                self._bids[price] = deque()
                # Insert into sorted desc list
                self._bid_prices.append(price)
                self._bid_prices.sort(reverse=True)
            self._bids[price].append(order)
        else:
            price = order.price
            if price not in self._asks:
                self._asks[price] = deque()
                self._ask_prices.append(price)
                self._ask_prices.sort()
            self._asks[price].append(order)

    def _remove_from_book(self, order):
        """Remove an order from the book."""
        if order.side == "BUY":
            q = self._bids.get(order.price)
            if q:
                try:
                    q.remove(order)
                except ValueError:
                    pass
                if not q:
                    del self._bids[order.price]
                    self._bid_prices.remove(order.price)
        else:
            q = self._asks.get(order.price)
            if q:
                try:
                    q.remove(order)
                except ValueError:
                    pass
                if not q:
                    del self._asks[order.price]
                    self._ask_prices.remove(order.price)

    def _match_order(self, order):
        """Match incoming order against resting orders. Returns trades."""
        trades = []

        if order.side == "BUY":
            # Match against asks (lowest first)
            while order.remaining > 0 and self._ask_prices:
                best_ask = self._ask_prices[0]
                if order.order_type == "LIMIT" and best_ask > order.price:
                    break
                q = self._asks[best_ask]
                while order.remaining > 0 and q:
                    resting = q[0]
                    fill_qty = min(order.remaining, resting.remaining)
                    order.filled_quantity += fill_qty
                    resting.filled_quantity += fill_qty
                    trades.append(Trade.create(
                        self.symbol, order.order_id, resting.order_id,
                        resting.price, fill_qty))
                    self._update_status(order)
                    self._update_status(resting)
                    if resting.remaining == 0:
                        q.popleft()
                if not q:
                    del self._asks[best_ask]
                    self._ask_prices.pop(0)
        else:
            # Match against bids (highest first)
            while order.remaining > 0 and self._bid_prices:
                best_bid = self._bid_prices[0]
                if order.order_type == "LIMIT" and best_bid < order.price:
                    break
                q = self._bids[best_bid]
                while order.remaining > 0 and q:
                    resting = q[0]
                    fill_qty = min(order.remaining, resting.remaining)
                    order.filled_quantity += fill_qty
                    resting.filled_quantity += fill_qty
                    trades.append(Trade.create(
                        self.symbol, resting.order_id, order.order_id,
                        resting.price, fill_qty))
                    self._update_status(order)
                    self._update_status(resting)
                    if resting.remaining == 0:
                        q.popleft()
                if not q:
                    del self._bids[best_bid]
                    self._bid_prices.pop(0)

        return trades

    def _update_status(self, order):
        if order.filled_quantity >= order.quantity:
            order.status = "FILLED"
        elif order.filled_quantity > 0:
            order.status = "PARTIALLY_FILLED"

    def place_order(self, order):
        """Place an order. Returns list of trades executed."""
        self._orders[order.order_id] = order
        trades = self._match_order(order)

        if order.remaining > 0:
            if order.order_type == "MARKET":
                order.status = "CANCELLED"
            else:
                self._add_to_book(order)

        self._trades.extend(trades)
        return trades

    def cancel_order(self, order_id):
        """Cancel an open order. Returns True if cancelled."""
        order = self._orders.get(order_id)
        if not order or order.status in ("FILLED", "CANCELLED"):
            return False
        self._remove_from_book(order)
        order.status = "CANCELLED"
        return True

    def get_order(self, order_id):
        """Look up an order."""
        return self._orders.get(order_id)

    def get_book_depth(self, levels=10):
        """Return L2 order book depth aggregated by price level."""
        bids = []
        for p in self._bid_prices[:levels]:
            total = sum(o.remaining for o in self._bids[p])
            if total > 0:
                bids.append((p, total))
        asks = []
        for p in self._ask_prices[:levels]:
            total = sum(o.remaining for o in self._asks[p])
            if total > 0:
                asks.append((p, total))
        return {"bids": bids, "asks": asks}

    def get_bbo(self):
        """Return best bid/ask and spread."""
        bid = self._bid_prices[0] if self._bid_prices else None
        ask = self._ask_prices[0] if self._ask_prices else None
        spread = None
        if bid is not None and ask is not None:
            spread = round(ask - bid, 2)
        return {"bid": bid, "ask": ask, "spread": spread}

    def get_trades(self, limit=50):
        """Recent trade history."""
        return self._trades[-limit:]

    def get_open_orders(self, side=None):
        """List open orders, optionally filtered by side."""
        result = []
        for order in self._orders.values():
            if order.status in ("NEW", "PARTIALLY_FILLED"):
                if side is None or order.side == side:
                    result.append(order)
        return result


class Exchange:
    """Multi-symbol exchange routing orders to per-symbol order books."""

    def __init__(self):
        self._books = {}

    def get_book(self, symbol):
        """Get or create order book for a symbol."""
        if symbol not in self._books:
            self._books[symbol] = OrderBook(symbol)
        return self._books[symbol]

    def place_order(self, order):
        """Route order to the correct order book."""
        return self.get_book(order.symbol).place_order(order)

    def cancel_order(self, symbol, order_id):
        """Cancel an order."""
        if symbol not in self._books:
            return False
        return self._books[symbol].cancel_order(order_id)

    def get_symbols(self):
        """List all symbols with active order books."""
        return list(self._books.keys())


if __name__ == "__main__":
    # Example usage from spec
    exchange = Exchange()
    book = exchange.get_book("AAPL")

    exchange.place_order(Order("s1", "AAPL", "SELL", "LIMIT", 100, price=150.0))
    exchange.place_order(Order("s2", "AAPL", "SELL", "LIMIT", 50, price=151.0))

    trades = exchange.place_order(
        Order("b1", "AAPL", "BUY", "LIMIT", 80, price=150.0))
    assert len(trades) == 1
    assert trades[0].price == 150.0
    assert trades[0].quantity == 80

    depth = book.get_book_depth()
    assert depth["asks"][0] == (150.0, 20)

    trades = exchange.place_order(
        Order("b2", "AAPL", "BUY", "MARKET", 30))
    assert trades[0].price == 150.0
    assert trades[0].quantity == 20
    assert trades[1].price == 151.0
    assert trades[1].quantity == 10

    bbo = book.get_bbo()
    assert bbo["ask"] == 151.0
    assert bbo["bid"] is None

    exchange.place_order(Order("b3", "AAPL", "BUY", "LIMIT", 50, price=149.0))
    assert exchange.cancel_order("AAPL", "b3") is True
    assert book.get_bbo()["bid"] is None

    print("All assertions passed.")
