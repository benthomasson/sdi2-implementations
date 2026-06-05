"""Tests for Hotel Reservation System."""

import sys
sys.path.insert(0, "../implementer")

from hotel_reservation import (
    HotelReservationSystem, Hotel, RoomType, Reservation,
    AvailabilityError, ConcurrencyError, _date_range,
)


def make_system():
    """Create a system with one hotel and one room type for quick tests."""
    s = HotelReservationSystem()
    s.add_hotel(Hotel("h1", "Grand Hotel", "NYC"))
    s.add_room_type(RoomType("std", "h1", "Standard", 100.0, 5))
    return s


def test_example_usage():
    """Verify the exact example from the task spec."""
    system = HotelReservationSystem()
    system.add_hotel(Hotel("h1", "Grand Hotel", "NYC"))
    system.add_room_type(RoomType("std", "h1", "Standard", 100.0, 5))

    results = system.search("2024-03-15", "2024-03-17", city="NYC")
    assert len(results) == 1
    assert results[0]["available_rooms"] == 5

    res = system.reserve("h1", "std", "Alice", "2024-03-15", "2024-03-17")
    assert res.total_price == 200.0

    occ = system.get_occupancy("h1", "std", "2024-03-15")
    assert occ["available_rooms"] == 4

    result = system.cancel(res.reservation_id, cancel_time="2024-03-01")
    assert result["refund_amount"] == 200.0

    r1 = system.reserve("h1", "std", "Bob", "2024-03-20", "2024-03-21",
                         idempotency_key="req-123")
    r2 = system.reserve("h1", "std", "Bob", "2024-03-20", "2024-03-21",
                         idempotency_key="req-123")
    assert r1.reservation_id == r2.reservation_id
    print("PASS: example usage")


def test_double_booking_prevented():
    """Book all rooms, then verify next booking fails."""
    s = make_system()
    for i in range(5):
        s.reserve("h1", "std", f"Guest{i}", "2024-04-01", "2024-04-02")
    try:
        s.reserve("h1", "std", "Extra", "2024-04-01", "2024-04-02")
        assert False, "Should have raised AvailabilityError"
    except AvailabilityError:
        pass
    print("PASS: double booking prevented")


def test_cancellation_restores_availability():
    s = make_system()
    res = s.reserve("h1", "std", "Alice", "2024-04-01", "2024-04-02")
    assert s.get_occupancy("h1", "std", "2024-04-01")["available_rooms"] == 4
    s.cancel(res.reservation_id, cancel_time="2024-03-01")
    assert s.get_occupancy("h1", "std", "2024-04-01")["available_rooms"] == 5
    print("PASS: cancellation restores availability")


def test_seasonal_pricing():
    s = make_system()
    s.set_seasonal_pricing("h1", "std", "2024-06-01", "2024-08-31", 1.5)
    results = s.search("2024-06-15", "2024-06-17")
    assert results[0]["price_per_night"] == 150.0
    print("PASS: seasonal pricing")


def test_dynamic_pricing():
    s = HotelReservationSystem()
    s.add_hotel(Hotel("h1", "Test", "NYC"))
    s.add_room_type(RoomType("std", "h1", "Standard", 100.0, 10))
    # 50% occupancy -> 1.1x
    for i in range(5):
        s.reserve("h1", "std", f"G{i}", "2024-04-01", "2024-04-02")
    results = s.search("2024-04-01", "2024-04-02")
    assert round(results[0]["price_per_night"], 2) == 110.0
    # 70% -> 1.3x
    for i in range(2):
        s.reserve("h1", "std", f"G{5+i}", "2024-04-01", "2024-04-02")
    results = s.search("2024-04-01", "2024-04-02")
    assert round(results[0]["price_per_night"], 2) == 130.0
    print("PASS: dynamic pricing")


def test_multi_date_overlap():
    """Booking overlapping date ranges should fail if any date is full."""
    s = HotelReservationSystem()
    s.add_hotel(Hotel("h1", "Test", "NYC"))
    s.add_room_type(RoomType("std", "h1", "Standard", 100.0, 1))
    s.reserve("h1", "std", "A", "2024-04-02", "2024-04-04")
    try:
        s.reserve("h1", "std", "B", "2024-04-01", "2024-04-03")
        assert False, "Should fail on overlapping date"
    except AvailabilityError:
        pass
    print("PASS: multi-date overlap")


def test_cancellation_refund_policies():
    s = HotelReservationSystem()
    s.add_hotel(Hotel("h1", "Test", "NYC"))
    s.add_room_type(RoomType("std", "h1", "Standard", 100.0, 10))

    # Full refund (>24h before)
    r = s.reserve("h1", "std", "A", "2024-06-10", "2024-06-12")
    result = s.cancel(r.reservation_id, cancel_time="2024-06-08 10:00:00")
    assert result["refund_amount"] == 200.0

    # Partial refund (<24h before)
    r = s.reserve("h1", "std", "B", "2024-06-10", "2024-06-12")
    result = s.cancel(r.reservation_id, cancel_time="2024-06-09 12:00:00")
    assert result["refund_amount"] == 100.0

    # No refund (after check-in)
    r = s.reserve("h1", "std", "C", "2024-06-10", "2024-06-12")
    result = s.cancel(r.reservation_id, cancel_time="2024-06-10 14:00:00")
    assert result["refund_amount"] == 0.0
    print("PASS: cancellation refund policies")


def test_concurrency_version_bump():
    """Version number changes after booking, confirming optimistic locking state."""
    s = make_system()
    inv = s._get_inventory("h1", "std", "2024-05-01")
    v0 = inv["version"]
    s.reserve("h1", "std", "A", "2024-05-01", "2024-05-02")
    inv = s._get_inventory("h1", "std", "2024-05-01")
    assert inv["version"] == v0 + 1
    print("PASS: concurrency version bump")


def test_search_filters():
    """City and max_price filters work."""
    s = HotelReservationSystem()
    s.add_hotel(Hotel("h1", "Grand Hotel", "NYC"))
    s.add_hotel(Hotel("h2", "Beach Resort", "Miami"))
    s.add_room_type(RoomType("std", "h1", "Standard", 100.0, 5))
    s.add_room_type(RoomType("std", "h2", "Standard", 150.0, 4))

    # Filter by city
    results = s.search("2024-04-01", "2024-04-02", city="Miami")
    assert len(results) == 1
    assert results[0]["hotel"].city == "Miami"

    # Filter by max_price
    results = s.search("2024-04-01", "2024-04-02", max_price=120.0)
    assert len(results) == 1
    assert results[0]["price_per_night"] == 100.0
    print("PASS: search filters")


if __name__ == "__main__":
    test_example_usage()
    test_double_booking_prevented()
    test_cancellation_restores_availability()
    test_seasonal_pricing()
    test_dynamic_pricing()
    test_multi_date_overlap()
    test_cancellation_refund_policies()
    test_concurrency_version_bump()
    test_search_filters()
    print("\nAll tests passed!")
