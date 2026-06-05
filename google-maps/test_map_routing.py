"""Tests for Map Routing Service."""
import sys
import time
import random

sys.path.insert(0, "../implementer")
from map_routing import Node, Edge, RouteStep, Route, MapService


def build_sample_graph():
    """Build the example graph from the task spec."""
    s = MapService()
    s.add_node(Node("A", 37.77, -122.42, "Start"))
    s.add_node(Node("B", 37.78, -122.41, "Via Main"))
    s.add_node(Node("C", 37.79, -122.40, "Destination"))
    s.add_edge(Edge("A", "B", "Main St", 1.5, 40))
    s.add_edge(Edge("B", "C", "Oak Ave", 1.2, 30))
    s.add_edge(Edge("A", "C", "Highway 1", 3.0, 80))
    return s


def test_shortest_path_by_distance():
    """Req 1,3: Shortest path A->B->C = 2.7 km (shorter than direct 3.0)."""
    s = build_sample_graph()
    route = s.shortest_path("A", "C", optimize="distance")
    assert route is not None
    assert route.path == ["A", "B", "C"]
    assert abs(route.total_distance_km - 2.7) < 1e-6
    print("PASS: shortest_path_by_distance")


def test_fastest_path_differs():
    """Req 2,5: Fastest path may differ from shortest distance path."""
    s = build_sample_graph()
    dist_route = s.shortest_path("A", "C", optimize="distance")
    time_route = s.shortest_path("A", "C", optimize="time")
    # Highway 1 at 80km/h: 3.0/80*60 = 2.25 min
    # Main+Oak: 1.5/40*60 + 1.2/30*60 = 2.25 + 2.4 = 4.65 min
    assert time_route is not None
    assert time_route.path == ["A", "C"], f"Expected highway, got {time_route.path}"
    assert time_route.path != dist_route.path
    print("PASS: fastest_path_differs")


def test_astar_matches_dijkstra():
    """Req 3,4: A* and Dijkstra produce same optimal path."""
    s = build_sample_graph()
    r1 = s.shortest_path("A", "C", algorithm="dijkstra", optimize="distance")
    r2 = s.shortest_path("A", "C", algorithm="astar", optimize="distance")
    assert r1.path == r2.path
    assert abs(r1.total_distance_km - r2.total_distance_km) < 1e-6
    print("PASS: astar_matches_dijkstra")


def test_one_way_roads():
    """Req 4: One-way roads are respected."""
    s = MapService()
    s.add_node(Node("X", 0.0, 0.0))
    s.add_node(Node("Y", 0.0, 1.0))
    s.add_edge(Edge("X", "Y", "One Way St", 1.0, 50, one_way=True))
    assert s.shortest_path("X", "Y") is not None
    assert s.shortest_path("Y", "X") is None  # Can't go backwards
    print("PASS: one_way_roads")


def test_unreachable():
    """Req 5: Unreachable destination returns None."""
    s = MapService()
    s.add_node(Node("A", 0.0, 0.0))
    s.add_node(Node("B", 1.0, 1.0))
    # No edges
    assert s.shortest_path("A", "B") is None
    print("PASS: unreachable")


def test_directions():
    """Req 6: Turn-by-turn directions are generated."""
    s = build_sample_graph()
    directions = s.get_directions("A", "C")
    assert len(directions) >= 1
    assert all(isinstance(d, RouteStep) for d in directions)
    assert all(d.road_name for d in directions)
    assert all(d.instruction for d in directions)
    print("PASS: directions")


def test_eta():
    """Req 7: ETA matches expected travel time."""
    s = build_sample_graph()
    eta_min = s.eta("A", "C")
    assert eta_min is not None
    # Fastest route is Highway 1: 3.0/80*60 = 2.25 min
    assert abs(eta_min - 2.25) < 1e-6
    print("PASS: eta")


def test_alternative_routes():
    """Req 8: Alternative routes are distinct."""
    s = build_sample_graph()
    routes = s.alternative_routes("A", "C", k=3)
    assert len(routes) >= 2
    paths = [r.path for r in routes]
    assert len(paths) == len(set(tuple(p) for p in paths)), "Routes not distinct"
    print("PASS: alternative_routes")


def test_same_node():
    """Req 9: Start == end returns trivial route."""
    s = build_sample_graph()
    route = s.shortest_path("A", "A")
    assert route is not None
    assert route.path == ["A"]
    assert route.total_distance_km == 0.0
    print("PASS: same_node")


def test_large_graph_performance():
    """Req 10: A* on 10K+ nodes completes quickly."""
    s = MapService()
    N = 10000
    random.seed(42)
    for i in range(N):
        s.add_node(Node(str(i), random.uniform(-90, 90), random.uniform(-180, 180)))
    for i in range(N - 1):
        s.add_edge(Edge(str(i), str(i + 1), f"Road {i}", random.uniform(0.1, 5.0),
                        random.uniform(30, 120)))
    # Add some shortcuts
    for _ in range(5000):
        a, b = random.randint(0, N - 1), random.randint(0, N - 1)
        if a != b:
            s.add_edge(Edge(str(a), str(b), "Shortcut", random.uniform(0.5, 10.0),
                            random.uniform(40, 100)))

    t0 = time.time()
    route = s.shortest_path("0", str(N - 1), algorithm="astar")
    elapsed = time.time() - t0
    assert route is not None
    assert elapsed < 5.0, f"A* took {elapsed:.2f}s on {N} nodes"
    print(f"PASS: large_graph_performance ({elapsed:.3f}s)")


if __name__ == "__main__":
    test_shortest_path_by_distance()
    test_fastest_path_differs()
    test_astar_matches_dijkstra()
    test_one_way_roads()
    test_unreachable()
    test_directions()
    test_eta()
    test_alternative_routes()
    test_same_node()
    test_large_graph_performance()
    print("\nAll tests passed!")
