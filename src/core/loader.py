# src/core/loader.py
import json
import os
from typing import Tuple, Dict, Any
import warnings

try:
    from src.core.models import Donkey, Graph, Star
except ModuleNotFoundError:
    from core.models import Donkey, Graph, Star

DEFAULT_BURRO_KEYS = {
    "burroenergiaInicial": 100,
    "estadoSalud": "Excelente",
    "pasto": 300,
    "number": None,
    "startAge": 0,
    "deathAge": 1000
}

class Loader:
    def __init__(self, path_burro: str = "data/burro.json", path_galaxies: str = "data/galaxies.json"):
        self.path_burro = path_burro
        self.path_galaxies = path_galaxies

    def load(self) -> Tuple[Donkey, Graph]:
        donkey = self._load_burro()
        graph = self._load_galaxies()
        return donkey, graph

    def _load_burro(self) -> Donkey:
        if not os.path.exists(self.path_burro):
            raise FileNotFoundError(f"burro.json not found at {self.path_burro}")
        with open(self.path_burro, "r", encoding="utf-8") as f:
            data = json.load(f)

        # fill defaults if missing
        for k, v in DEFAULT_BURRO_KEYS.items():
            data.setdefault(k, v)

        donkey = Donkey(
            id=data.get("number"),
            nombre=data.get("nombre", "Burro"),
            salud=data.get("estadoSalud", "Excelente"),
            energia_pct=float(data.get("burroenergiaInicial", 100)),
            pasto_kg=float(data.get("pasto", 0)),
            edad=float(data.get("startAge", 0)),
            vida_maxima=float(data.get("deathAge", 0))
        )
        return donkey

    def _load_galaxies(self) -> Graph:
        if not os.path.exists(self.path_galaxies):
            raise FileNotFoundError(f"galaxies.json not found at {self.path_galaxies}")
        with open(self.path_galaxies, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "constellations" not in data:
            raise KeyError("galaxies.json must contain 'constellations' array")

        graph = Graph()
        # temp index to collect stars and track occurrences
        occurrences = {}  # id -> list of (constellation_name, raw_star_dict)
        raw_stars = {}

        for const in data["constellations"]:
            cname = const.get("name", "Unnamed")
            for s in const.get("stars", []):
                sid = s.get("id")
                if sid is None:
                    raise KeyError(f"Star without 'id' in constellation {cname}")
                # normalize coordinates: accept either x,y or coordenates
                if "x" in s and "y" in s:
                    x = float(s["x"])
                    y = float(s["y"])
                elif "coordenates" in s and isinstance(s["coordenates"], dict):
                    x = float(s["coordenates"].get("x", 0))
                    y = float(s["coordenates"].get("y", 0))
                else:
                    x = float(s.get("x", 0))
                    y = float(s.get("y", 0))

                # normalize links: accept 'links' or 'linkedTo'
                raw_links = s.get("links", s.get("linkedTo", []))
                normalized_links = []
                for l in raw_links:
                    # support both {to:..} and {starId:..}
                    to = l.get("to", l.get("starId"))
                    if to is None:
                        warnings.warn(f"Link without target in star {sid} (const {cname}), skipping")
                        continue
                    dist = float(l.get("distance", l.get("dist", 0)))
                    blocked = bool(l.get("blocked", False))
                    normalized_links.append({"to": int(to), "distance": dist, "blocked": blocked})

                star_dict = {
                    "id": int(sid),
                    "label": s.get("label", f"Star{sid}"),
                    "x": x,
                    "y": y,
                    "radius": float(s.get("radius", 0.5)),
                    "timeToEat": float(s.get("timeToEat", 1.0)),
                    "amountOfEnergy": float(s.get("amountOfEnergy", 1.0)),
                    "investigationEnergyCost": float(s.get("investigationEnergyCost", s.get("investigation_energy_cost", 0.0))),
                    "hypergiant": bool(s.get("hypergiant", False)),
                    "shared": bool(s.get("shared", False)),
                    "links": normalized_links,
                    "constellation": cname
                }
                # register
                raw_stars[sid] = star_dict
                occurrences.setdefault(sid, []).append((cname, star_dict))

        # Build Star objects and add to graph
        for sid, items in occurrences.items():
            # choose the first entry for base data, but merge constellation refs
            base = items[0][1]
            # Shared must only be true if star appears in more than one constellation
            computed_shared = len(items) > 1
            if base.get("shared", False) and not computed_shared:
                warnings.warn(
                    f"Star {sid} is marked 'shared' in JSON but only appears in one constellation; ignoring flag.")

            star = Star(
                id=int(base["id"]),
                label=base["label"],
                x=base["x"],
                y=base["y"],
                radius=base["radius"],
                time_to_eat=base["timeToEat"],
                amount_of_energy=base["amountOfEnergy"],
                investigation_energy_cost=base["investigationEnergyCost"],
                hypergiant=base["hypergiant"],
                shared=computed_shared
            )
            # add constellation names y registra en cada constelación usando Graph
            for cname, sd in items:
                graph.add_star(star, constellation_name=cname)

        # Now add edges from the normalized links
        for sid, items in occurrences.items():
            # links defined for this star (take them from the first occurrence available)
            star_info = items[0][1]
            for l in star_info["links"]:
                to = int(l["to"])
                dist = float(l["distance"])
                blocked = bool(l.get("blocked", False))
                if to not in graph.stars:
                    raise KeyError(f"Star {sid} has link to missing star {to}")
                graph.add_edge(sid, to, dist, blocked=blocked)

        # Ensure bidirectionality
        graph.ensure_bidirectional(default_blocked=False)

        # Perform some checks and warnings
        #  - hypergiant count per constellation
        hg_counts = graph.hypergiant_counts()
        for cname, count in hg_counts.items():
            if count > 2:
                warnings.warn(f"Constellation '{cname}' has {count} hypergiants (max recommended 2)")

        #  - coordinates overlapping
        coords = {}
        for s in graph.stars.values():
            key = (int(s.x), int(s.y))
            coords.setdefault(key, []).append(s.id)
        for key, sids in coords.items():
            if len(sids) > 1:
                warnings.warn(f"Stars {sids} have same integer coordinates {key}; they may overlap on screen")

        # Final consistency pass: recompute 'shared' flags from actual memberships
        try:
            graph.recompute_shared_flags()
        except Exception:
            # If method doesn't exist or fails, skip silently (backward-compat)
            pass

        return graph
