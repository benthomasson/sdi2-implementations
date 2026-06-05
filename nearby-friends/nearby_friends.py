"""Nearby Friends service with geospatial indexing and pub/sub notifications."""

import math
import time
from collections import defaultdict, deque


class User:
    def __init__(self, user_id: str, name: str):
        self.user_id = user_id
        self.name = name


class LocationUpdate:
    def __init__(self, user_id: str, lat: float, lon: float, timestamp: float):
        self.user_id = user_id
        self.lat = lat
        self.lon = lon
        self.timestamp = timestamp


def _haversine(lat1, lon1, lat2, lon2):
    """Distance in km between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class NearbyFriendsService:
    def __init__(self, distance_threshold_km: float = 5.0,
                 location_ttl_seconds: float = 600):
        self.distance_threshold_km = distance_threshold_km
        self.location_ttl_seconds = location_ttl_seconds
        # ~0.045 degrees per 5km at equator; scale cell size with threshold
        self._cell_size = (distance_threshold_km / 111.0)

        self._users = {}                    # user_id -> User
        self._friends = defaultdict(set)    # user_id -> set of friend_ids
        self._locations = {}                # user_id -> LocationUpdate (current)
        self._sharing = {}                  # user_id -> bool
        self._history = {}                  # user_id -> deque of LocationUpdate
        self._subscriptions = {}            # user_id -> callback
        self._grid = defaultdict(set)       # (row, col) -> set of user_ids
        self._user_cell = {}                # user_id -> (row, col)

    def _get_cell(self, lat, lon):
        return (math.floor(lat / self._cell_size),
                math.floor(lon / self._cell_size))

    def _neighbor_cells(self, cell):
        r, c = cell
        return [(r + dr, c + dc)
                for dr in (-1, 0, 1) for dc in (-1, 0, 1)]

    def add_user(self, user):
        self._users[user.user_id] = user
        self._sharing[user.user_id] = True
        self._history[user.user_id] = deque(maxlen=100)

    def add_friendship(self, user_id1, user_id2):
        self._friends[user_id1].add(user_id2)
        self._friends[user_id2].add(user_id1)

    def remove_friendship(self, user_id1, user_id2):
        self._friends[user_id1].discard(user_id2)
        self._friends[user_id2].discard(user_id1)

    def set_sharing(self, user_id, enabled):
        self._sharing[user_id] = enabled

    def subscribe(self, user_id, callback):
        self._subscriptions[user_id] = callback

    def get_friends(self, user_id):
        return list(self._friends[user_id])

    def get_location_history(self, user_id, limit=10):
        return list(self._history[user_id])[-limit:]

    def update_location(self, user_id, lat, lon, timestamp=None):
        """Update user's location. Returns list of nearby friend IDs notified."""
        if timestamp is None:
            timestamp = time.time()

        loc = LocationUpdate(user_id, lat, lon, timestamp)
        self._locations[user_id] = loc
        self._history[user_id].append(loc)

        # Update grid index
        new_cell = self._get_cell(lat, lon)
        if user_id in self._user_cell:
            old_cell = self._user_cell[user_id]
            if old_cell != new_cell:
                self._grid[old_cell].discard(user_id)
                self._grid[new_cell].add(user_id)
                self._user_cell[user_id] = new_cell
        else:
            self._grid[new_cell].add(user_id)
            self._user_cell[user_id] = new_cell

        # Notify nearby friends
        notified = []
        if not self._sharing.get(user_id, True):
            return notified

        for friend_id in self._friends.get(user_id, set()):
            if not self._sharing.get(friend_id, True):
                continue
            friend_loc = self._locations.get(friend_id)
            if friend_loc is None:
                continue
            if timestamp - friend_loc.timestamp > self.location_ttl_seconds:
                continue
            dist = _haversine(lat, lon, friend_loc.lat, friend_loc.lon)
            if dist <= self.distance_threshold_km:
                notified.append(friend_id)
                if friend_id in self._subscriptions:
                    self._subscriptions[friend_id](user_id, dist)

        return notified

    def get_nearby_friends(self, user_id, current_time=None):
        """Get friends within threshold with fresh locations."""
        if current_time is None:
            current_time = time.time()

        user_loc = self._locations.get(user_id)
        if user_loc is None:
            return []

        if current_time - user_loc.timestamp > self.location_ttl_seconds:
            return []

        if not self._sharing.get(user_id, True):
            return []

        friend_ids = self._friends.get(user_id, set())
        if not friend_ids:
            return []

        # Use grid for spatial filtering
        user_cell = self._user_cell.get(user_id)
        if user_cell is None:
            return []

        candidate_ids = set()
        for cell in self._neighbor_cells(user_cell):
            candidate_ids.update(self._grid.get(cell, set()))

        results = []
        for fid in candidate_ids & friend_ids:
            if not self._sharing.get(fid, True):
                continue
            floc = self._locations.get(fid)
            if floc is None:
                continue
            if current_time - floc.timestamp > self.location_ttl_seconds:
                continue
            dist = _haversine(user_loc.lat, user_loc.lon, floc.lat, floc.lon)
            if dist <= self.distance_threshold_km:
                results.append({
                    "user_id": fid,
                    "name": self._users[fid].name,
                    "lat": floc.lat,
                    "lon": floc.lon,
                    "distance_km": dist,
                    "last_update": floc.timestamp,
                })

        results.sort(key=lambda r: r["distance_km"])
        return results
