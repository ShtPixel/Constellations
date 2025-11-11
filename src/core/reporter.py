"""Route report generator.

Exports a JSON-compatible dict summarizing a planned route.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional
import json
import time

try:
    from src.core.models import Graph, Donkey
except ModuleNotFoundError:
    from core.models import Graph, Donkey


def build_route_report(graph: Graph, donkey: Donkey, route: List[int], total_cost: float) -> Dict[str, Any]:
    stars_section = []
    for idx, sid in enumerate(route):
        st = graph.stars.get(sid)
        if not st:
            continue
        stars_section.append({
            "index": idx,
            "id": sid,
            "label": st.label,
            "constellations": list(st.constellations),
            "hypergiant": bool(st.hypergiant),
            "shared": bool(st.shared),
        })
    return {
        "generated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "donkey": {
            "id": donkey.id,
            "salud": donkey.salud,
            "energia_pct_inicial": donkey.energia_pct,
            "pasto_kg_inicial": donkey.pasto_kg,
            "edad_inicial": donkey.edad,
            "vida_maxima": donkey.vida_maxima,
        },
        "route_length": len(route),
        "total_cost_estimate": total_cost,
        "stars": stars_section,
    }


def save_route_report(path: str, report: Dict[str, Any]) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def build_final_report(graph: Graph, donkey: Donkey, route: List[int],
                       simulation_state: Optional[Any], simulation_log: Optional[List[Dict]]) -> Dict[str, Any]:
    """Construye un reporte final enriquecido con datos de simulación.

    Incluye:
      - Ruta y datos básicos (similar a build_route_report)
      - Estado final (energía, vida restante, pasto, salud, muerto/finished)
      - Estadísticas por estrella visitada (último registro en stars_log)
      - Log de eventos (visit, death, finish, blocked_route) recortado si excede 200 entradas.
    """
    base = build_route_report(graph, donkey, route, total_cost=0.0)
    final_section = {}
    stars_detail = []
    # Conjuntos/orden de constelaciones visitadas según ruta
    constellations_order: List[str] = []
    seen_const: set[str] = set()
    for sid in route:
        st = graph.stars.get(sid)
        if not st:
            continue
        for cname in getattr(st, 'constellations', []) or []:
            if cname not in seen_const:
                seen_const.add(cname)
                constellations_order.append(cname)
    if simulation_state:
        final_section = {
            "final_energy_pct": simulation_state.energy_pct,
            "final_pasto_kg": simulation_state.pasto_kg,
            "final_life_remaining": simulation_state.life_remaining,
            "ticks": simulation_state.tick,
            "dead": simulation_state.dead,
            "finished": simulation_state.finished,
            "visited_unique": len(getattr(simulation_state, 'stars_log', []) or []),
        }
        for entry in (simulation_state.stars_log or []):
            sid = entry.get("star")
            st = graph.stars.get(sid)
            stars_detail.append({
                "star": sid,
                "label": st.label if st else f"Star{sid}",
                "hypergiant": bool(st.hypergiant) if st else False,
                "life_delta": entry.get("life_delta", 0.0),
                "kg_eaten": entry.get("kg_eaten", 0.0),
                "energy_gain": entry.get("energy_gain", 0.0),
                "invest_cost": entry.get("invest_cost", 0.0),
                "portion_eat": entry.get("portion_eat", 0.0),
                "portion_invest": entry.get("portion_invest", 0.0),
                "energy_before": entry.get("energy_before"),
                "energy_after": entry.get("energy_after"),
                "pasto_before": entry.get("pasto_before"),
                "pasto_after": entry.get("pasto_after"),
                "life_before": entry.get("life_before"),
                "life_after": entry.get("life_after"),
                "salud_before": entry.get("salud_before"),
                "salud_after": entry.get("salud_after"),
            })
        # Totales agregados
        try:
            total_kg = sum(d.get('kg_eaten', 0.0) for d in stars_detail)
            total_gain = sum(d.get('energy_gain', 0.0) for d in stars_detail)
            total_invest = sum(d.get('invest_cost', 0.0) for d in stars_detail)
            total_eat_t = sum(d.get('portion_eat', 0.0) for d in stars_detail)
            total_inv_t = sum(d.get('portion_invest', 0.0) for d in stars_detail)
            final_section["totals"] = {
                "kg_eaten": total_kg,
                "energy_gain": total_gain,
                "invest_cost": total_invest,
                "time_eating": total_eat_t,
                "time_investigating": total_inv_t,
            }
        except Exception:
            pass
    log_section = []
    if simulation_log:
        if len(simulation_log) > 200:
            # mantener primeros y últimos 50 eventos para contexto
            trimmed = simulation_log[:100] + [{"event": "...trimmed...", "count": len(simulation_log)-200}] + simulation_log[-100:]
        else:
            trimmed = simulation_log
        log_section = trimmed
    base["final"] = final_section
    base["stars_visit_detail"] = stars_detail
    base["simulation_log"] = log_section
    base["constellations_visited"] = constellations_order
    return base

def save_final_report(path: str, report: Dict[str, Any]) -> None:
    """Guardar reporte final en JSON."""
    save_route_report(path, report)
