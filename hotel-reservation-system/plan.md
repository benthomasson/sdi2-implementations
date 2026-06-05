# Plan (Iteration 1)

Task: Hotel Reservation System
=========================
SDI Vol 2 Reference: Chapter 7 - Hotel Reservation System

Overview
--------
Build a hotel reservation system with inventory management, search, booking,
and cancellation. The core challenge is preventing double-bookings using
optimistic concurrency control — multiple users may try to book the last
available room simultaneously.

Requirements
------------
1. Hotel management: add hotels with rooms, room types, and pricing.
2. Room types: each type has a name, base price, and total inventory count.
3. Availability search: given a date range and optional filters (city,
   room type, price range), return available hotels with room counts.
4. Reservation: book a room for a date range. Must atomically check
   availability and reserve to prevent double-booking.
5. Optimistic concurrency: use a version number on inventory. If the
   version changed between check and reserve, retry or fail.
6. Cancellation: cancel a reservation, releasing inventory. Support
   cancellation policies (full refund, partial, none based on timing).
7. Pricing: support base price, seasonal pricing multipliers, and
   dynamic pricing based on occupancy (higher price when nearly full).
8. Reservation status: PENDING → CONFIRMED → CANCELLED / COMPLETED.
9. Idempotency: reservation requests with the same idempotency key
   return the existing reservation.

Interface
---------
class Hotel:
    def __init__(self, hotel_id: str, name: str, city: str):
        """A hotel."""

class RoomType:
    def __init__(self, type_id: str, hotel_id: str, name: str,
                 base_price: float, total_rooms: int):
        """A room type within a hotel."""

class Reservation:
    def __init__(self, reservation_id: str, hotel_id: str,
                 room_type_id: str, guest_name: str,
                 check_in: str, check_out: str, total_price: float):
        """A reservation."""

class HotelReservationSystem:
    def __init__(self):
        """Initialize the system."""

    def add_hotel(self, hotel: Hotel) -> None:
        """Add a hotel."""

    def add_room_type(self, room_type: RoomType) -> None:
        """Add a room type to a hotel."""

    def search(self, check_in: str, check_out: str,
               city: str = None, room_type: str = None,
               max_price: float = None) -> list[dict]:
        """Search available rooms. Returns list of
        {hotel, room_type, available_rooms, price_per_night}."""

    def reserve(self, hotel_id: str, room_type_id: str,
                guest_name: str, check_in: str, check_out: str,
                idempotency_key: str = None) -> Reservation:
        """Book a room. Raises AvailabilityError if no rooms available.
        Raises ConcurrencyError if version conflict."""

    def cancel(self, reservation_id: str, cancel_time: str = None) -> dict:
        """Cancel a reservation. Returns {refund_amount, status}."""

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        """Look up a reservation."""

    def get_occupancy(self, hotel_id: str, room_type_id: str,
                      date: str) -> dict:
        """Return {total_rooms, booked_rooms, available_rooms, occupancy_pct}."""

    def set_seasonal_pricing(self, hotel_id: str, room_type_id: str,
                             start_date: str, end_date: str,
                             multiplier: float) -> None:
        """Set seasonal pricing multiplier for a date range."""

Example Usage
-------------
    system = HotelReservationSystem()
    system.add_hotel(Hotel("h1", "Grand Hotel", "NYC"))
    system.add_room_type(RoomType("std", "h1", "Standard", 100.0, 5))

    # Search
    results = system.search("2024-03-15", "2024-03-17", city="NYC")
    assert len(results) == 1
    assert results[0]["available_rooms"] == 5

    # Reserve
    res = system.reserve("h1", "std", "Alice", "2024-03-15", "2024-03-17")
    assert res.total_price == 200.0  # 2 nights * $100

    # Availability decreased
    occ = system.get_occupancy("h1", "std", "2024-03-15")
    assert occ["available_rooms"] == 4

    # Cancel
    result = system.cancel(res.reservation_id)
    assert result["refund_amount"] == 200.0

    # Idempotency
    r1 = system.reserve("h1", "std", "Bob", "2024-03-20", "2024-03-21",
                         idempotency_key="req-123")
    r2 = system.reserve("h1", "std", "Bob", "2024-03-20", "2024-03-21",
                         idempotency_key="req-123")
    assert r1.reservation_id == r2.reservation_id  # same reservation

Constraints
-----------
- Dates are strings in YYYY-MM-DD format.
- Inventory is tracked per room type per date.
- Optimistic concurrency must prevent double-booking.
- Handle up to 1,000 hotels, 10 room types each.
- Target: 200-400 lines of Python.

Testing Requirements
--------------------
1. Search returns available rooms correctly.
2. Reservation decreases availability.
3. Double-booking is prevented (book all rooms, next fails).
4. Cancellation restores availability.
5. Seasonal pricing affects search results.
6. Dynamic pricing based on occupancy.
7. Idempotent reservations return same result.
8. Reservation status transitions work.
9. Multi-date booking checks all dates.
10. Concurrent booking simulation (optimistic locking).
11. Cancellation refund policies.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `planner/plan.md`. 

**Summary:** In-memory optimistic locking using per-date inventory counters with version numbers. Each `(hotel, room_type, date)` tracks `{booked, version}`. Reservations atomically check-and-increment across all nights in the range, failing on version mismatch. Pricing layers base price with seasonal multipliers and occupancy-based dynamic pricing. Cancellation refund tiers based on timing relative to check-in. Idempotency via key-to-reservation-ID map. Confidence: **HIGH**.

[Committed changes to planner branch]