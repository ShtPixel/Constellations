from __future__ import annotations
from typing import Dict, Optional, Tuple, List
from dataclasses import replace
import heapq
import time

try:
    from src.core.models import Graph, Donkey
except ModuleNotFoundError:
    from core.models import Graph, Donkey

INF = float('inf')


def dijkstra(graph: Graph, source: int, include_blocked: bool = False) -> Tuple[Dict[int, float], Dict[int, Optional[int]]]:
    """
    Compute single-source shortest paths using Dijkstra.

    Args:
        graph: Graph with adjacency[u][v] = Edge(distance, blocked)
        source: starting node id (must exist in graph.stars)
        include_blocked: if True, treat blocked edges as usable; default False ignores blocked.

    Returns:
        (dist, parent) where:
          - dist[v] = minimal distance from source to v (absent => INF)
          - parent[v] = previous node on the shortest path (None for source)
    """
    if source not in graph.stars:
        raise ValueError(f"source {source} not in graph")

    dist: Dict[int, float] = {source: 0.0}
    parent: Dict[int, Optional[int]] = {source: None}
    pq: List[Tuple[float, int]] = [(0.0, source)]

    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, INF):
            continue
        for v, e in graph.adjacency.get(u, {}).items():
            if (not include_blocked) and e.blocked:
                continue
            nd = d + float(e.distance)
            if nd < dist.get(v, INF):
                dist[v] = nd
                parent[v] = u
                heapq.heappush(pq, (nd, v))

    return dist, parent


def reconstruct_path(parent: Dict[int, Optional[int]], target: int) -> List[int]:
    """Reconstruct path from source to target using parent table. Returns [] if unreachable."""
    if target not in parent:
        return []
    path: List[int] = []
    cur: Optional[int] = target
    while cur is not None:
        path.append(cur)
        cur = parent.get(cur)
    path.reverse()
    return path


def greedy_max_visits(graph: Graph, source: int, budget: float, include_blocked: bool = False) -> Tuple[List[int], float]:
    """Planifica un recorrido que visite la mayor cantidad de nodos posible
    seleccionando iterativamente el próximo nodo alcanzable más cercano.

    Supuestos:
    - El costo de moverse entre nodos es la distancia (suma de aristas) del camino más corto.
    - No se considera ganancia de energía al visitar estrellas (baseline simple).
    - Ignora aristas bloqueadas por defecto (include_blocked=False).

    Args:
        graph: grafo con adjacency y stars.
        source: nodo inicial.
        budget: energía/distancia disponible para moverse.
        include_blocked: si True, permite usar aristas bloqueadas.

    Returns:
        (ruta, costo_total_usado)
    """
    if source not in graph.stars:
        raise ValueError("source not in graph")
    if budget <= 0:
        return [source], 0.0

    visited: set[int] = set([source])
    route: List[int] = [source]
    used = 0.0
    current = source

    # Lista de candidatos inicial
    remaining: set[int] = set(graph.stars.keys()) - visited

    while remaining:
        # Dijkstra desde current a todos
        dist, parent = dijkstra(graph, current, include_blocked=include_blocked)
        # Elegir el alcanzable más cercano dentro del presupuesto restante
        best_node = None
        best_cost = INF
        for v in list(remaining):
            c = dist.get(v, INF)
            if c < best_cost and used + c <= budget:
                best_cost = c
                best_node = v
        if best_node is None:
            break  # no hay más alcanzables dentro del presupuesto

        # Avanzar: consumir costo y mover current
        used += best_cost
        # Agregar path intermedio (expande ruta por nodos intermedios si existen)
        path = reconstruct_path(parent, best_node)
        if path and path[0] == current:
            # añadir intermedios sin repetir
            for node in path[1:]:
                if node not in visited:
                    visited.add(node)
                route.append(node)
        else:
            # fallback: añadir directamente el nodo
            route.append(best_node)
            visited.add(best_node)
        current = best_node
        remaining.discard(best_node)

    return route, used


