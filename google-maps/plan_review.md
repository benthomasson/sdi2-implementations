# Plan Review: Google Maps (Map Routing Service)

## Plan Strengths

- Unified `_find_path` for both Dijkstra and A*: A* adds Haversine heuristic, Dijkstra uses h=0. Same loop, clean parameterization.
- A* heuristic is admissible: uses Haversine straight-line distance (never overestimates). For time optimization, divides by max speed across all edges.
- Yen's K-shortest paths algorithm correctly blocks edges from previously found paths at each spur node to force alternative routes.
- Turn-by-turn directions use bearing computation between consecutive node triples: left/right/straight based on bearing change.
- One-way edges correctly handled: `add_edge` only adds reverse direction when `one_way=False`.
- Map tiles via grid cell bucketing: `floor(lat/tile_size) * tile_size` creates non-overlapping tiles.
- Geocoding simulation: case-insensitive name-to-coordinate lookup from named nodes.

## Plan Gaps

1. **A* stale-node check (line 138) is fragile.** The condition `dist.get(u, float("inf")) < _ - heuristic - 1e-9` tries to skip stale priority queue entries, but the epsilon comparison and recomputing the heuristic at pop time could miss edge cases. The standard approach is a `visited` set. Works in practice but theoretically unsound.

2. **A* heuristic for time optimization computes `max_speed` on every call.** Line 111: iterates all edges in the graph to find the maximum speed limit. This should be cached when edges are added.

3. **`add_edge` overwrites existing edges.** If two roads connect the same pair of intersections, only the last one is stored. A multigraph (list of edges per pair) would be more accurate.

4. **Yen's algorithm only finds alternatives by distance.** `alternative_routes` hardcodes `optimize="distance"`. No option to find alternative fastest routes.

## Implementation Issues (0 test failures)

No test failures. Solid implementation at 267 lines. A* on 10K nodes with 5K shortcuts completes well within the 5-second limit.
