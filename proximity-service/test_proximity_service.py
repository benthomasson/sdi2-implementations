"""Tests for proximity service."""
import sys, os, time, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'implementer'))

from proximity_service import POI, GeohashIndex, Quadtree, haversine


def test_example_usage():
    """Verify the example from the spec (quadtree + haversine parts)."""
    gh = GeohashIndex.encode(37.7749, -122.4194, precision=6)
    assert len(gh) == 6
    center = GeohashIndex.decode(gh)
    assert len(center) == 4

    neighbors = GeohashIndex.neighbors(gh)
    assert len(neighbors) == 8

    # Quadtree portion of the example
    qt = Quadtree(bounds=(37.0, -123.0, 38.0, -122.0))
    qt.insert(POI("1", "Coffee Shop", 37.7750, -122.4180, "cafe"))
    qt.insert(POI("2", "Bookstore", 37.7760, -122.4200, "retail"))
    results = qt.query_range(37.7749, -122.4194, radius_km=1.0)
    assert len(results) == 2

    dist = haversine(37.7749, -122.4194, 37.7760, -122.4200)
    assert dist < 1.0


def test_geohash_nearby_small_radius():
    """Geohash nearby with small radius finds nearby POIs."""
    index = GeohashIndex(precision=6)
    index.add(POI("1", "Coffee Shop", 37.7750, -122.4180, "cafe"))
    index.add(POI("2", "Bookstore", 37.7760, -122.4200, "retail"))
    index.add(POI("3", "Far Away Place", 38.0, -123.0, "other"))

    results = index.nearby(37.7749, -122.4194, radius_km=1.0)
    assert len(results) == 2


def test_geohash_nearby_large_radius_works():
    """With a large enough radius, search precision <= index precision, so it works."""
    index = GeohashIndex(precision=6)
    index.add(POI("1", "Coffee Shop", 37.7750, -122.4180, "cafe"))
    index.add(POI("2", "Bookstore", 37.7760, -122.4200, "retail"))
    index.add(POI("3", "Far Away Place", 38.0, -123.0, "other"))

    # radius=10 -> precision 5 (< 6), so prefix matching works
    results = index.nearby(37.7749, -122.4194, radius_km=10.0)
    assert len(results) == 2, f"Expected 2 nearby, got {len(results)}"


def test_geohash_encode_decode_roundtrip():
    """Encode then decode should return coordinates close to original."""
    coords = [(0, 0), (45.0, 90.0), (-33.8688, 151.2093), (37.7749, -122.4194)]
    for lat, lon in coords:
        gh = GeohashIndex.encode(lat, lon, precision=8)
        clat, clon, lat_err, lon_err = GeohashIndex.decode(gh)
        assert abs(clat - lat) < lat_err * 2, f"Lat mismatch for ({lat},{lon})"
        assert abs(clon - lon) < lon_err * 2, f"Lon mismatch for ({lat},{lon})"


def test_neighbors_count_and_uniqueness():
    """8 unique neighbors, none equal to the center."""
    gh = GeohashIndex.encode(40.7128, -74.0060, precision=5)
    nbrs = GeohashIndex.neighbors(gh)
    assert len(nbrs) == 8
    assert len(set(nbrs)) == 8
    assert gh not in nbrs


def test_haversine_known_distances():
    """Check against known distances."""
    assert haversine(0, 0, 0, 0) == 0.0
    # NYC to London ~ 5570 km
    d = haversine(40.7128, -74.0060, 51.5074, -0.1278)
    assert 5550 < d < 5600, f"NYC-London: {d}"


def test_remove_poi():
    """Removed POI should not appear in results."""
    index = GeohashIndex(precision=6)
    index.add(POI("a", "A", 37.775, -122.418))
    assert index.remove("a") is True
    assert index.remove("a") is False
    # Use large radius to avoid the nearby precision bug
    results = index.nearby(37.775, -122.418, radius_km=100.0)
    assert len(results) == 0


def test_quadtree_insert_and_query():
    """Quadtree insert, size, bbox query, range query."""
    qt = Quadtree(bounds=(-90, -180, 90, 180), max_points=2)
    pois = [POI(str(i), f"P{i}", i * 10.0, i * 20.0) for i in range(5)]
    for p in pois:
        assert qt.insert(p) is True
    assert qt.size == 5
    # bbox around one point
    found = qt.query_bbox(9, 19, 11, 21)
    assert len(found) == 1 and found[0].id == "1"
    # range query
    found = qt.query_range(10.0, 20.0, radius_km=1.0)
    assert len(found) == 1 and found[0].id == "1"


def test_large_dataset_performance():
    """10k POIs, search should complete quickly."""
    random.seed(42)
    qt = Quadtree(bounds=(30, -125, 45, -70), max_points=8)
    for i in range(10000):
        lat = 30 + random.random() * 15
        lon = -125 + random.random() * 55
        qt.insert(POI(str(i), f"P{i}", lat, lon))
    assert qt.size == 10000
    t0 = time.time()
    results = qt.query_range(37.7749, -122.4194, radius_km=50.0)
    elapsed = time.time() - t0
    assert len(results) > 0
    assert elapsed < 5.0, f"Quadtree too slow: {elapsed}s"


if __name__ == "__main__":
    passed = failed = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
