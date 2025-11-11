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
	# Estadísticas por estrella
	stars_log: List[Dict] = None  # se llena en runtime


class Simulator:
	"""Unified Simulator class (removed duplicate definition).

	Handles movement consumption, star visits (eat/investigate), hypergiant effects,
	and logging of events. Originally the file had two class Simulator definitions,
	which caused the second (without __init__) to shadow this one leading to
	`TypeError: Simulator() takes no arguments`. This merged version restores
	proper initialization and functionality.
	"""
	def __init__(self, graph: Graph, donkey: Donkey, route: List[int]):
		if not route:
			raise ValueError("Route must contain at least one star id")
		self.graph = graph
		self.donkey = donkey  # reference (planner may mutate donkey during planning)
		self.route = route
		self.index = 0  # índice de posición dentro de la ruta
		self._visited: set[int] = set()
		self.state = SimulationState(
			current_star=route[0],
			energy_pct=float(donkey.energia_pct),
			pasto_kg=float(donkey.pasto_kg),
			life_remaining=max(0.0, float(donkey.vida_maxima) - float(donkey.edad)),
			stars_log=[],
		)
		self.log: List[Dict] = []

	def _apply_hypergiant(self, star_id: int):
		star = self.graph.stars.get(star_id)
		if star and star.hypergiant:
			self.state.energy_pct = min(100.0, self.state.energy_pct * 1.5)
			self.state.pasto_kg *= 2.0

	def _consume_movement(self, distance: float):
		factor_salud = {
			"Excelente": 0.6,
			"Regular": 0.8,
			"Mala": 1.0,
			"Moribundo": 1.3,
			"Muerto": 0.0,
		}.get(self.donkey.salud, 1.0)
		self.state.life_remaining = max(0.0, self.state.life_remaining - distance)
		self.state.energy_pct = max(0.0, self.state.energy_pct - distance * factor_salud)

	def _visit_star(self, star_id: int):
		star = self.graph.stars.get(star_id)
		if not star:
			return
		before_energy = self.state.energy_pct
		before_pasto = self.state.pasto_kg
		before_life = self.state.life_remaining
		before_salud = self.donkey.salud
		# Tiempo total de la sesión en la estrella (heurística)
		session_time = max(0.5, float(getattr(star, 'time_to_eat', 1.0)) * 2.0)
		# División comer/investigar
		portion_eat = session_time * 0.5 if self.state.energy_pct < 50.0 else 0.0
		portion_invest = session_time - portion_eat
		kg_possible = portion_eat / max(0.1, star.time_to_eat)  # kg que puede comer
		kg_eaten = min(self.state.pasto_kg, kg_possible)
		gain_per_kg = self.donkey.energy_gain_per_kg()
		# Bonus de estrella
		gain_per_kg *= (1.0 + max(0.0, star.energy_bonus_pct))
		energy_gain = kg_eaten * gain_per_kg
		# Consumo de pasto
		self.state.pasto_kg = max(0.0, self.state.pasto_kg - kg_eaten)
		# Investigación consume energía
		inv_cost_unit = float(getattr(star, 'investigation_energy_cost', 0.0))
		invest_energy_cost = inv_cost_unit * portion_invest
		# Aplicar efectos
		self.state.energy_pct = max(0.0, min(100.0, self.state.energy_pct - invest_energy_cost + energy_gain))
		# Vida: aplicar delta (enfermedad/bono)
		life_delta = float(getattr(star, 'life_delta', 0.0))
		self.state.life_remaining = max(0.0, self.state.life_remaining + life_delta)
		# Posible cambio de salud
		self.donkey.apply_health_modifier(getattr(star, 'health_modifier', None))
		# Hipergigante
		self._apply_hypergiant(star_id)
		# Registrar log detallado
		self.state.stars_log.append({
			"star": star_id,
			"kg_eaten": kg_eaten,
			"energy_gain": energy_gain,
			"invest_cost": invest_energy_cost,
			"portion_eat": portion_eat,
			"portion_invest": portion_invest,
			"energy_before": before_energy,
			"pasto_before": before_pasto,
			"life_before": before_life,
			"salud_before": before_salud,
			"energy_after": self.state.energy_pct,
			"pasto_after": self.state.pasto_kg,
			"life_after": self.state.life_remaining,
			"salud_after": self.donkey.salud,
			"life_delta": life_delta,
			"hypergiant": bool(star.hypergiant),
		})

	def step(self) -> SimulationState:
		if self.state.finished or self.state.dead:
			return self.state
		if self.index >= len(self.route) - 1:
			# Final visit only (si no se ha procesado)
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
		# Arrive and visit (solo primera vez cuenta como visita)
		self.index += 1
		self.state.current_star = dst
		if dst not in self._visited:
			self._visit_star(dst)
			self._visited.add(dst)
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

