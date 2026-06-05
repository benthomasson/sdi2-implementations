"""Map Routing Service - shortest/fastest path finding on road networks."""

import heapq
import math
from dataclasses import dataclass, field


@dataclass
class Node:
    """An intersection or waypoint."""
    node_id: str
    lat: float
    lon: float
    name: str = ""


@dataclass
class Edge:
    """A road segment."""
    from_id: str
    to_id: str
    road_name: str
    distance_km: float
    speed_limit_kmh: float = 50.0
    one_way: bool = False


@dataclass
class RouteStep:
    """A single step in turn-by-turn directions."""
    instruction: str
    road_name: str
    distance_km: float
    duration_min: float


@dataclass
class Route:
    """A complete route."""
    steps: list
    total_distance_km: float
    total_duration_min: float
    path: list


def _haversine(lat1, lon1, lat2, lon2):
    """Distance in km between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1, lon1, lat2, lon2):
    """Bearing in degrees from point 1 to point 2."""
    dlon = math.radians(lon2 - lon1)
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _turn_instruction(bearing_change):
    """Convert bearing change to turn instruction."""
    bc = bearing_change % 360
    if bc > 180:
        bc -= 360
    if -30 <= bc <= 30:
        return "Continue straight"
    elif bc > 30:
        return "Turn right"
    else:
        return "Turn left"


class MapService:
    """Map routing service with Dijkstra/A* pathfinding."""

    def __init__(self):
        self.nodes = {}
        self.adj = {}  # node_id -> {neighbor_id -> edge_data}
        self.geocode_map = {}

    def add_node(self, node):
        """Add an intersection to the road network."""
        self.nodes[node.node_id] = node
        if node.node_id not in self.adj:
            self.adj[node.node_id] = {}
        if node.name:
            self.geocode_map[node.name.lower()] = (node.lat, node.lon, node.node_id)

    def add_edge(self, edge):
        """Add a road segment. If not one_way, adds both directions."""
        e = {"road_name": edge.road_name, "distance_km": edge.distance_km,
             "speed_limit_kmh": edge.speed_limit_kmh}
        self.adj.setdefault(edge.from_id, {})[edge.to_id] = e
        if not edge.one_way:
            self.adj.setdefault(edge.to_id, {})[edge.from_id] = e

    def _get_weight(self, edge_data, optimize):
        if optimize == "time":
            return (edge_data["distance_km"] / edge_data["speed_limit_kmh"]) * 60  # minutes
        return edge_data["distance_km"]

    def _heuristic(self, node_id, goal_id, optimize):
        """A* heuristic using Haversine distance."""
        n1, n2 = self.nodes[node_id], self.nodes[goal_id]
        dist = _haversine(n1.lat, n1.lon, n2.lat, n2.lon)
        if optimize == "time":
            max_speed = max((e["speed_limit_kmh"] for adj in self.adj.values() for e in adj.values()), default=120)
            return (dist / max_speed) * 60
        return dist

    def _find_path(self, start_id, end_id, algorithm="astar", optimize="distance", blocked_edges=None):
        """Core pathfinding. Returns (path, cost) or (None, None)."""
        if start_id not in self.nodes or end_id not in self.nodes:
            return None, None
        if start_id == end_id:
            return [start_id], 0.0

        blocked = blocked_edges or set()
        dist = {start_id: 0.0}
        prev = {}
        counter = 0
        h = self._heuristic(start_id, end_id, optimize) if algorithm == "astar" else 0
        pq = [(h, counter, start_id)]

        while pq:
            _, _, u = heapq.heappop(pq)
            if u == end_id:
                path = []
                while u is not None:
                    path.append(u)
                    u = prev.get(u)
                return path[::-1], dist[end_id]

            if dist.get(u, float("inf")) < _ - (self._heuristic(u, end_id, optimize) if algorithm == "astar" else 0) - 1e-9:
                continue

            for v, edata in self.adj.get(u, {}).items():
                if (u, v) in blocked:
                    continue
                w = self._get_weight(edata, optimize)
                nd = dist[u] + w
                if nd < dist.get(v, float("inf")):
                    dist[v] = nd
                    prev[v] = u
                    counter += 1
                    h = self._heuristic(v, end_id, optimize) if algorithm == "astar" else 0
                    heapq.heappush(pq, (nd + h, counter, v))

        return None, None

    def _build_route(self, path, optimize="distance"):
        """Build a Route object from a path of node IDs."""
        if not path or len(path) < 2:
            if path and len(path) == 1:
                return Route([], 0.0, 0.0, path)
            return None

        steps = []
        total_dist = 0.0
        total_time = 0.0

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edata = self.adj[u][v]
            dist_km = edata["distance_km"]
            dur_min = (dist_km / edata["speed_limit_kmh"]) * 60
            total_dist += dist_km
            total_time += dur_min

            # Determine turn instruction
            if i == 0:
                instruction = f"Head onto {edata['road_name']}"
            else:
                prev_node = self.nodes[path[i - 1]]
                curr_node = self.nodes[path[i]]
                next_node = self.nodes[path[i + 1]]
                b1 = _bearing(prev_node.lat, prev_node.lon, curr_node.lat, curr_node.lon)
                b2 = _bearing(curr_node.lat, curr_node.lon, next_node.lat, next_node.lon)
                turn = _turn_instruction(b2 - b1)
                prev_road = self.adj[path[i - 1]][path[i]]["road_name"]
                if edata["road_name"] == prev_road and turn == "Continue straight":
                    instruction = f"Continue on {edata['road_name']} for {dist_km:.1f} km"
                else:
                    instruction = f"{turn} onto {edata['road_name']}"

            steps.append(RouteStep(instruction, edata["road_name"], dist_km, dur_min))

        return Route(steps, round(total_dist, 10), round(total_time, 10), path)

    def shortest_path(self, start_id, end_id, algorithm="astar", optimize="distance"):
        """Find shortest/fastest route."""
        path, cost = self._find_path(start_id, end_id, algorithm, optimize)
        if path is None:
            return None
        return self._build_route(path, optimize)

    def alternative_routes(self, start_id, end_id, k=3):
        """Find up to k alternative routes using Yen's algorithm."""
        best_path, _ = self._find_path(start_id, end_id, "astar", "distance")
        if best_path is None:
            return []

        A = [best_path]
        B = []

        for i in range(1, k):
            for j in range(len(A[-1]) - 1):
                spur_node = A[-1][j]
                root_path = A[-1][:j + 1]
                blocked = set()
                for p in A:
                    if p[:j + 1] == root_path and j + 1 < len(p):
                        blocked.add((p[j], p[j + 1]))

                spur_path, _ = self._find_path(spur_node, end_id, "astar", "distance", blocked)
                if spur_path is not None:
                    total = root_path[:-1] + spur_path
                    if total not in A and total not in [x[1] for x in B]:
                        route = self._build_route(total)
                        if route:
                            heapq.heappush(B, (route.total_distance_km, total))

            if not B:
                break
            _, next_path = heapq.heappop(B)
            A.append(next_path)

        return [self._build_route(p) for p in A]

    def eta(self, start_id, end_id):
        """Estimated time of arrival in minutes."""
        route = self.shortest_path(start_id, end_id, optimize="time")
        return route.total_duration_min if route else None

    def get_directions(self, start_id, end_id):
        """Get turn-by-turn directions."""
        route = self.shortest_path(start_id, end_id)
        return route.steps if route else []

    def get_tile(self, lat, lon, tile_size=0.01):
        """Return nodes and edges within a map tile."""
        min_lat = math.floor(lat / tile_size) * tile_size
        min_lon = math.floor(lon / tile_size) * tile_size
        max_lat = min_lat + tile_size
        max_lon = min_lon + tile_size

        tile_nodes = [n for n in self.nodes.values()
                      if min_lat <= n.lat < max_lat and min_lon <= n.lon < max_lon]
        tile_node_ids = {n.node_id for n in tile_nodes}
        tile_edges = []
        for nid in tile_node_ids:
            for vid, edata in self.adj.get(nid, {}).items():
                tile_edges.append({"from": nid, "to": vid, **edata})

        return {"nodes": tile_nodes, "edges": tile_edges}

    def geocode(self, name):
        """Map a location name to coordinates."""
        result = self.geocode_map.get(name.lower())
        if result:
            return {"lat": result[0], "lon": result[1], "node_id": result[2]}
        return None
