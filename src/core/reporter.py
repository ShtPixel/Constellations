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
    final_section: Dict[str, Any] = {}
    stars_detail: List[Dict[str, Any]] = []
    aggregates = {
        "total_kg_eaten": 0.0,
        "total_energy_gain": 0.0,
        "total_invest_cost": 0.0,
        "total_life_delta": 0.0,
    }
    term_reason = "planned_only"

    if simulation_state:
        # Determine termination reason
        if getattr(simulation_state, 'dead', False):
            term_reason = "death"
        elif getattr(simulation_state, 'finished', False):
            # Check if blocked in log
            blocked = any((isinstance(e, dict) and e.get("event") == "blocked_route") for e in (simulation_log or []))
            term_reason = "blocked" if blocked else "finished"
        final_section = {
            "final_energy_pct": simulation_state.energy_pct,
            "final_pasto_kg": simulation_state.pasto_kg,
            "final_life_remaining": simulation_state.life_remaining,
            "ticks": simulation_state.tick,
            "dead": simulation_state.dead,
            "finished": simulation_state.finished,
            "termination_reason": term_reason,
            "visited_unique": len(getattr(simulation_state, 'stars_log', []) or []),
        }
        for entry in (simulation_state.stars_log or []):
            sid = entry.get("star")
            st = graph.stars.get(sid)
            life_delta = float(entry.get("life_delta", 0.0))
            kg_eaten = float(entry.get("kg_eaten", 0.0))
            energy_gain = float(entry.get("energy_gain", 0.0))
            invest_cost = float(entry.get("invest_cost", 0.0))
            aggregates["total_kg_eaten"] += kg_eaten
            aggregates["total_energy_gain"] += energy_gain
            aggregates["total_invest_cost"] += invest_cost
            aggregates["total_life_delta"] += life_delta
            stars_detail.append({
                "star": sid,
                "label": st.label if st else f"Star{sid}",
                "hypergiant": bool(st.hypergiant) if st else False,
                "life_delta": life_delta,
                "kg_eaten": kg_eaten,
                "energy_gain": energy_gain,
                "invest_cost": invest_cost,
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
    log_section: List[Dict[str, Any]] = []
    if simulation_log:
        if len(simulation_log) > 200:
            trimmed = simulation_log[:100] + [{"event": "...trimmed...", "count": len(simulation_log)-200}] + simulation_log[-100:]
        else:
            trimmed = simulation_log
        log_section = trimmed
    base["final"] = final_section
    base["aggregates"] = aggregates
    base["termination_reason"] = term_reason
    base["stars_visit_detail"] = stars_detail
    base["simulation_log"] = log_section
    return base
