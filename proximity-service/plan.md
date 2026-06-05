# Plan (Iteration 1)

Task: Proximity Service
==================
SDI Vol 2 Reference: Chapter 1 - Proximity Service

Overview
--------
Build a proximity service that finds nearby businesses or points of interest
(POIs) within a given radius of a location. The system uses geohashing to
convert 2D coordinates into 1D string prefixes for efficient spatial queries,
and a quadtree as an alternative spatial index. This is the core algorithm
behind services like Yelp's nearby search, Google Places, and Foursquare.

Requirements
------------
1. Geohash encoding: convert (latitude, longitude) to a geohash string of
   configurable precision (1-12 characters). Use base32 encoding.
2. Geohash decoding: convert a geohash string back to a bounding box
   (min_lat, max_lat, min_lon, max_lon) and center point.
3. Neighbor computation: given a geohash, find all 8 neighboring geohash
   cells at the same precision level.
4. Proximity search via geohash: given a location and radius, determine
   the appropriate geohash precision, query the geohash prefix and its
   neighbors, then filter results by exact distance.
5. Quadtree spatial index: build a quadtree that recursively subdivides
   space. Each leaf node holds up to a max number of POIs. Internal nodes
   have 4 children (NW, NE, SW, SE).
6. Quadtree range query: find all POIs within a bounding box or radius.
7. POI management: add, remove, and update POIs with id, name, lat, lon,
   and category.
8. Distance calculation: Haversine formula for great-circle distance.
9. Compare both indexing strategies on the same dataset.

Interface
---------
class POI:
    def __init__(self, id: str, name: str, lat: float, lon: float,
                 category: str = ""):
        """A point of interest."""

class GeohashIndex:
    def __init__(self, precision: int = 6):
        """Create a geohash-based spatial index."""

    def add(self, poi: POI) -> None:
        """Add a POI to the index."""

    def remove(self, poi_id: str) -> bool:
        """Remove a POI by ID."""

    def nearby(self, lat: float, lon: float, radius_km: float,
               limit: int = 20) -> list[POI]:
        """Find POIs within radius_km of the given location."""

    @staticmethod
    def encode(lat: float, lon: float, precision: int = 6) -> str:
        """Encode coordinates to a geohash string."""

    @staticmethod
    def decode(geohash: str) -> tuple[float, float, float, float]:
        """Decode geohash to (center_lat, center_lon, lat_err, lon_err)."""

    @staticmethod
    def neighbors(geohash: str) -> list[str]:
        """Return the 8 neighboring geohash cells."""

class Quadtree:
    def __init__(self, bounds: tuple[float, float, float, float],
                 max_points: int = 4, max_depth: int = 20):
        """Create a quadtree for the given bounds (min_lat, min_lon, max_lat, max_lon)."""

    def insert(self, poi: POI) -> bool:
        """Insert a POI into the quadtree."""

    def query_range(self, lat: float, lon: float,
                    radius_km: float) -> list[POI]:
        """Find all POIs within radius_km."""

    def query_bbox(self, min_lat: float, min_lon: float,
                   max_lat: float, max_lon: float) -> list[POI]:
        """Find all POIs within a bounding box."""

    @property
    def size(self) -> int:
        """Total number of POIs in the tree."""

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in km between two points."""

Example Usage
-------------
    # Geohash
    gh = GeohashIndex.encode(37.7749, -122.4194, precision=6)
    assert len(gh) == 6
    center = GeohashIndex.decode(gh)

    neighbors = GeohashIndex.neighbors(gh)
    assert len(neighbors) == 8

    # Index and search
    index = GeohashIndex(precision=6)
    index.add(POI("1", "Coffee Shop", 37.7750, -122.4180, "cafe"))
    index.add(POI("2", "Bookstore", 37.7760, -122.4200, "retail"))
    index.add(POI("3", "Far Away Place", 38.0, -123.0, "other"))

    results = index.nearby(37.7749, -122.4194, radius_km=1.0)
    assert len(results) == 2  # only nearby POIs

    # Quadtree
    qt = Quadtree(bounds=(37.0, -123.0, 38.0, -122.0))
    qt.insert(POI("1", "Coffee Shop", 37.7750, -122.4180, "cafe"))
    qt.insert(POI("2", "Bookstore", 37.7760, -122.4200, "retail"))
    results = qt.query_range(37.7749, -122.4194, radius_km=1.0)
    assert len(results) == 2

    # Haversine
    dist = haversine(37.7749, -122.4194, 37.7760, -122.4200)
    assert dist < 1.0  # less than 1 km

Constraints
-----------
- Latitude range: [-90, 90], Longitude range: [-180, 180].
- Geohash precision 1-12 characters.
- Quadtree max depth: 20 levels.
- Handle up to 100,000 POIs efficiently.
- Nearby queries should return results sorted by distance.
- Target: 200-400 lines of Python.

Testing Requirements
--------------------
1. Geohash encode/decode roundtrip accuracy.
2. Geohash neighbors: verify all 8 neighbors are adjacent.
3. Nearby search returns only POIs within radius.
4. Nearby search excludes POIs outside radius.
5. Quadtree insert and range query correctness.
6. Quadtree handles points on boundaries.
7. Haversine distance accuracy against known values.
8. Large dataset: 10,000 POIs, verify search performance.
9. Edge cases: poles, antimeridian, zero radius.
10. Remove POI and verify it's excluded from results.
11. Compare geohash and quadtree results on same dataset.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `planner/PLAN.md`. 

Summary: Single-file Python module (~300 lines) with `POI`, `GeohashIndex`, `Quadtree`, and `haversine`. Standard geohash base32 with bit-interleaving, neighbor computation via coordinate nudging, quadtree with recursive subdivision, and haversine for distance filtering. No external dependencies. Confidence: **HIGH**.

[Committed changes to planner branch]