def energy_budget_from_donkey(donkey: Donkey) -> float:
    """Cálculo mejorado de presupuesto estático para fase 2.

    Considera:
    - Energía inicial (burroenergiaInicial) como unidades de energía disponibles.
    - Potencial de conversión de todo el pasto: pasto_kg * ganancia_por_kg.
    - Vida máxima como tope superior de distancia recorrible (cada unidad de distancia reduce vida en 1).

    Fórmula:
        presupuesto_energia = energia_pct + pasto_kg * gain_per_kg
        presupuesto_distancia = vida_maxima - edad (no negativo)
    Se toma el mínimo entre presupuesto_energia y presupuesto_distancia para restringir la ruta.
    """
    energia_base = float(donkey.energia_pct)
    gain_per_kg = float(donkey.energy_gain_per_kg())
    energia_pasto_total = float(donkey.pasto_kg) * gain_per_kg
    presupuesto_energia = energia_base + energia_pasto_total
    vida_restante = max(0.0, float(donkey.vida_maxima) - float(donkey.edad))
    return max(0.0, min(presupuesto_energia, vida_restante))


def compute_energy_budget(donkey: Donkey) -> float:
    """Presupuesto energético estático usando SOLO valores iniciales.

    energia_pct + pasto_kg * gain_per_kg
    """
    energia_base = float(donkey.energia_pct)
    gain_per_kg = float(donkey.energy_gain_per_kg())
    return max(0.0, energia_base + float(donkey.pasto_kg) * gain_per_kg)


def compute_life_budget(donkey: Donkey) -> float:
    """Presupuesto de vida (años luz) usando SOLO valores iniciales."""
    return max(0.0, float(donkey.vida_maxima) - float(donkey.edad))


def movement_energy_factor(donkey: Donkey) -> float:
    """Factor energético por unidad de distancia según salud inicial.

    Lee sim_config['movementCostFactorByHealth'] si existe; por defecto usa
    {Excelente:0.6, Buena:0.75, Regular:0.8, Mala:1.0, Moribundo:1.3}.
    """
    cfg = getattr(donkey, 'sim_config', None) or {}
    factors = cfg.get('movementCostFactorByHealth') or {}
    try:
        return float(factors.get(donkey.salud, 1.0))
    except Exception:
        # defaults
        defaults = {
            "Excelente": 0.6,
            "Buena": 0.75,
            "Regular": 0.8,
            "Mala": 1.0,
            "Moribundo": 1.3,
        }
        return float(defaults.get(donkey.salud, 1.0))


def estimate_static_visit_cost(star, donkey: Donkey) -> float:
    """Costo energético ESTÁTICO de visitar la estrella para el plan puro.

    En 1.2 se calculan rutas con valores iniciales; no hay recuperación ni
    mutaciones. Aproximamos el costo como:
        investigation_energy_cost * (time_to_eat * 0.5)
    (Se asume que la mitad de la sesión se invierte en investigar.)
    """
    tiempo = float(getattr(star, 'time_to_eat', 1.0))
    inv_cost = float(getattr(star, 'investigation_energy_cost', 0.0))
    portion_investigacion = tiempo * 0.5
    return max(0.0, inv_cost * portion_investigacion)


def greedy_max_visits_enhanced(graph: Graph, source: int, donkey: Donkey, include_blocked: bool = False) -> Tuple[List[int], float]:
    """Versión mejorada del plan greedy que usa un presupuesto derivado del burro
    y descuenta un costo estático por visita de estrella.

    Costo por mover entre nodos = distancia del camino más corto.
    Al llegar a una estrella se descuenta estimate_static_visit_cost.
    Se detiene cuando no hay estrellas alcanzables dentro del presupuesto restante.
    """
    if source not in graph.stars:
        raise ValueError("source not in graph")
    budget = energy_budget_from_donkey(donkey)
    if budget <= 0:
        return [source], 0.0

    visited: set[int] = {source}
    route: List[int] = [source]
    used = 0.0
    current = source
    remaining: set[int] = set(graph.stars.keys()) - visited

    while remaining:
        dist, parent = dijkstra(graph, current, include_blocked=include_blocked)
        best_node = None
        best_cost = INF
        for v in list(remaining):
            move_cost = dist.get(v, INF)
            if move_cost is INF:
                continue
            visit_cost = estimate_static_visit_cost(graph.stars[v], donkey)
            total_cost = move_cost + visit_cost
            if total_cost < best_cost and used + total_cost <= budget:
                best_cost = total_cost
                best_node = v
        if best_node is None:
            break
        # apply move cost
        move_cost = dist[best_node]
        used += move_cost
        path = reconstruct_path(parent, best_node)
        if path and path[0] == current:
            for node in path[1:]:
                if node not in visited:
                    visited.add(node)
                route.append(node)
        else:
            route.append(best_node)
            visited.add(best_node)
        # apply visit cost
        star_obj = graph.stars[best_node]
        visit_cost = estimate_static_visit_cost(star_obj, donkey)
        used += visit_cost
        # Hypergiant effect: recharge 50% actual energy and double pasto stock (static impact)
        if getattr(star_obj, 'hypergiant', False):
            donkey.energia_pct = min(100.0, donkey.energia_pct * 1.5)
            donkey.pasto_kg *= 2.0
            # Recalcular potencial máximo para no exceder vida restante
            budget = energy_budget_from_donkey(donkey)
        current = best_node
        remaining.discard(best_node)
    return route, used


