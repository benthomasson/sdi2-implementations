"""Tests for Stock Exchange Matching Engine."""

import sys
sys.path.insert(0, "../implementer")

from solution import Order, Trade, OrderBook, Exchange


def make_exchange():
    """Fresh exchange with reset Trade counter."""
    Trade._counter = 0
    return Exchange()


def test_example_usage():
    """Full example from the spec."""
    exchange = make_exchange()
    book = exchange.get_book("AAPL")

    exchange.place_order(Order("s1", "AAPL", "SELL", "LIMIT", 100, price=150.0))
    exchange.place_order(Order("s2", "AAPL", "SELL", "LIMIT", 50, price=151.0))

    trades = exchange.place_order(Order("b1", "AAPL", "BUY", "LIMIT", 80, price=150.0))
    assert len(trades) == 1
    assert trades[0].price == 150.0
    assert trades[0].quantity == 80

    depth = book.get_book_depth()
    assert depth["asks"][0] == (150.0, 20)

    trades = exchange.place_order(Order("b2", "AAPL", "BUY", "MARKET", 30))
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


def test_price_time_priority():
    """Earlier order at same price fills first."""
    exchange = make_exchange()
    exchange.place_order(Order("s1", "AAPL", "SELL", "LIMIT", 50, price=100.0))
    exchange.place_order(Order("s2", "AAPL", "SELL", "LIMIT", 50, price=100.0))

    trades = exchange.place_order(Order("b1", "AAPL", "BUY", "LIMIT", 50, price=100.0))
    assert len(trades) == 1
    assert trades[0].sell_order_id == "s1"  # s1 was first


def test_partial_fill():
    """Partial fill leaves remainder in book with correct status."""
    exchange = make_exchange()
    exchange.place_order(Order("s1", "AAPL", "SELL", "LIMIT", 100, price=50.0))

    trades = exchange.place_order(Order("b1", "AAPL", "BUY", "LIMIT", 30, price=50.0))
    assert len(trades) == 1
    assert trades[0].quantity == 30

    s1 = exchange.get_book("AAPL").get_order("s1")
    assert s1.status == "PARTIALLY_FILLED"
    assert s1.remaining == 70

    depth = exchange.get_book("AAPL").get_book_depth()
    assert depth["asks"][0] == (50.0, 70)


def test_no_match_rests_in_book():
    """Limit order with no match rests in book."""
    exchange = make_exchange()
    exchange.place_order(Order("b1", "AAPL", "BUY", "LIMIT", 100, price=99.0))
    exchange.place_order(Order("s1", "AAPL", "SELL", "LIMIT", 100, price=101.0))

    bbo = exchange.get_book("AAPL").get_bbo()
    assert bbo["bid"] == 99.0
    assert bbo["ask"] == 101.0
    assert bbo["spread"] == 2.0


def test_cancel_and_nonexistent():
    """Cancel works; cancelling nonexistent returns False."""
    exchange = make_exchange()
    exchange.place_order(Order("b1", "AAPL", "BUY", "LIMIT", 50, price=100.0))

    assert exchange.cancel_order("AAPL", "b1") is True
    assert exchange.cancel_order("AAPL", "b1") is False  # already cancelled
    assert exchange.cancel_order("AAPL", "nope") is False  # never existed
    assert exchange.cancel_order("NOPE", "b1") is False  # wrong symbol


def test_market_order_insufficient_liquidity():
    """Market order partially fills then remainder is cancelled."""
    exchange = make_exchange()
    exchange.place_order(Order("s1", "AAPL", "SELL", "LIMIT", 20, price=100.0))

    trades = exchange.place_order(Order("b1", "AAPL", "BUY", "MARKET", 50))
    assert len(trades) == 1
    assert trades[0].quantity == 20

    b1 = exchange.get_book("AAPL").get_order("b1")
    assert b1.status == "CANCELLED"
    assert b1.filled_quantity == 20


def test_multiple_symbols():
    """Different symbols have independent order books."""
    exchange = make_exchange()
    exchange.place_order(Order("a1", "AAPL", "SELL", "LIMIT", 100, price=150.0))
    exchange.place_order(Order("g1", "GOOG", "SELL", "LIMIT", 100, price=2800.0))

    trades = exchange.place_order(Order("b1", "AAPL", "BUY", "LIMIT", 50, price=150.0))
    assert len(trades) == 1
    assert trades[0].symbol == "AAPL"

    # GOOG book unaffected
    assert exchange.get_book("GOOG").get_bbo()["ask"] == 2800.0
    assert exchange.get_book("AAPL").get_bbo()["ask"] == 150.0
    assert set(exchange.get_symbols()) == {"AAPL", "GOOG"}


def test_trade_history():
    """Trade history records all executions."""
    exchange = make_exchange()
    book = exchange.get_book("AAPL")
    exchange.place_order(Order("s1", "AAPL", "SELL", "LIMIT", 100, price=100.0))
    exchange.place_order(Order("b1", "AAPL", "BUY", "LIMIT", 40, price=100.0))
    exchange.place_order(Order("b2", "AAPL", "BUY", "LIMIT", 30, price=100.0))

    history = book.get_trades()
    assert len(history) == 2
    assert history[0].quantity == 40
    assert history[1].quantity == 30


def test_book_depth_aggregation():
    """L2 depth aggregates multiple orders at same price."""
    exchange = make_exchange()
    book = exchange.get_book("AAPL")
    exchange.place_order(Order("b1", "AAPL", "BUY", "LIMIT", 100, price=99.0))
    exchange.place_order(Order("b2", "AAPL", "BUY", "LIMIT", 50, price=99.0))
    exchange.place_order(Order("b3", "AAPL", "BUY", "LIMIT", 200, price=98.0))

    depth = book.get_book_depth(levels=2)
    assert depth["bids"][0] == (99.0, 150)  # 100 + 50
    assert depth["bids"][1] == (98.0, 200)
    assert len(depth["asks"]) == 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  PASS: {t.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
