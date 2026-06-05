"""QA tests for the nearby friends service — edge cases and validation."""

from nearby_friends import User, LocationUpdate, NearbyFriendsService, _haversine


def test_example_from_spec():
    """Verify the exact example usage from the task specification."""
    service = NearbyFriendsService(distance_threshold_km=5.0)
    service.add_user(User("alice", "Alice"))
    service.add_user(User("bob", "Bob"))
    service.add_user(User("charlie", "Charlie"))
    service.add_friendship("alice", "bob")
    service.add_friendship("alice", "charlie")

    service.update_location("alice", 37.7749, -122.4194, timestamp=1000)
    service.update_location("bob", 37.7760, -122.4180, timestamp=1001)
    service.update_location("charlie", 40.7128, -74.0060, timestamp=1002)

    friends = service.get_nearby_friends("alice", current_time=1003)
    assert len(friends) == 1
    assert friends[0]["user_id"] == "bob"
    assert friends[0]["distance_km"] < 5.0

    service.set_sharing("bob", False)
    friends = service.get_nearby_friends("alice", current_time=1004)
    assert len(friends) == 0

    friends = service.get_nearby_friends("alice", current_time=2000)
    assert len(friends) == 0


def test_haversine_known_distance():
    """Haversine returns correct distance for known points."""
    # NYC to LA is ~3944 km
    dist = _haversine(40.7128, -74.0060, 33.9425, -118.4081)
    assert 3900 < dist < 4000, f"NYC-LA distance should be ~3944km, got {dist}"

    # Same point should be 0
    assert _haversine(0, 0, 0, 0) == 0.0


def test_return_dict_fields():
    """get_nearby_friends returns dicts with all required fields."""
    svc = NearbyFriendsService()
    svc.add_user(User("a", "A"))
    svc.add_user(User("b", "B"))
    svc.add_friendship("a", "b")
    svc.update_location("a", 10.0, 20.0, timestamp=100)
    svc.update_location("b", 10.0, 20.0, timestamp=100)

    friends = svc.get_nearby_friends("a", current_time=100)
    assert len(friends) == 1
    f = friends[0]
    required_keys = {"user_id", "name", "lat", "lon", "distance_km", "last_update"}
    assert set(f.keys()) == required_keys, f"Missing keys: {required_keys - set(f.keys())}"


def test_update_location_returns_notified_ids():
    """update_location returns list of nearby friend IDs that were notified."""
    svc = NearbyFriendsService()
    svc.add_user(User("a", "A"))
    svc.add_user(User("b", "B"))
    svc.add_friendship("a", "b")
    svc.update_location("b", 10.0, 20.0, timestamp=100)

    notified = svc.update_location("a", 10.0, 20.0, timestamp=101)
    assert isinstance(notified, list)
    assert "b" in notified


def test_no_location_returns_empty():
    """User with no location update gets empty nearby list."""
    svc = NearbyFriendsService()
    svc.add_user(User("a", "A"))
    svc.add_user(User("b", "B"))
    svc.add_friendship("a", "b")
    svc.update_location("b", 10.0, 20.0, timestamp=100)

    friends = svc.get_nearby_friends("a", current_time=100)
    assert friends == []


def test_location_history_limit():
    """Location history respects the limit parameter and max capacity."""
    svc = NearbyFriendsService()
    svc.add_user(User("a", "A"))
    for i in range(15):
        svc.update_location("a", 10.0 + i * 0.001, 20.0, timestamp=100 + i)

    history = svc.get_location_history("a", limit=5)
    assert len(history) == 5
    # Should be the last 5
    assert history[0].timestamp == 110
    assert history[4].timestamp == 114

    # Default limit=10
    history = svc.get_location_history("a")
    assert len(history) == 10


def test_sharing_disabled_user_not_notified():
    """A user with sharing disabled should not trigger notifications from update_location."""
    svc = NearbyFriendsService()
    svc.add_user(User("a", "A"))
    svc.add_user(User("b", "B"))
    svc.add_friendship("a", "b")
    svc.update_location("b", 10.0, 20.0, timestamp=100)

    svc.set_sharing("a", False)
    notified = svc.update_location("a", 10.0, 20.0, timestamp=101)
    assert notified == [], "Sharing-disabled user should not notify anyone"


def test_get_friends_list():
    """get_friends returns the correct friend IDs."""
    svc = NearbyFriendsService()
    svc.add_user(User("a", "A"))
    svc.add_user(User("b", "B"))
    svc.add_user(User("c", "C"))
    svc.add_friendship("a", "b")
    svc.add_friendship("a", "c")

    friends = svc.get_friends("a")
    assert set(friends) == {"b", "c"}
    assert "a" not in svc.get_friends("b") or "a" in svc.get_friends("b")
    # Bidirectional check
    assert "a" in svc.get_friends("b")
    assert "a" in svc.get_friends("c")


def test_custom_threshold():
    """Service works with custom distance threshold."""
    svc = NearbyFriendsService(distance_threshold_km=1.0, location_ttl_seconds=600)
    svc.add_user(User("a", "A"))
    svc.add_user(User("b", "B"))
    svc.add_friendship("a", "b")

    # Points ~1.5km apart — should be outside 1km threshold
    svc.update_location("a", 37.7749, -122.4194, timestamp=100)
    svc.update_location("b", 37.7880, -122.4194, timestamp=100)

    friends = svc.get_nearby_friends("a", current_time=100)
    assert len(friends) == 0, "Points ~1.5km apart should be outside 1km threshold"


if __name__ == "__main__":
    tests = [
        test_example_from_spec,
        test_haversine_known_distance,
        test_return_dict_fields,
        test_update_location_returns_notified_ids,
        test_no_location_returns_empty,
        test_location_history_limit,
        test_sharing_disabled_user_not_notified,
        test_get_friends_list,
        test_custom_threshold,
    ]
    for t in tests:
        t()
        print(f"  PASS: {t.__name__}")
    print(f"\nAll {len(tests)} QA tests passed!")
