"""Basic step-by-step simulator skeleton for Phase 3.

The simulator advances through a planned route of star IDs, applying movement
costs, eating, investigation, hypergiant effects, and allows dynamic edge
blocking decisions externally.

This is an initial scaffold; logic is intentionally simplified and will be
refined (diseases / bonuses, user edits per star, time management).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Optional

try:
	from src.core.models import Graph, Donkey
except ModuleNotFoundError:
	from core.models import Graph, Donkey

try:
	from src.core.planner import dijkstra, reconstruct_path, estimate_static_visit_cost
except ModuleNotFoundError:
	from core.planner import dijkstra, reconstruct_path, estimate_static_visit_cost


@dataclass
class SimulationState:
	current_star: int
	energy_pct: float
	pasto_kg: float
	life_remaining: float  # años luz restantes
	tick: int = 0
	finished: bool = False
	dead: bool = False


class Simulator:
	def __init__(self, graph: Graph, donkey: Donkey, route: List[int]):
		if not route:
			raise ValueError("Route must contain at least one star id")
		self.graph = graph
		# Copy donkey primitive state
		self.donkey = donkey
		self.route = route
		self.index = 0  # index within route
		self.state = SimulationState(
			current_star=route[0],
			energy_pct=float(donkey.energia_pct),
			pasto_kg=float(donkey.pasto_kg),
			life_remaining=max(0.0, float(donkey.vida_maxima) - float(donkey.edad)),
		)
		self.log: List[Dict] = []

	def _apply_hypergiant(self, star_id: int):
		star = self.graph.stars.get(star_id)
		if star and star.hypergiant:
			# Recharge 50% of current energy (cap 100%) and double pasto
			self.state.energy_pct = min(100.0, self.state.energy_pct * 1.5)
			self.state.pasto_kg *= 2.0

	def _consume_movement(self, distance: float):
		# Movement consumes both life and energy proportionally to distance.
		self.state.life_remaining = max(0.0, self.state.life_remaining - distance)
		self.state.energy_pct = max(0.0, self.state.energy_pct - distance)  # placeholder model

	def _visit_star(self, star_id: int):
		star = self.graph.stars.get(star_id)
		if not star:
			return
		# Investigative cost minus potential eating recovery
		cost = estimate_static_visit_cost(star, self.donkey)
		# Apply cost directly on energy_pct (bounded)
		self.state.energy_pct = max(0.0, self.state.energy_pct - cost)
		# Eating recovery if below threshold handled inside cost function; we could adjust pasto consumption later.
		self._apply_hypergiant(star_id)

	def step(self) -> SimulationState:
		if self.state.finished or self.state.dead:
			return self.state
		if self.index >= len(self.route) - 1:
			# Final visit only
			self._visit_star(self.route[self.index])
			self.state.finished = True
			self._log_event("finish", self.route[self.index])
			return self.state
		src = self.route[self.index]
		dst = self.route[self.index + 1]
		# shortest path distance src->dst (ignoring blocked edges)
		dist_map, parent = dijkstra(self.graph, src)
		distance = dist_map.get(dst)
		if distance is None:
			# unreachable due to dynamic blocking
			self.state.finished = True
			self._log_event("blocked_route", src)
			return self.state
		# Move
		self._consume_movement(distance)
		# Arrive and visit
		self.index += 1
		self.state.current_star = dst
		self._visit_star(dst)
		self.state.tick += 1
		# Check death conditions
		if self.state.energy_pct <= 0 or self.state.life_remaining <= 0:
			self.state.dead = True
			self.state.finished = True
			self._log_event("death", dst)
		else:
			self._log_event("visit", dst, extra={"distance": distance})
		return self.state

	def run_all(self) -> SimulationState:
		while not self.state.finished and not self.state.dead:
			self.step()
		return self.state

	def _log_event(self, kind: str, star_id: int, extra: Optional[Dict] = None):
		star = self.graph.stars.get(star_id)
		entry = {
			"tick": self.state.tick,
			"event": kind,
			"star": star_id,
			"energy_pct": self.state.energy_pct,
			"pasto_kg": self.state.pasto_kg,
			"life_remaining": self.state.life_remaining,
			"hypergiant": bool(star.hypergiant) if star else False,
		}
		if extra:
			entry.update(extra)
		self.log.append(entry)

	def export_log(self) -> List[Dict]:
		return self.log

