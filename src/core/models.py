# src/core/models.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math

@dataclass
class Link:
    to: int
    distance: float
    blocked: bool = False

@dataclass
class Star:
    id: int
    label: str
    x: float
    y: float
    radius: float = 0.5
    time_to_eat: float = 1.0
    amount_of_energy: float = 1.0
    investigation_energy_cost: float = 0.0
    hypergiant: bool = False
    shared: bool = False
    constellations: List[str] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)

    def add_link(self, to: int, distance: float, blocked: bool = False):
        # avoid duplicate exact link (same to and distance)
        for l in self.links:
            if l.to == to:
                # if same neighbor but different distance, keep minimal
                if l.distance != distance:
                    l.distance = min(l.distance, distance)
                l.blocked = l.blocked and blocked  # keep blocked True if both True
                return
        self.links.append(Link(to=to, distance=distance, blocked=blocked))

    def distance_to(self, other: 'Star') -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

@dataclass
class Constellation:
    name: str
    stars: List[int] = field(default_factory=list)
    color: Optional[Tuple[int,int,int]] = None

@dataclass
class Donkey:
    id: Optional[int]
    nombre: Optional[str]
    salud: str
    energia_pct: float
    pasto_kg: float
    edad: float
    vida_maxima: float

    def is_alive(self) -> bool:
        return self.energia_pct > 0 and self.vida_maxima > 0

    def energy_gain_per_kg(self) -> float:
        # Default mapping: puedes ajustar o leer desde JSON/setting
        mapping = {
            "Excelente": 5.0,
            "Regular": 3.0,
            "Mala": 2.0,
            "Moribundo": 0.5,
            "Muerto": 0.0
        }
        return mapping.get(self.salud, 2.0)

@dataclass
class Edge:
    u: int
    v: int
    distance: float
    blocked: bool = False

@dataclass
class Graph:
    stars: Dict[int, Star] = field(default_factory=dict)
    constellations: Dict[str, Constellation] = field(default_factory=dict)
    adjacency: Dict[int, Dict[int, Edge]] = field(default_factory=dict)

    def add_star(self, star: Star, constellation_name: Optional[str] = None):
        """Registra la estrella y (opcionalmente) la anexa a una constelación.

        Invariantes:
        - self.stars: {id -> Star}
        - self.constellations[name].stars: lista de IDs (ints)
        - star.constellations sincronizado al anexar
        """
        self.stars[star.id] = star
        if constellation_name is not None:
            const = self.constellations.get(constellation_name)
            if const is None:
                const = Constellation(constellation_name)
                self.constellations[constellation_name] = const
            if star.id not in const.stars:
                const.stars.append(star.id)
            if constellation_name not in star.constellations:
                star.constellations.append(constellation_name)

    def add_edge(self, u: int, v: int, distance: float, blocked: bool = False):
        if u not in self.stars or v not in self.stars:
            raise KeyError(f"Trying to add edge with missing star: {u} -> {v}")
        # add in adjacency dict (keeps minimal distance if conflicting)
        existing = self.adjacency.setdefault(u, {})
        if v in existing:
            existing_edge = existing[v]
            existing_edge.distance = min(existing_edge.distance, distance)
            existing_edge.blocked = existing_edge.blocked and blocked
        else:
            existing[v] = Edge(u=u, v=v, distance=distance, blocked=blocked)
        # also ensure a Star.links list is consistent
        self.stars[u].add_link(v, distance, blocked)

    def ensure_bidirectional(self, default_blocked: bool = False):
        for u, neighbors in list(self.adjacency.items()):
            for v, edge in list(neighbors.items()):
                # add reverse if missing
                rev = self.adjacency.setdefault(v, {})
                if u not in rev:
                    rev[u] = Edge(u=v, v=u, distance=edge.distance, blocked=edge.blocked or default_blocked)
                    # also update star.links
                    self.stars[v].add_link(u, edge.distance, edge.blocked or default_blocked)

    def neighbors(self, node_id: int, include_blocked: bool = False) -> List[Edge]:
        if node_id not in self.adjacency:
            return []
        edges = []
        for v, e in self.adjacency[node_id].items():
            if not include_blocked and e.blocked:
                continue
            edges.append(e)
        return edges

    def toggle_edge_block(self, u: int, v: int, blocked: Optional[bool] = None):
        if u in self.adjacency and v in self.adjacency[u]:
            if blocked is None:
                self.adjacency[u][v].blocked = not self.adjacency[u][v].blocked
            else:
                self.adjacency[u][v].blocked = blocked
        if v in self.adjacency and u in self.adjacency[v]:
            if blocked is None:
                self.adjacency[v][u].blocked = not self.adjacency[v][u].blocked
            else:
                self.adjacency[v][u].blocked = blocked

    def find_shared_stars(self) -> List[Star]:
        return [s for s in self.stars.values() if len(s.constellations) > 1 or s.shared]

    def hypergiant_counts(self) -> Dict[str, int]:
        counts = {}
        for cname, const in self.constellations.items():
            c = 0
            for sid in const.stars:
                if sid in self.stars and self.stars[sid].hypergiant:
                    c += 1
            counts[cname] = c
        return counts
