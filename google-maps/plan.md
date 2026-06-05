# Plan (Iteration 1)

Task: Map Routing Service
====================
SDI Vol 2 Reference: Chapter 3 - Google Maps

Overview
--------
Build a map routing service that finds the shortest/fastest path between two
points on a road network. The system models roads as a weighted directed graph
and uses Dijkstra's and A* algorithms for pathfinding. It produces turn-by-turn
directions and ETA estimates. This is the core algorithm behind Google Maps,
Apple Maps, and Waze routing.

Requirements
------------
1. Road network graph: nodes represent intersections, edges represent road
   segments with distance (km) and speed limit (km/h).
2. Edge properties: name, distance, speed_limit, one_way flag.
3. Dijkstra's algorithm for shortest path by distance.
4. A* algorithm for shortest path with heuristic (Haversine to goal).
5. Fastest path: weight edges by travel time (distance / speed_limit).
6. Turn-by-turn directions: produce a list of navigation instructions
   (e.g., "Turn left onto Main St", "Continue for 2.3 km").
7. ETA calculation based on road speed limits.
8. Alternative routes: find top-K shortest paths.
9. Map tiles: divide the map into grid cells, return POIs/roads per tile.
10. Geocoding simulation: map location names to coordinates.

Interface
---------
class Node:
    def __init__(self, node_id: str, lat: float, lon: float, name: str = ""):
        """An intersection or waypoint."""

class Edge:
    def __init__(self, from_id: str, to_id: str, road_name: str,
                 distance_km: float, speed_limit_kmh: float = 50,
                 one_way: bool = False):
        """A road segment."""

class RouteStep:
    def __init__(self, instruction: str, road_name: str,
                 distance_km: float, duration_min: float):
        """A single step in turn-by-turn directions."""

class Route:
    def __init__(self, steps: list[RouteStep], total_distance_km: float,
                 total_duration_min: float, path: list[str]):
        """A complete route."""

class MapService:
    def __init__(self):
        """Initialize the map service."""

    def add_node(self, node: Node) -> None:
        """Add an intersection to the road network."""

    def add_edge(self, edge: Edge) -> None:
        """Add a road segment. If not one_way, adds both directions."""

    def shortest_path(self, start_id: str, end_id: str,
                      algorithm: str = "astar",
                      optimize: str = "distance") -> Route | None:
        """Find shortest/fastest route. algorithm: 'dijkstra' or 'astar'.
        optimize: 'distance' or 'time'."""

    def alternative_routes(self, start_id: str, end_id: str,
                           k: int = 3) -> list[Route]:
        """Find up to k alternative routes."""

    def eta(self, start_id: str, end_id: str) -> float | None:
        """Estimated time of arrival in minutes."""

    def get_directions(self, start_id: str, end_id: str) -> list[RouteStep]:
        """Get turn-by-turn directions."""

Example Usage
-------------
    service = MapService()
    service.add_node(Node("A", 37.77, -122.42, "Start"))
    service.add_node(Node("B", 37.78, -122.41, "Via Main"))
    service.add_node(Node("C", 37.79, -122.40, "Destination"))

    service.add_edge(Edge("A", "B", "Main St", 1.5, 40))
    service.add_edge(Edge("B", "C", "Oak Ave", 1.2, 30))
    service.add_edge(Edge("A", "C", "Highway 1", 3.0, 80))

    route = service.shortest_path("A", "C", optimize="distance")
    assert route.total_distance_km == 2.7  # A->B->C is shorter

    fast_route = service.shortest_path("A", "C", optimize="time")
    # Highway might be faster despite being longer

    directions = service.get_directions("A", "C")
    assert len(directions) >= 1

Constraints
-----------
- Graph can have up to 100,000 nodes and 500,000 edges.
- A* must use Haversine as the admissible heuristic.
- Handle disconnected graphs (return None for unreachable).
- Target: 200-400 lines of Python.

Testing Requirements
--------------------
1. Shortest path by distance is correct.
2. Fastest path by time differs from shortest distance.
3. A* and Dijkstra produce same result.
4. One-way roads are respected.
5. Unreachable destination returns None.
6. Turn-by-turn directions are generated.
7. ETA calculation matches expected travel time.
8. Alternative routes are distinct.
9. Single-node path (start == end).
10. Large graph performance is acceptable.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `planner/PLAN.md`. 

**Summary:** Single Python module using adjacency-list graph, shared Dijkstra/A* loop (A* adds Haversine heuristic), Yen's algorithm for K alternative routes, bearing-based turn-by-turn directions, grid-based map tiles, and dictionary geocoding. Confidence: **HIGH**.

[Committed changes to planner branch]