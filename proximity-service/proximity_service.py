"""Proximity service with geohash and quadtree spatial indexes."""

import math
from collections import defaultdict

BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
_DECODE = {c: i for i, c in enumerate(BASE32)}


class POI:
    """A point of interest."""
    def __init__(self, id: str, name: str, lat: float, lon: float, category: str = ""):
        self.id = id
        self.name = name
        self.lat = lat
        self.lon = lon
        self.category = category

    def __repr__(self):
        return f"POI({self.id!r}, {self.name!r}, {self.lat}, {self.lon})"


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class GeohashIndex:
    """Geohash-based spatial index."""

    # Radius (km) -> precision mapping
    _PRECISION_TABLE = [
        (5000, 1), (1250, 2), (156, 3), (39, 4),
        (5, 5), (1.2, 6), (0.15, 7), (0.038, 8),
    ]

    def __init__(self, precision: int = 6):
        self.precision = precision
        self._pois = {}  # id -> POI
        self._index = defaultdict(dict)  # geohash -> {id: POI}

    def add(self, poi: POI) -> None:
        """Add a POI to the index."""
        gh = self.encode(poi.lat, poi.lon, self.precision)
        self._pois[poi.id] = (poi, gh)
        self._index[gh][poi.id] = poi

    def remove(self, poi_id: str) -> bool:
        """Remove a POI by ID."""
        if poi_id not in self._pois:
            return False
        poi, gh = self._pois.pop(poi_id)
        del self._index[gh][poi_id]
        if not self._index[gh]:
            del self._index[gh]
        return True

    def nearby(self, lat: float, lon: float, radius_km: float, limit: int = 20) -> list:
        """Find POIs within radius_km, sorted by distance."""
        precision = min(self._precision_for_radius(radius_km), self.precision)
        center_gh = self.encode(lat, lon, precision)
        cells = [center_gh] + self.neighbors(center_gh)
        candidates = []
        for cell in cells:
            # Collect all POIs whose geohash starts with this cell prefix
            for gh, pois in self._index.items():
                if gh[:precision] == cell:
                    candidates.extend(pois.values())
        # Filter by exact distance and sort
        results = []
        for poi in candidates:
            d = haversine(lat, lon, poi.lat, poi.lon)
            if d <= radius_km:
                results.append((d, poi))
        results.sort(key=lambda x: x[0])
        return [poi for _, poi in results[:limit]]

    @classmethod
    def _precision_for_radius(cls, radius_km: float) -> int:
        for threshold, prec in cls._PRECISION_TABLE:
            if radius_km > threshold:
                return prec
        return 8

    @staticmethod
    def encode(lat: float, lon: float, precision: int = 6) -> str:
        """Encode coordinates to a geohash string."""
        lat_range = [-90.0, 90.0]
        lon_range = [-180.0, 180.0]
        bits = 0
        bit_count = 0
        is_lon = True
        result = []
        while len(result) < precision:
            if is_lon:
                mid = (lon_range[0] + lon_range[1]) / 2
                if lon >= mid:
                    bits = bits * 2 + 1
                    lon_range[0] = mid
                else:
                    bits = bits * 2
                    lon_range[1] = mid
            else:
                mid = (lat_range[0] + lat_range[1]) / 2
                if lat >= mid:
                    bits = bits * 2 + 1
                    lat_range[0] = mid
                else:
                    bits = bits * 2
                    lat_range[1] = mid
            is_lon = not is_lon
            bit_count += 1
            if bit_count == 5:
                result.append(BASE32[bits])
                bits = 0
                bit_count = 0
        return "".join(result)

    @staticmethod
    def decode(geohash: str):
        """Decode geohash to (center_lat, center_lon, lat_err, lon_err)."""
        lat_range = [-90.0, 90.0]
        lon_range = [-180.0, 180.0]
        is_lon = True
        for ch in geohash:
            val = _DECODE[ch]
            for bit in range(4, -1, -1):
                b = (val >> bit) & 1
                if is_lon:
                    mid = (lon_range[0] + lon_range[1]) / 2
                    if b:
                        lon_range[0] = mid
                    else:
                        lon_range[1] = mid
                else:
                    mid = (lat_range[0] + lat_range[1]) / 2
                    if b:
                        lat_range[0] = mid
                    else:
                        lat_range[1] = mid
                is_lon = not is_lon
        lat = (lat_range[0] + lat_range[1]) / 2
        lon = (lon_range[0] + lon_range[1]) / 2
        lat_err = (lat_range[1] - lat_range[0]) / 2
        lon_err = (lon_range[1] - lon_range[0]) / 2
        return (lat, lon, lat_err, lon_err)

    @staticmethod
    def neighbors(geohash: str) -> list:
        """Return the 8 neighboring geohash cells."""
        lat, lon, lat_err, lon_err = GeohashIndex.decode(geohash)
        prec = len(geohash)
        dlat = lat_err * 2
        dlon = lon_err * 2
        result = []
        for dy, dx in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
            nlat = lat + dy * dlat
            nlon = lon + dx * dlon
            # Clamp latitude
            nlat = max(-90.0, min(90.0, nlat))
            # Wrap longitude
            if nlon > 180.0:
                nlon -= 360.0
            elif nlon < -180.0:
                nlon += 360.0
            result.append(GeohashIndex.encode(nlat, nlon, prec))
        return result