def greedy_max_visits_pure(graph: Graph, source: int, donkey: Donkey, include_blocked: bool = False) -> Tuple[List[int], float]:
    """Planner Fase 2 PURO (requisito 2):

    Calcula la ruta que permite conocer la mayor cantidad de estrellas usando SOLO
    los valores iniciales del burro, sin mutar su energía, pasto o salud durante el
    proceso de planificación y sin aplicar efectos de hipergigantes.

    Modelo:
      - Presupuesto base = energia_pct + pasto_kg * gain_per_kg (capped por vida restante)
      - Costo de mover entre nodos = distancia camino más corto (Dijkstra)
      - Costo de visita estática estimada = estimate_static_visit_cost(star, donkey)
      - No se recarga energía ni duplica pasto en hipergigantes (se ignoran efectos dinámicos).
      - Una estrella solo se considera una vez (nodo objetivo); se agregan intermedios del path sin penalización adicional
        excepto el costo de movimiento.

    Devuelve: (ruta, costo_total_usado)
    """
    if source not in graph.stars:
        raise ValueError("source not in graph")
    # Clonar snapshot del burro para evitar estado mutado previo
    donkey0 = replace(donkey)
    # Presupuestos separados
    energy_budget = compute_energy_budget(donkey0)
    life_budget = compute_life_budget(donkey0)
    if energy_budget <= 0 or life_budget <= 0:
        return [source], 0.0
    move_factor = movement_energy_factor(donkey0)

    visited: set[int] = {source}
    route: List[int] = [source]
    used_energy = 0.0
    used_life = 0.0
    current = source
    remaining: set[int] = set(graph.stars.keys()) - visited

    while remaining:
        dist, _parent = dijkstra(graph, current, include_blocked=include_blocked)
        best_node = None
        best_score = INF
        best_move_cost = 0.0
        best_visit_cost = 0.0
        for v in list(remaining):
            move_dist = dist.get(v, INF)
            if move_dist is INF:
                continue
            visit_cost = estimate_static_visit_cost(graph.stars[v], donkey0)
            # energía que costaría moverse (factor * distancia) + visita
            energy_need = move_factor * move_dist + visit_cost
            # vida que se consume solo por moverse
            life_need = move_dist
            # factibilidad con presupuestos restantes
            if used_energy + energy_need <= energy_budget and used_life + life_need <= life_budget:
                total = energy_need + life_need  # métrica simple combinada
                if total < best_score:
                    best_score = total
                    best_node = v
                    best_move_cost = move_dist
                    best_visit_cost = visit_cost
        if best_node is None:
            break
        # Avanzar: solo añadimos el destino (no intermedios) para evitar inflar conteo
        route.append(best_node)
        visited.add(best_node)
        used_energy += (move_factor * best_move_cost + best_visit_cost)
        used_life += best_move_cost
        current = best_node
        remaining.discard(best_node)
    # Se retorna la energía usada como métrica principal de costo (consistente con otros planners que retornan un único float)
    return route, used_energy


