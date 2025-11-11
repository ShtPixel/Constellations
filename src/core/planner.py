from __future__ import annotations
from typing import Dict, Optional, Tuple, List
import heapq

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


def estimate_static_visit_cost(star, donkey: Donkey) -> float:
    """Costo energético estático estimado al visitar una estrella (fase 2).

    Usa investigación_energy_cost (energía por unidad de tiempo de investigación) y time_to_eat.
    Modelo simplificado:
    - Se asume que el burro dedica 50% del time_to_eat a comer si energia_pct < 50.
    - Cada kg consumido en esa fracción recupera gain_per_kg de energía, amortiguando el costo.
    - Cost_investigacion = investigation_energy_cost * (time_to_eat * 0.5)
    - Recuperación potencial (si energia_pct < 50) = min(pasto_disponible_para_comer, time_to_eat * 0.5) * gain_per_kg
    Retorna costo_neto = max(0, cost_investigacion - recuperacion).
    """
    tiempo = float(getattr(star, 'time_to_eat', 1.0))
    inv_cost = float(getattr(star, 'investigation_energy_cost', 0.0))
    portion_investigacion = tiempo * 0.5
    cost_investigacion = inv_cost * portion_investigacion
    gain_per_kg = donkey.energy_gain_per_kg()
    recuperacion = 0.0
    if donkey.energia_pct < 50.0:
        # Asumir 1 kg por unidad de tiempo como simplificación
        kg_comidos = portion_investigacion  # tiempo*0.5 unidades -> kg
        recuperacion = kg_comidos * gain_per_kg
    return max(0.0, cost_investigacion - recuperacion)


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
    # Presupuesto puro
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
        best_total = INF
        for v in list(remaining):
            move_cost = dist.get(v, INF)
            if move_cost is INF:
                continue
            visit_cost = estimate_static_visit_cost(graph.stars[v], donkey)
            total_cost = move_cost + visit_cost
            if total_cost < best_total and used + total_cost <= budget:
                best_total = total_cost
                best_node = v
        if best_node is None:
            break
        # aplicar costo de movimiento
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
        # aplicar costo estático estimado de visita (sin mutaciones nuevas)
        visit_cost = estimate_static_visit_cost(graph.stars[best_node], donkey)
        used += visit_cost
        current = best_node
        remaining.discard(best_node)
    return route, used
