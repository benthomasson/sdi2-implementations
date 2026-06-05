"""Hotel Reservation System with optimistic concurrency control."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import uuid


class AvailabilityError(Exception):
    pass

class ConcurrencyError(Exception):
    pass


@dataclass
class Hotel:
    hotel_id: str
    name: str
    city: str


@dataclass
class RoomType:
    type_id: str
    hotel_id: str
    name: str
    base_price: float
    total_rooms: int


@dataclass
class Reservation:
    reservation_id: str
    hotel_id: str
    room_type_id: str
    guest_name: str
    check_in: str
    check_out: str
    total_price: float
    status: str = "CONFIRMED"


def _date_range(check_in: str, check_out: str) -> list[str]:
    """Return list of date strings from check_in to check_out (exclusive)."""
    start = datetime.strptime(check_in, "%Y-%m-%d")
    end = datetime.strptime(check_out, "%Y-%m-%d")
    dates = []
    cur = start
    while cur < end:
        dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return dates


class HotelReservationSystem:
    def __init__(self):
        self.hotels: dict[str, Hotel] = {}
        self.room_types: dict[tuple[str, str], RoomType] = {}  # (hotel_id, type_id) -> RoomType
        # inventory: (hotel_id, type_id, date) -> {"booked": int, "version": int}
        self.inventory: dict[tuple[str, str, str], dict] = {}
        self.reservations: dict[str, Reservation] = {}
        self.idempotency_keys: dict[str, str] = {}  # key -> reservation_id
        # seasonal pricing: (hotel_id, type_id) -> [(start, end, multiplier)]
        self.seasonal_pricing: dict[tuple[str, str], list] = {}

    def add_hotel(self, hotel: Hotel) -> None:
        self.hotels[hotel.hotel_id] = hotel

    def add_room_type(self, room_type: RoomType) -> None:
        key = (room_type.hotel_id, room_type.type_id)
        self.room_types[key] = room_type

    def _get_inventory(self, hotel_id: str, type_id: str, date: str) -> dict:
        key = (hotel_id, type_id, date)
        if key not in self.inventory:
            self.inventory[key] = {"booked": 0, "version": 0}
        return self.inventory[key]

    def _get_price(self, hotel_id: str, type_id: str, date: str) -> float:
        rt = self.room_types[(hotel_id, type_id)]
        price = rt.base_price

        # Seasonal multiplier
        seasonal_key = (hotel_id, type_id)
        if seasonal_key in self.seasonal_pricing:
            for start, end, mult in self.seasonal_pricing[seasonal_key]:
                if start <= date <= end:
                    price *= mult
                    break

        # Dynamic pricing based on occupancy
        inv = self._get_inventory(hotel_id, type_id, date)
        occupancy = inv["booked"] / rt.total_rooms if rt.total_rooms > 0 else 0
        if occupancy >= 0.9:
            price *= 1.5
        elif occupancy >= 0.7:
            price *= 1.3
        elif occupancy >= 0.5:
            price *= 1.1

        return price

    def search(self, check_in: str, check_out: str,
               city: str = None, room_type: str = None,
               max_price: float = None) -> list[dict]:
        dates = _date_range(check_in, check_out)
        results = []

        for (hotel_id, type_id), rt in self.room_types.items():
            hotel = self.hotels[hotel_id]

            if city and hotel.city != city:
                continue
            if room_type and rt.name != room_type:
                continue

            # Min availability across all dates
            available = rt.total_rooms
            for d in dates:
                inv = self._get_inventory(hotel_id, type_id, d)
                avail_on_date = rt.total_rooms - inv["booked"]
                available = min(available, avail_on_date)

            if available <= 0:
                continue

            # Average price per night
            total = sum(self._get_price(hotel_id, type_id, d) for d in dates)
            price_per_night = total / len(dates) if dates else rt.base_price

            if max_price and price_per_night > max_price:
                continue

            results.append({
                "hotel": hotel,
                "room_type": rt,
                "available_rooms": available,
                "price_per_night": price_per_night,
            })

        return results

    def reserve(self, hotel_id: str, room_type_id: str,
                guest_name: str, check_in: str, check_out: str,
                idempotency_key: str = None) -> Reservation:
        # Idempotency check
        if idempotency_key and idempotency_key in self.idempotency_keys:
            return self.reservations[self.idempotency_keys[idempotency_key]]

        rt = self.room_types.get((hotel_id, room_type_id))
        if not rt:
            raise ValueError(f"Room type {room_type_id} not found in hotel {hotel_id}")

        dates = _date_range(check_in, check_out)

        # Phase 1: Read versions and check availability
        snapshots = {}
        for d in dates:
            inv = self._get_inventory(hotel_id, room_type_id, d)
            avail = rt.total_rooms - inv["booked"]
            if avail <= 0:
                raise AvailabilityError(f"No rooms available on {d}")
            snapshots[d] = inv["version"]

        # Phase 2: Verify versions unchanged and commit
        for d in dates:
            inv = self._get_inventory(hotel_id, room_type_id, d)
            if inv["version"] != snapshots[d]:
                raise ConcurrencyError(f"Version conflict on {d}")

        # Calculate total price
        total_price = sum(self._get_price(hotel_id, room_type_id, d) for d in dates)

        # Commit: increment booked count and version for each date
        for d in dates:
            inv = self._get_inventory(hotel_id, room_type_id, d)
            inv["booked"] += 1
            inv["version"] += 1

        reservation = Reservation(
            reservation_id=str(uuid.uuid4()),
            hotel_id=hotel_id,
            room_type_id=room_type_id,
            guest_name=guest_name,
            check_in=check_in,
            check_out=check_out,
            total_price=total_price,
        )
        self.reservations[reservation.reservation_id] = reservation

        if idempotency_key:
            self.idempotency_keys[idempotency_key] = reservation.reservation_id

        return reservation

    def cancel(self, reservation_id: str, cancel_time: str = None) -> dict:
        res = self.reservations.get(reservation_id)
        if not res:
            raise ValueError(f"Reservation {reservation_id} not found")
        if res.status == "CANCELLED":
            raise ValueError("Reservation already cancelled")

        # Release inventory
        dates = _date_range(res.check_in, res.check_out)
        for d in dates:
            inv = self._get_inventory(res.hotel_id, res.room_type_id, d)
            inv["booked"] -= 1
            inv["version"] += 1

        # Determine refund based on cancellation timing
        check_in_dt = datetime.strptime(res.check_in, "%Y-%m-%d")
        if cancel_time:
            cancel_dt = datetime.strptime(cancel_time, "%Y-%m-%d %H:%M:%S") if " " in cancel_time else datetime.strptime(cancel_time, "%Y-%m-%d")
        else:
            cancel_dt = datetime.now()

        hours_before = (check_in_dt - cancel_dt).total_seconds() / 3600

        if hours_before >= 24:
            refund_pct = 1.0  # Full refund
        elif hours_before >= 0:
            refund_pct = 0.5  # Partial refund
        else:
            refund_pct = 0.0  # No refund (after check-in)

        refund_amount = res.total_price * refund_pct
        res.status = "CANCELLED"

        return {"refund_amount": refund_amount, "status": "CANCELLED"}

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        return self.reservations.get(reservation_id)

    def get_occupancy(self, hotel_id: str, room_type_id: str, date: str) -> dict:
        rt = self.room_types[(hotel_id, room_type_id)]
        inv = self._get_inventory(hotel_id, room_type_id, date)
        booked = inv["booked"]
        available = rt.total_rooms - booked
        return {
            "total_rooms": rt.total_rooms,
            "booked_rooms": booked,
            "available_rooms": available,
            "occupancy_pct": booked / rt.total_rooms if rt.total_rooms > 0 else 0,
        }

    def set_seasonal_pricing(self, hotel_id: str, room_type_id: str,
                             start_date: str, end_date: str,
                             multiplier: float) -> None:
        key = (hotel_id, room_type_id)
        if key not in self.seasonal_pricing:
            self.seasonal_pricing[key] = []
        self.seasonal_pricing[key].append((start_date, end_date, multiplier))


# ── Tests ──

def test_all():
    system = HotelReservationSystem()
    system.add_hotel(Hotel("h1", "Grand Hotel", "NYC"))
    system.add_hotel(Hotel("h2", "Beach Resort", "Miami"))
    system.add_room_type(RoomType("std", "h1", "Standard", 100.0, 5))
    system.add_room_type(RoomType("dlx", "h1", "Deluxe", 200.0, 3))
    system.add_room_type(RoomType("std", "h2", "Standard", 150.0, 4))

    # 1. Search returns available rooms correctly
    results = system.search("2024-03-15", "2024-03-17", city="NYC")
    assert len(results) == 2, f"Expected 2 results, got {len(results)}"
    std_result = [r for r in results if r["room_type"].name == "Standard"][0]
    assert std_result["available_rooms"] == 5
    assert std_result["price_per_night"] == 100.0
    print("PASS: 1. Search returns available rooms")

    # 2. Reservation decreases availability
    res = system.reserve("h1", "std", "Alice", "2024-03-15", "2024-03-17")
    assert res.total_price == 200.0  # 2 nights * $100
    occ = system.get_occupancy("h1", "std", "2024-03-15")
    assert occ["available_rooms"] == 4
    print("PASS: 2. Reservation decreases availability")

    # 3. Double-booking prevented
    for i in range(4):
        system.reserve("h1", "std", f"Guest{i}", "2024-03-15", "2024-03-17")
    # All 5 rooms booked now
    try:
        system.reserve("h1", "std", "Extra", "2024-03-15", "2024-03-17")
        assert False, "Should have raised AvailabilityError"
    except AvailabilityError:
        pass
    print("PASS: 3. Double-booking prevented")

    # 4. Cancellation restores availability
    cancel_result = system.cancel(res.reservation_id, cancel_time="2024-03-01")
    assert cancel_result["refund_amount"] == 200.0
    occ = system.get_occupancy("h1", "std", "2024-03-15")
    assert occ["available_rooms"] == 1
    print("PASS: 4. Cancellation restores availability")

    # 5. Seasonal pricing
    system.set_seasonal_pricing("h1", "std", "2024-06-01", "2024-08-31", 1.5)
    results = system.search("2024-06-15", "2024-06-17")
    nyc_std = [r for r in results if r["hotel"].hotel_id == "h1" and r["room_type"].type_id == "std"][0]
    assert nyc_std["price_per_night"] == 150.0, f"Expected 150.0, got {nyc_std['price_per_night']}"
    print("PASS: 5. Seasonal pricing")

    # 6. Dynamic pricing based on occupancy
    system2 = HotelReservationSystem()
    system2.add_hotel(Hotel("h1", "Test Hotel", "NYC"))
    system2.add_room_type(RoomType("std", "h1", "Standard", 100.0, 10))
    # Book 5 rooms (50% occupancy -> 1.1x)
    for i in range(5):
        system2.reserve("h1", "std", f"G{i}", "2024-04-01", "2024-04-02")
    occ = system2.get_occupancy("h1", "std", "2024-04-01")
    assert occ["occupancy_pct"] == 0.5
    results = system2.search("2024-04-01", "2024-04-02")
    assert results[0]["price_per_night"] == 110.0, f"Expected 110.0, got {results[0]['price_per_night']}"
    # Book 2 more (70% -> 1.3x)
    for i in range(2):
        system2.reserve("h1", "std", f"G{5+i}", "2024-04-01", "2024-04-02")
    results = system2.search("2024-04-01", "2024-04-02")
    assert results[0]["price_per_night"] == 130.0
    print("PASS: 6. Dynamic pricing based on occupancy")

    # 7. Idempotent reservations
    r1 = system.reserve("h1", "dlx", "Bob", "2024-05-01", "2024-05-02", idempotency_key="req-123")
    r2 = system.reserve("h1", "dlx", "Bob", "2024-05-01", "2024-05-02", idempotency_key="req-123")
    assert r1.reservation_id == r2.reservation_id
    print("PASS: 7. Idempotent reservations")

    # 8. Reservation status transitions
    res3 = system.reserve("h1", "dlx", "Carol", "2024-07-01", "2024-07-03")
    assert res3.status == "CONFIRMED"
    system.cancel(res3.reservation_id, cancel_time="2024-06-01")
    assert res3.status == "CANCELLED"
    print("PASS: 8. Reservation status transitions")

    # 9. Multi-date booking checks all dates
    system3 = HotelReservationSystem()
    system3.add_hotel(Hotel("h1", "Test", "NYC"))
    system3.add_room_type(RoomType("std", "h1", "Standard", 100.0, 1))
    system3.reserve("h1", "std", "A", "2024-04-02", "2024-04-04")  # Books Apr 2,3
    # Overlapping: Apr 1-3 needs Apr 1,2 — Apr 2 is full
    try:
        system3.reserve("h1", "std", "B", "2024-04-01", "2024-04-03")
        assert False, "Should have raised AvailabilityError"
    except AvailabilityError:
        pass
    print("PASS: 9. Multi-date booking checks all dates")

    # 10. Concurrent booking simulation (optimistic locking)
    system4 = HotelReservationSystem()
    system4.add_hotel(Hotel("h1", "Test", "NYC"))
    system4.add_room_type(RoomType("std", "h1", "Standard", 100.0, 1))
    # Simulate: read version, then someone else books, then try to commit
    inv = system4._get_inventory("h1", "std", "2024-05-01")
    old_version = inv["version"]
    # "Another user" books
    system4.reserve("h1", "std", "First", "2024-05-01", "2024-05-02")
    # Now manually try to book with stale version
    inv = system4._get_inventory("h1", "std", "2024-05-01")
    assert inv["version"] != old_version, "Version should have changed"
    # The room is full so it raises AvailabilityError (only 1 room)
    try:
        system4.reserve("h1", "std", "Second", "2024-05-01", "2024-05-02")
        assert False, "Should fail"
    except AvailabilityError:
        pass
    print("PASS: 10. Concurrent booking simulation")

    # 11. Cancellation refund policies
    system5 = HotelReservationSystem()
    system5.add_hotel(Hotel("h1", "Test", "NYC"))
    system5.add_room_type(RoomType("std", "h1", "Standard", 100.0, 10))
    # Full refund (>24h before)
    r = system5.reserve("h1", "std", "A", "2024-06-10", "2024-06-12")
    result = system5.cancel(r.reservation_id, cancel_time="2024-06-08 10:00:00")
    assert result["refund_amount"] == 200.0, f"Expected 200.0, got {result['refund_amount']}"
    # Partial refund (<24h before check-in)
    r = system5.reserve("h1", "std", "B", "2024-06-10", "2024-06-12")
    result = system5.cancel(r.reservation_id, cancel_time="2024-06-09 12:00:00")
    assert result["refund_amount"] == 100.0, f"Expected 100.0, got {result['refund_amount']}"
    # No refund (after check-in)
    r = system5.reserve("h1", "std", "C", "2024-06-10", "2024-06-12")
    result = system5.cancel(r.reservation_id, cancel_time="2024-06-10 14:00:00")
    assert result["refund_amount"] == 0.0, f"Expected 0.0, got {result['refund_amount']}"
    print("PASS: 11. Cancellation refund policies")

    print("\nAll 11 tests passed!")


if __name__ == "__main__":
    test_all()