def max_stars_before_death(graph: Graph, source: int, donkey: Donkey, include_blocked: bool = False) -> Tuple[List[int], float]:
    """Modo 1: Mayor cantidad de estrellas antes de morir (solo valores iniciales).

    Reglas:
    - No hay investigación ni consumo/recuperación de energía durante el cálculo.
    - No se come pasto.
    - Solo se descuenta vida por desplazamientos (distancia recorrida).
    - Objetivo: visitar la mayor cantidad de estrellas posible antes de agotar la vida.

    Implementación:
    - Presupuesto = vida_restante = max(0, vida_maxima - edad).
    - Costo = distancia por caminos más cortos (Dijkstra), ignorando aristas bloqueadas por defecto.
    - Sin efectos de hipergigantes, ni mutaciones del burro.
    """
    if source not in graph.stars:
        raise ValueError("source not in graph")
    vida_restante = max(0.0, float(donkey.vida_maxima) - float(donkey.edad))
    if vida_restante <= 0:
        return [source], 0.0

    # Implementación exacta: Longest simple path (sin repetir ningún nodo, incluidos intermedios)
    # bajo presupuesto de vida (distancia). Usamos DFS con poda por vida y tiempo.
    start_time = time.time()
    TIME_LIMIT_MS = 1000  # límite suave para evitar explosión en grafos grandes

    def timed_out():
        return (time.time() - start_time) * 1000.0 >= TIME_LIMIT_MS

    best_route: List[int] = [source]
    best_cost: float = 0.0

    def dfs(current: int, visited: set[int], life_left: float, route: List[int], used_dist: float):
        """Explora rutas agregando nodos alcanzables vía caminos más cortos sin repetir intermedios."""
        nonlocal best_route, best_cost
        if timed_out():
            return
        # actualizar mejor (más nodos, o igual nodos con menor distancia empleada)
        if (len(route) > len(best_route)) or (len(route) == len(best_route) and used_dist < best_cost):
            best_route = route.copy()
            best_cost = used_dist
        # Calcular distancias desde current
        dist_map, parent = dijkstra(graph, current, include_blocked=include_blocked)
        # Generar candidatos alcanzables dentro de la vida restante
        candidates: List[Tuple[float,int,List[int]]] = []
        for v in graph.stars.keys():
            if v in visited:
                continue
            d = dist_map.get(v)
            if d is None or d > life_left:
                continue
            path = reconstruct_path(parent, v)
            if not path or path[0] != current:
                continue
            # intermedios
            interm = path[1:]
            # evitar repetir cualquier intermedio
            if any(n in visited for n in interm):
                continue
            candidates.append((d, v, interm))
        # Orden por distancia ascendente para intentar empaquetar más estrellas
        candidates.sort(key=lambda x: x[0])
        for d, v, interm in candidates:
            new_visited = visited.union(interm)
            new_route = route + interm
            dfs(v, new_visited, life_left - d, new_route, used_dist + d)

    dfs(source, {source}, vida_restante, [source], 0.0)
    return best_route, best_cost


def optimal_max_visits_life(
    graph: Graph,
    source: int,
    donkey: Donkey,
    include_blocked: bool = False,
    time_limit_ms: int = 1200,
) -> Tuple[List[int], float]:
    """Modo 2: Ruta óptima maximizando número de estrellas usando SOLO vida.

    - No se usa energía ni pasto ni investigación; no se modifican condiciones del burro.
    - Reglas: no repetir estrellas (ni como paso intermedio), costo=distancia (camino más corto),
      presupuesto = vida_restante.
    - Retorna (ruta, distancia_total).

    Implementación: backtracking con límite de tiempo.
    Nota: El problema es NP-difícil; este enfoque busca una ruta óptima o cuasi-óptima
    dentro del tiempo dado.
    """
    if source not in graph.stars:
        raise ValueError("source not in graph")
    vida_restante = max(0.0, float(donkey.vida_maxima) - float(donkey.edad))
    if vida_restante <= 0:
        return [source], 0.0

    start_time = time.time()
    def timed_out() -> bool:
        return (time.time() - start_time) * 1000.0 >= time_limit_ms

    best_route: List[int] = [source]
    best_cost: float = 0.0

    # Usaremos DFS con poda básica. "visited" evita repetir estrellas (incluye intermedias).
    def dfs(current: int, visited: set[int], life_left: float, route: List[int], used_dist: float):
        nonlocal best_route, best_cost
        if timed_out():
            # Al expirar tiempo, mantener mejor hasta ahora
            return
        # Actualizar mejor si mayor cantidad de nodos o igual con menor costo
        if (len(route) > len(best_route)) or (len(route) == len(best_route) and used_dist < best_cost):
            best_route = route.copy()
            best_cost = used_dist
        # Dijkstra desde current
        dist_map, parent = dijkstra(graph, current, include_blocked=include_blocked)
        # Generar candidatos ordenados por costo ascendente para empacar más nodos
        candidates: List[Tuple[float, int, List[int]]] = []
        for v in graph.stars.keys():
            if v in visited:
                continue
            d = dist_map.get(v)
            if d is None:
                continue
            if d > life_left:
                continue
            path = reconstruct_path(parent, v)
            if not path or path[0] != current:
                continue
            # No permitir repetir estrellas en el camino (además de current)
            path_nodes = path[1:]
            if any(n in visited for n in path_nodes):
                continue
            candidates.append((d, v, path))
        # Ordenar por distancia ascendente
        candidates.sort(key=lambda x: x[0])
        for d, v, path in candidates:
            # Aplicar movimiento y visitar intermedios como visitas válidas
            path_nodes = path[1:]  # nuevos nodos en orden
            # Avanzar estado
            new_visited = visited.union(path_nodes)
            new_route = route + path_nodes
            new_life = life_left - d
            new_used = used_dist + d
            dfs(v, new_visited, new_life, new_route, new_used)

    dfs(source, {source}, vida_restante, [source], 0.0)
    return best_route, best_cost


