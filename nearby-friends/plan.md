# Plan (Iteration 1)

Task: Nearby Friends
===============
SDI Vol 2 Reference: Chapter 2 - Nearby Friends

Overview
--------
Build a real-time nearby friends system where users share their location and
can see which friends are nearby. Users publish location updates, and the
system matches friends within a configurable distance threshold. This combines
pub/sub messaging with geospatial indexing — similar to features in Facebook
Messenger, Snapchat, and Find My Friends.

Requirements
------------
1. User registration with a friends list (social graph).
2. Location updates: users publish their current (lat, lon) with a timestamp.
3. Nearby friend detection: given a user, find all friends within a distance
   threshold (default 5 km) who have shared their location recently.
4. Location sharing toggle: users can enable/disable sharing.
5. Location expiry: locations older than a TTL (default 10 minutes) are
   considered stale and excluded from results.
6. Pub/sub model: when a user updates their location, notify nearby friends
   via subscription callbacks.
7. Location history: store the last N location updates per user.
8. Distance calculation using Haversine formula.
9. Efficient spatial lookup using a grid-based index (geohash prefix buckets).

Interface
---------
class User:
    def __init__(self, user_id: str, name: str):
        """A user in the system."""

class LocationUpdate:
    def __init__(self, user_id: str, lat: float, lon: float, timestamp: float):
        """A location update from a user."""

class NearbyFriendsService:
    def __init__(self, distance_threshold_km: float = 5.0,
                 location_ttl_seconds: float = 600):
        """Initialize the nearby friends service."""

    def add_user(self, user: User) -> None:
        """Register a user."""

    def add_friendship(self, user_id1: str, user_id2: str) -> None:
        """Create a bidirectional friendship."""

    def remove_friendship(self, user_id1: str, user_id2: str) -> None:
        """Remove a friendship."""

    def update_location(self, user_id: str, lat: float, lon: float,
                        timestamp: float = None) -> list[str]:
        """Update a user's location. Returns list of nearby friend IDs
        that were notified."""

    def get_nearby_friends(self, user_id: str,
                           current_time: float = None) -> list[dict]:
        """Get all friends within distance threshold with fresh locations.
        Returns list of {user_id, name, lat, lon, distance_km, last_update}."""

    def set_sharing(self, user_id: str, enabled: bool) -> None:
        """Enable or disable location sharing for a user."""

    def subscribe(self, user_id: str, callback: callable) -> None:
        """Subscribe to nearby friend notifications."""

    def get_location_history(self, user_id: str, limit: int = 10) -> list[LocationUpdate]:
        """Get recent location history for a user."""

    def get_friends(self, user_id: str) -> list[str]:
        """Get list of friend IDs."""

Example Usage
-------------
    service = NearbyFriendsService(distance_threshold_km=5.0)

    service.add_user(User("alice", "Alice"))
    service.add_user(User("bob", "Bob"))
    service.add_user(User("charlie", "Charlie"))

    service.add_friendship("alice", "bob")
    service.add_friendship("alice", "charlie")

    # Alice and Bob are nearby
    service.update_location("alice", 37.7749, -122.4194, timestamp=1000)
    service.update_location("bob", 37.7760, -122.4180, timestamp=1001)

    # Charlie is far away
    service.update_location("charlie", 40.7128, -74.0060, timestamp=1002)

    friends = service.get_nearby_friends("alice", current_time=1003)
    assert len(friends) == 1
    assert friends[0]["user_id"] == "bob"
    assert friends[0]["distance_km"] < 5.0

    # Disable sharing
    service.set_sharing("bob", False)
    friends = service.get_nearby_friends("alice", current_time=1004)
    assert len(friends) == 0

    # Location expiry
    friends = service.get_nearby_friends("alice", current_time=2000)
    assert len(friends) == 0  # all locations expired

Constraints
-----------
- Distance threshold: 0.1 to 100 km.
- Location TTL: configurable, default 600 seconds.
- Location history: last 100 updates per user.
- Handle up to 10,000 users efficiently.
- Target: 150-300 lines of Python.

Testing Requirements
--------------------
1. Nearby friends within threshold are returned.
2. Friends beyond threshold are excluded.
3. Non-friends are excluded even if nearby.
4. Location sharing toggle works.
5. Expired locations are excluded.
6. Friendship is bidirectional.
7. Location update notifications via subscription.
8. Location history is maintained.
9. Removing friendship excludes from results.
10. Multiple nearby friends returned sorted by distance.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `planner/PLAN.md`. 

**Summary:** Single-module Python with a grid-based spatial index (lat/lon cells ~5km wide, check 9 neighboring cells for lookups), Haversine distance, adjacency-set social graph, deque-based location history, and callback-based pub/sub. Straightforward implementation — all decisions are standard for this problem class. High confidence.

[Committed changes to planner branch]