"""Route report generator.

Exports a JSON-compatible dict summarizing a planned route.
"""
from __future__ import annotations
from typing import List, Dict, Any
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