def optimal_max_visits_life_beam(
    graph: Graph,
    source: int,
    donkey: Donkey,
    include_blocked: bool = False,
    time_limit_ms: int = 1200,
    beam_width: int = 10,
) -> Tuple[List[int], float]:
    """Variación Modo 2 con Beam Search (rápida y robusta).

    - Reglas idénticas a optimal_max_visits_life: solo vida, sin repetir estrellas (incluye intermedias),
      costo=distancia (Dijkstra), presupuesto=vida_restante.
    - Usa beam search para explorar mejores candidatos primero y cortar el branching.
    - Retorna (ruta, distancia_total).
    """
    if source not in graph.stars:
        raise ValueError("source not in graph")
    vida_restante = max(0.0, float(donkey.vida_maxima) - float(donkey.edad))
    if vida_restante <= 0:
        return [source], 0.0

    start_time = time.time()
    def timed_out() -> bool:
        return (time.time() - start_time) * 1000.0 >= time_limit_ms

    from collections import namedtuple
    State = namedtuple("State", ["current", "visited", "route", "life_left", "used"])  # visited is frozenset

    best_route: List[int] = [source]
    best_cost: float = 0.0

    beam: List[State] = [State(source, frozenset([source]), [source], vida_restante, 0.0)]

    while beam and not timed_out():
        next_beam: List[State] = []
        # Expand each state
        for st in beam:
            # Update best
            if (len(st.route) > len(best_route)) or (len(st.route) == len(best_route) and st.used < best_cost):
                best_route, best_cost = st.route, st.used
            # Dijkstra from current
            dist_map, parent = dijkstra(graph, st.current, include_blocked=include_blocked)
            # Generate candidates reachable
            candidates: List[Tuple[float, int, List[int]]] = []
            for v in graph.stars.keys():
                if v in st.visited:
                    continue
                d = dist_map.get(v)
                if d is None or d > st.life_left:
                    continue
                path = reconstruct_path(parent, v)
                if not path or path[0] != st.current:
                    continue
                path_nodes = path[1:]
                # Avoid repeating any intermediate star
                if any((n in st.visited) for n in path_nodes):
                    continue
                candidates.append((d, v, path_nodes))
            # Sort by distance asc to pack more nodes
            candidates.sort(key=lambda x: x[0])
            # Keep top min(beam_width, len(candidates)) per state for diversity
            for d, v, path_nodes in candidates[:max(1, beam_width // max(1, len(beam)) )]:
                new_visited = set(st.visited)
                new_visited.update(path_nodes)
                new_route = st.route + path_nodes
                next_beam.append(State(v, frozenset(new_visited), new_route, st.life_left - d, st.used + d))
        if not next_beam:
            break
        # Rank states globally: by more nodes, then less distance used
        next_beam.sort(key=lambda s: (-len(s.route), s.used))
        beam = next_beam[:beam_width]

    return best_route, best_cost