class _QuadNode:
    """Internal node for quadtree."""
    __slots__ = ('bounds', 'points', 'children', 'max_points', 'depth', 'max_depth')

    def __init__(self, bounds, max_points, depth, max_depth):
        self.bounds = bounds  # (min_lat, min_lon, max_lat, max_lon)
        self.points = []
        self.children = None
        self.max_points = max_points
        self.depth = depth
        self.max_depth = max_depth

    def _subdivide(self):
        min_lat, min_lon, max_lat, max_lon = self.bounds
        mid_lat = (min_lat + max_lat) / 2
        mid_lon = (min_lon + max_lon) / 2
        d = self.depth + 1
        self.children = [
            _QuadNode((mid_lat, min_lon, max_lat, mid_lon), self.max_points, d, self.max_depth),  # NW
            _QuadNode((mid_lat, mid_lon, max_lat, max_lon), self.max_points, d, self.max_depth),  # NE
            _QuadNode((min_lat, min_lon, mid_lat, mid_lon), self.max_points, d, self.max_depth),  # SW
            _QuadNode((min_lat, mid_lon, mid_lat, max_lon), self.max_points, d, self.max_depth),  # SE
        ]
        # Redistribute points
        for poi in self.points:
            for child in self.children:
                if child._contains(poi.lat, poi.lon):
                    child.insert(poi)
                    break
        self.points = []

    def _contains(self, lat, lon):
        min_lat, min_lon, max_lat, max_lon = self.bounds
        return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon

    def _intersects(self, min_lat, min_lon, max_lat, max_lon):
        return not (self.bounds[2] < min_lat or self.bounds[0] > max_lat or
                    self.bounds[3] < min_lon or self.bounds[1] > max_lon)

    def insert(self, poi):
        if not self._contains(poi.lat, poi.lon):
            return False
        if self.children is None:
            self.points.append(poi)
            if len(self.points) > self.max_points and self.depth < self.max_depth:
                self._subdivide()
            return True
        for child in self.children:
            if child.insert(poi):
                return True
        return False

    def query_bbox(self, min_lat, min_lon, max_lat, max_lon, results):
        if not self._intersects(min_lat, min_lon, max_lat, max_lon):
            return
        if self.children is None:
            for poi in self.points:
                if min_lat <= poi.lat <= max_lat and min_lon <= poi.lon <= max_lon:
                    results.append(poi)
        else:
            for child in self.children:
                child.query_bbox(min_lat, min_lon, max_lat, max_lon, results)

    def count(self):
        if self.children is None:
            return len(self.points)
        return sum(c.count() for c in self.children)


class Quadtree:
    """Quadtree spatial index."""

    def __init__(self, bounds: tuple = (-90, -180, 90, 180), max_points: int = 4, max_depth: int = 20):
        self._root = _QuadNode(bounds, max_points, 0, max_depth)

    def insert(self, poi: POI) -> bool:
        """Insert a POI into the quadtree."""
        return self._root.insert(poi)

    def query_range(self, lat: float, lon: float, radius_km: float) -> list:
        """Find all POIs within radius_km, sorted by distance."""
        # Approximate bounding box from radius
        dlat = radius_km / 111.0
        dlon = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.001))
        candidates = self.query_bbox(lat - dlat, lon - dlon, lat + dlat, lon + dlon)
        results = []
        for poi in candidates:
            d = haversine(lat, lon, poi.lat, poi.lon)
            if d <= radius_km:
                results.append((d, poi))
        results.sort(key=lambda x: x[0])
        return [poi for _, poi in results]

    def query_bbox(self, min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> list:
        """Find all POIs within a bounding box."""
        results = []
        self._root.query_bbox(min_lat, min_lon, max_lat, max_lon, results)
        return results

    @property
    def size(self) -> int:
        return self._root.count()
