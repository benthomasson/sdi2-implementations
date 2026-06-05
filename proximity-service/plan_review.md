# Plan Review: Proximity Service

## Plan Strengths

- Standard geohash encoding/decoding with base32 and bit-interleaving (longitude on odd bits, latitude on even bits).
- Neighbor computation via coordinate nudging: decode center, offset by cell dimensions, re-encode. Handles antimeridian wrapping and pole clamping.
- Quadtree with configurable `max_points` per leaf and `max_depth`. Subdivision redistributes points to children. `__slots__` on `_QuadNode` for memory efficiency.
- Range queries on quadtree use bounding box approximation from radius (`dlat = radius_km / 111.0`, with cos(lat) correction for dlon), then Haversine filter.
- Geohash `nearby()` correctly collects all matching prefixes from the center cell and 8 neighbors, then filters by exact Haversine distance.
- Precision-for-radius table maps search radius to appropriate geohash precision.
- POI removal from geohash index correctly cleans up both the index and the ID lookup.

## Plan Gaps

1. **Geohash `nearby()` search precision exceeded index precision.** `_precision_for_radius(1.0)` returned 7 but the index stored POIs at precision 6. The prefix comparison `gh[:7] == cell` on a 6-char key never matched. **Fixed:** Capped search precision at `min(_precision_for_radius(radius_km), self.precision)`.

2. **Geohash `nearby()` scans all index entries.** Line 72-74: iterates every geohash bucket to find prefix matches. Should use a prefix-keyed data structure (trie or sorted list with bisect) for O(k) lookups where k is the number of matching cells.

3. **Quadtree doesn't support POI removal.** No `remove` method on the quadtree — only the geohash index supports removal.

4. **Quadtree bounding box approximation at extreme latitudes.** `max(cos(radians(lat)), 0.001)` prevents division by zero at poles but produces very wide longitude ranges, which is correct but leads to many candidates being checked.

## Implementation Issues (1 bug fixed)

1. **Geohash nearby search returned 0 results for small radii.** Search precision (7) exceeded index precision (6), making prefix comparison fail. **Fix:** `precision = min(self._precision_for_radius(radius_km), self.precision)`. Updated the test from documenting the bug to asserting correct behavior. 9/9 tests pass.
