"""Tests for the nearby friends service."""

from nearby_friends import User, LocationUpdate, NearbyFriendsService


def make_service():
    svc = NearbyFriendsService(distance_threshold_km=5.0, location_ttl_seconds=600)
    svc.add_user(User("alice", "Alice"))
    svc.add_user(User("bob", "Bob"))
    svc.add_user(User("charlie", "Charlie"))
    svc.add_user(User("dave", "Dave"))
    svc.add_friendship("alice", "bob")
    svc.add_friendship("alice", "charlie")
    svc.add_friendship("alice", "dave")
    return svc


def test_nearby_friends_within_threshold():
    """1. Nearby friends within threshold are returned."""
    svc = make_service()
    svc.update_location("alice", 37.7749, -122.4194, timestamp=1000)
    svc.update_location("bob", 37.7760, -122.4180, timestamp=1001)
    friends = svc.get_nearby_friends("alice", current_time=1002)
    assert len(friends) == 1
    assert friends[0]["user_id"] == "bob"
    assert friends[0]["distance_km"] < 5.0


def test_friends_beyond_threshold_excluded():
    """2. Friends beyond threshold are excluded."""
    svc = make_service()
    svc.update_location("alice", 37.7749, -122.4194, timestamp=1000)
    svc.update_location("charlie", 40.7128, -74.0060, timestamp=1001)
    friends = svc.get_nearby_friends("alice", current_time=1002)
    assert all(f["user_id"] != "charlie" for f in friends)


def test_non_friends_excluded():
    """3. Non-friends are excluded even if nearby."""
    svc = make_service()
    svc.add_user(User("stranger", "Stranger"))
    svc.update_location("alice", 37.7749, -122.4194, timestamp=1000)
    svc.update_location("stranger", 37.7750, -122.4195, timestamp=1001)
    friends = svc.get_nearby_friends("alice", current_time=1002)
    assert all(f["user_id"] != "stranger" for f in friends)


def test_sharing_toggle():
    """4. Location sharing toggle works."""
    svc = make_service()
    svc.update_location("alice", 37.7749, -122.4194, timestamp=1000)
    svc.update_location("bob", 37.7760, -122.4180, timestamp=1001)

    svc.set_sharing("bob", False)
    friends = svc.get_nearby_friends("alice", current_time=1002)
    assert len(friends) == 0

    svc.set_sharing("bob", True)
    friends = svc.get_nearby_friends("alice", current_time=1003)
    assert len(friends) == 1


def test_expired_locations_excluded():
    """5. Expired locations are excluded."""
    svc = make_service()
    svc.update_location("alice", 37.7749, -122.4194, timestamp=1000)
    svc.update_location("bob", 37.7760, -122.4180, timestamp=1001)
    friends = svc.get_nearby_friends("alice", current_time=2000)
    assert len(friends) == 0


def test_bidirectional_friendship():
    """6. Friendship is bidirectional."""
    svc = make_service()
    svc.update_location("alice", 37.7749, -122.4194, timestamp=1000)
    svc.update_location("bob", 37.7760, -122.4180, timestamp=1001)

    friends_a = svc.get_nearby_friends("alice", current_time=1002)
    friends_b = svc.get_nearby_friends("bob", current_time=1002)
    assert any(f["user_id"] == "bob" for f in friends_a)
    assert any(f["user_id"] == "alice" for f in friends_b)


def test_subscription_notifications():
    """7. Location update notifications via subscription."""
    svc = make_service()
    notifications = []
    svc.subscribe("bob", lambda uid, dist: notifications.append((uid, dist)))

    svc.update_location("bob", 37.7760, -122.4180, timestamp=1000)
    svc.update_location("alice", 37.7749, -122.4194, timestamp=1001)

    assert len(notifications) == 1
    assert notifications[0][0] == "alice"
    assert notifications[0][1] < 5.0


def test_location_history():
    """8. Location history is maintained."""
    svc = make_service()
    svc.update_location("alice", 37.7749, -122.4194, timestamp=1000)
    svc.update_location("alice", 37.7750, -122.4195, timestamp=1001)
    svc.update_location("alice", 37.7751, -122.4196, timestamp=1002)

    history = svc.get_location_history("alice", limit=2)
    assert len(history) == 2
    assert history[0].timestamp == 1001
    assert history[1].timestamp == 1002


def test_remove_friendship_excludes():
    """9. Removing friendship excludes from results."""
    svc = make_service()
    svc.update_location("alice", 37.7749, -122.4194, timestamp=1000)
    svc.update_location("bob", 37.7760, -122.4180, timestamp=1001)

    friends = svc.get_nearby_friends("alice", current_time=1002)
    assert any(f["user_id"] == "bob" for f in friends)

    svc.remove_friendship("alice", "bob")
    friends = svc.get_nearby_friends("alice", current_time=1003)
    assert all(f["user_id"] != "bob" for f in friends)


def test_multiple_nearby_sorted_by_distance():
    """10. Multiple nearby friends returned sorted by distance."""
    svc = make_service()
    # Alice at a point, bob closer, dave slightly further
    svc.update_location("alice", 37.7749, -122.4194, timestamp=1000)
    svc.update_location("bob", 37.7755, -122.4190, timestamp=1001)    # closer
    svc.update_location("dave", 37.7780, -122.4160, timestamp=1002)   # further but within 5km

    friends = svc.get_nearby_friends("alice", current_time=1003)
    assert len(friends) >= 2
    assert friends[0]["user_id"] == "bob"
    assert friends[1]["user_id"] == "dave"
    assert friends[0]["distance_km"] <= friends[1]["distance_km"]


def test_example_usage():
    """Verify the example from the task specification."""
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


if __name__ == "__main__":
    test_nearby_friends_within_threshold()
    test_friends_beyond_threshold_excluded()
    test_non_friends_excluded()
    test_sharing_toggle()
    test_expired_locations_excluded()
    test_bidirectional_friendship()
    test_subscription_notifications()
    test_location_history()
    test_remove_friendship_excludes()
    test_multiple_nearby_sorted_by_distance()
    test_example_usage()
    print("All 11 tests passed!")
