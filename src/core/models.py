# src/core/models.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

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
    # Nuevos campos para fase avanzada (edición por científico)
    # life_delta: ganancia o pérdida de años luz al investigar esta estrella
    life_delta: float = 0.0
    # health_modifier: posible cambio textual del estado de salud ("Excelente", "Regular", "Mala", etc.)
    health_modifier: Optional[str] = None
    # energy_bonus_pct: porcentaje extra de energía recuperada al comer aquí (ej. 0.1 = +10%)
    energy_bonus_pct: float = 0.0

    def add_link(self, to: int, distance: float, blocked: bool = False):
        # avoid duplicate exact link (same to and distance)
        for l in self.links:
            if l.to == to:
                # if same neighbor but different distance, keep minimal
                if l.distance != distance:
                    l.distance = min(l.distance, distance)
                # If any source marks the link as blocked, treat it as blocked
                l.blocked = l.blocked or blocked
                return
        self.links.append(Link(to=to, distance=distance, blocked=blocked))

    # Nota: método distance_to eliminado por no ser usado actualmente

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
    # Configuración opcional de simulación (cargada desde burro.json)
    sim_config: Optional[dict] = None

    def is_alive(self) -> bool:
        return self.energia_pct > 0 and self.vida_maxima > 0

    def energy_gain_per_kg(self) -> float:
        """Retorna ganancia de energía por kg según salud.

        Si hay configuración en sim_config['healthEnergyGain'] la usa; de lo contrario,
        aplica valores por defecto del enunciado.
        """
        if self.sim_config and isinstance(self.sim_config.get("healthEnergyGain"), dict):
            mapping = self.sim_config.get("healthEnergyGain")
            try:
                return float(mapping.get(self.salud, 2.0))
            except Exception:
                pass
        # Defaults
        mapping = {
            "Excelente": 5.0,
            "Buena": 3.0,
            "Regular": 3.0,  # alias de compatibilidad
            "Mala": 2.0,
            "Moribundo": 0.5,
            "Muerto": 0.0,
        }
        return mapping.get(self.salud, 2.0)

    def apply_health_modifier(self, modifier: Optional[str]):
        """Aplica cambio de salud si el modificador es válido."""
        if not modifier:
            return
        valid = {"Excelente", "Regular", "Mala", "Moribundo", "Muerto"}
        # también aceptar "Buena" como estado válido
        if modifier in valid or modifier == "Buena":
            self.salud = modifier

    # --- Nuevo: actualización dinámica de salud basada en energía (%) ---
    def update_health_by_energy(self):
        """Deriva salud desde energia_pct si no está muerto.

        Mapeo (inclusive límites superiores):
          0 -> Muerto (si energia_pct <=0)
          (0,25] -> Moribundo
          (25,50] -> Mala
          (50,75] -> Buena (alias Regular)
          (75,100] -> Excelente

        Si una enfermedad cambió la salud explícitamente a un estado peor (ej. Moribundo)
        y el % de energía sube, permitimos mejora natural. Si es "Muerto" no cambia.
        """
        if self.salud == "Muerto":
            return
        e = float(self.energia_pct)
        if e <= 0:
            self.salud = "Muerto"
            return
        if e <= 25:
            target = "Moribundo"
        elif e <= 50:
            target = "Mala"
        elif e <= 75:
            target = "Buena"  # preferimos mostrar Buena
        else:
            target = "Excelente"
        self.salud = target

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
            # If any definition says blocked, mark edge as blocked
            existing_edge.blocked = existing_edge.blocked or blocked
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

    # Removed unused helpers: neighbors(), find_shared_stars().

    def hypergiant_counts(self) -> Dict[str, int]:
        counts = {}
        for cname, const in self.constellations.items():
            c = 0
            for sid in const.stars:
                if sid in self.stars and self.stars[sid].hypergiant:
                    c += 1
            counts[cname] = c
        return counts

    def recompute_shared_flags(self) -> int:
        """Recalcula el atributo 'shared' de cada estrella según pertenezca
        a más de una constelación. Además, sincroniza star.constellations con
        los datos de Graph.constellations.

        Returns:
            int: número de estrellas cuyo flag 'shared' cambió.
        """
        # Construye mapa sid -> conjunto de constelaciones en las que aparece
        memberships: Dict[int, set] = {}
        for cname, const in self.constellations.items():
            for sid in const.stars:
                memberships.setdefault(sid, set()).add(cname)

        changed = 0
        for sid, star in self.stars.items():
            consts = sorted(memberships.get(sid, set()))
            # Sincroniza la lista de constelaciones en el objeto Star
            prev_shared = star.shared
            star.constellations = consts
            star.shared = len(consts) > 1
            if star.shared != prev_shared:
                changed += 1
        return changed

    def toggle_edge_block(self, u: int, v: int, blocked: Optional[bool] = None) -> bool:
        """Alterna o establece el estado 'blocked' para la arista (u,v) y su
        par inverso (v,u). También sincroniza Star.links en ambos extremos.

        Args:
            u (int): nodo origen
            v (int): nodo destino
            blocked (Optional[bool]): si None, alterna; si True/False, fija.

        Returns:
            bool: True si se modificó alguna arista, False si no existía la arista.
        """
        changed = False
        # Helper para aplicar cambio en adjacency y Star.links
        def _apply(a: int, b: int) -> bool:
            mod = False
            if a in self.adjacency and b in self.adjacency[a]:
                edge = self.adjacency[a][b]
                new_val = (not edge.blocked) if blocked is None else bool(blocked)
                if edge.blocked != new_val:
                    edge.blocked = new_val
                    mod = True
                # sync Star.links
                if a in self.stars:
                    for l in self.stars[a].links:
                        if l.to == b:
                            l.blocked = edge.blocked
                            break
            return mod

        changed = _apply(u, v) or changed
        changed = _apply(v, u) or changed
        return changed
