from typing import Dict, Tuple, Set
import json
import math
import os
import time

try:
	import pygame
except Exception:  
	pygame = None

try:
	from src.core.planner import (
		dijkstra,
		reconstruct_path,
		greedy_max_visits_enhanced,
		max_stars_before_death,
		optimal_max_visits_life,
		optimal_max_visits_life_beam,
		energy_budget_from_donkey,
	)
except ModuleNotFoundError:
	from core.planner import (
		dijkstra,
		reconstruct_path,
		greedy_max_visits_enhanced,
		max_stars_before_death,
		optimal_max_visits_life,
		optimal_max_visits_life_beam,
		energy_budget_from_donkey,
	)

try:
	from src.core.reporter import build_route_report, save_route_report
except ModuleNotFoundError:
	from core.reporter import build_route_report, save_route_report
try:
	from src.core.reporter import build_final_report
except ModuleNotFoundError:
	from core.reporter import build_final_report

try:
	from src.render.report_viewer import ReportViewer
except ModuleNotFoundError:
	from render.report_viewer import ReportViewer

try:
	from src.core.simulator import Simulator
except ModuleNotFoundError:
	from core.simulator import Simulator

try:
	from src.sound.sound_manager import SoundManager
except ModuleNotFoundError:
	from sound.sound_manager import SoundManager

# Manifest opcional (assets)
try:
	from src.core.assets import AssetManifest, load_pygame_image, load_pygame_font
except ModuleNotFoundError:
	try:
		from core.assets import AssetManifest, load_pygame_image, load_pygame_font
	except ModuleNotFoundError:
		AssetManifest = None  # type: ignore
		def load_pygame_image(path):
			return None
		def load_pygame_font(path, size):
			return None


class GraphRenderer:

	def __init__(self, graph, width=None, height=None, min_size=None, margin=None, pixel_coords: bool = True, ui_config=None, donkey=None):
		self.graph = graph
		self.donkey = donkey
		# Require UI config (JSON) as the single source of truth
		if not ui_config:
			raise ValueError("Falta 'ui' en burro.json o no se pasó ui_config al renderer")
		ui = ui_config or {}
		win_cfg = ui.get("window", {})
		if "width" not in win_cfg or "height" not in win_cfg:
			raise ValueError("La configuración UI debe incluir window.width y window.height en burro.json")
		cfg_w = win_cfg.get("width")
		cfg_h = win_cfg.get("height")
		cfg_min = win_cfg.get("minViewport", 0)
		cfg_margin = win_cfg.get("margin", 0)
		w = cfg_w if width is None else width
		h = cfg_h if height is None else height
		ms = cfg_min if min_size is None else min_size
		mg = cfg_margin if margin is None else margin
		self.width = max(int(w), int(ms))
		self.height = max(int(h), int(ms))
		self.margin = int(mg)
		self.pixel_coords = bool(pixel_coords)
		colors_cfg = ui.get("colors", {})
		# Solo JSON: si faltan claves críticas, error explícito
		required_colors = ["BACKGROUND", "EDGE", "EDGE_BLOCKED", "SHARED", "GRID_COLOR", "ID_COLOR"]
		missing = [k for k in required_colors if k not in colors_cfg]
		if missing:
			raise ValueError(f"Faltan colores en ui.colors: {missing}")
		self.bg_color = tuple(colors_cfg["BACKGROUND"])  # type: ignore
		self.edge_color = tuple(colors_cfg["EDGE"])  # type: ignore
		self.edge_blocked_color = tuple(colors_cfg["EDGE_BLOCKED"])  # type: ignore
		self.shared_color = tuple(colors_cfg["SHARED"])  # type: ignore
		self.grid_color = tuple(colors_cfg["GRID_COLOR"])  # type: ignore
		self.id_color = tuple(colors_cfg["ID_COLOR"])  # type: ignore
		grid_cfg = ui.get("grid", {})
		if "spacing" not in grid_cfg:
			raise ValueError("Falta ui.grid.spacing en burro.json")
		self.grid_spacing = int(grid_cfg.get("spacing"))
		self.external_palette = ui.get("PALETTE")
		self.constellation_colors = {}
		self.selected_origin = None
		self.mouse_pos = (0, 0)
		self.hover_edge = None
		self.show_path_to_hover = False
		self.dists = {}
		self.parents = {}
		self.planned_route = []
		self.font = None
		self.small_font = None
		self.last_message = None
		self.last_plan_mode = None  # 'enhanced' | 'pure' | None
		# Simulation fields
		self.simulator = None
		self.sim_running = False
		self.sim_speed = 1.0  # steps per second
		self._last_step_time = 0.0
		self._sound = SoundManager()
		# Animation state (visual recorrido paso a paso)
		self._anim_active = False
		self._anim_index = 0  # índice de tramo (leg) actual en planned_route
		self._anim_src = None
		self._anim_dst = None
		self._anim_start_ms = 0.0
		self._anim_duration_ms = 0.0
		# Dwell/estadia visual en estrella tras llegar (para mostrar tiempo X)
		self._dwell_active = False
		self._dwell_star = None
		self._dwell_start_ms = 0.0
		self._dwell_duration_ms = 0.0
		# Marcadores de animación y muerte
		self._last_anim_pos = None
		self._death_marker = None
		# Edición de efectos por estrella
		self._edit_mode = False
		self._edit_star = None
		# Assets (manifest opcional)
		self.assets = AssetManifest() if 'AssetManifest' in globals() and AssetManifest else None
		self._bg_image_original = None
		self._bg_image_scaled = None
		# Imágenes (opcional): estrellas y burro
		self._img_star = None
		self._img_star_hg = None
		self._img_donkey = None
		self._img_cache: Dict[Tuple[str, int, int], any] = {}
		# Factores de escala visual (ajustables)
		self.STAR_BASE_ACTIVE = 14  # antes 10
		self.STAR_BASE_INACTIVE = 10  # antes 7
		self.STAR_RADIUS_MULT_ACTIVE = 20  # antes 14
		self.STAR_RADIUS_MULT_INACTIVE = 14  # antes 9
		self.DONKEY_BASE_SIZE = 40  # antes 28
		# UI/HUD
		self.show_help = True
		self._last_message_snapshot = None
		self._message_time = 0
		# Cámara (zoom/pan) y enfoque de constelación
		self.cam_scale_mul = 1.0
		self.cam_off_x = 0.0
		self.cam_off_y = 0.0
		self._panning = False
		self._pan_last = (0, 0)
		self.active_constellation = None  # nombre o None
		self.show_grid = True
		# Modo turbo (acelera animaciones)
		self.turbo = False
		# Auto-planificar con click izquierdo (por defecto desactivado)
		self.auto_plan_on_click = False
		# Hipersalto (UI selección y animación warp)
		self.hyperjump_active = False
		self.hyperjump_options = []  # lista de (sid, label, const)
		self.hyperjump_index = 0
		self._warp_next = False
		# Control: abrir automáticamente selector al llegar a hipergigante
		self.auto_open_hyperjump = False
		self._compute_palette()
		self._compute_transform()
		# Top bars baseline and alerts
		self._max_life = float(getattr(self.donkey, 'vida_maxima', 100.0)) - float(getattr(self.donkey, 'edad', 0.0)) if self.donkey else 100.0
		self._max_pasto = float(getattr(self.donkey, 'pasto_kg', 100.0)) if self.donkey else 100.0
		self._alerts: list[dict] = []  # {text, color, t0, dur}
		self._pre_step_energy: float | None = None
		self._pre_step_life: float | None = None
		# Modo enfoque de ruta (activado al planificar algunos modos)
		self._focus_mode = False
		# Panel de edición al llegar a una estrella (entrada de valores)
		self._arrival_input_active = False
		self._arrival_star_id = None
		self._arrival_input_value = ""
		self._arrival_fields = ["life_delta", "investigation_energy_cost", "energy_bonus_pct"]
		self._arrival_field_index = 0
		# Otros flags/UI
		self._hyper_modal_active = False
		self._live_report_enabled = False
		self._edge_events = []
		self._clean_mode = False
		# Reporte en pantalla (modal inline)
		self._report_modal_active = False
		self._report_lines: list[str] = []
		self._report_scroll = 0
		# Reporte automático al finalizar el recorrido
		self.auto_show_report_on_finish = True
		self._report_shown_once = False
		# Modal de carga de archivos (carga automática desde GUI)
		self._data_modal_active = False
		self._data_files_burro: list[str] = []
		self._data_files_galaxies: list[str] = []
		self._data_sel_index_burro = 0
		self._data_sel_index_galaxies = 0
		self._data_focus_section = 'burro'  # 'burro' o 'galaxies'
		self._data_last_load_msg = None

	def _force_death_route(self) -> Tuple[list[int], float]:
		"""Genera una ruta mínima hacia la estrella más cercana aunque exceda la vida.

		Devuelve (ruta, distancia). Si no hay aristas disponibles, retorna ([], 0).
		"""
		try:
			if self.selected_origin is None:
				return [], 0.0
			origin = int(self.selected_origin)
			# Distancias desde el origen
			dist_map, parent = dijkstra(self.graph, origin)
			# Encontrar el destino más cercano distinto del origen
			best_v = None
			best_d = float('inf')
			for v, d in dist_map.items():
				if v == origin:
					continue
				if d < best_d:
					best_d = d
					best_v = v
			if best_v is None or best_d == float('inf'):
				return [], 0.0
			path = reconstruct_path(parent, best_v)
			return path, float(best_d)
		except Exception:
			return [], 0.0

	def _compute_palette(self):
		# Use palette strictly from JSON (ui_config). If missing, require explicit mapping
		names = list(self.graph.constellations.keys())
		palette = self.external_palette or []
		if not palette:
			# if no palette is provided, assign a neutral gray to all
			for name in names:
				self.constellation_colors[name] = (180, 180, 180)
			return
		for i, name in enumerate(names):
			self.constellation_colors[name] = tuple(palette[i % len(palette)])  # type: ignore

		# Removed unused HSV conversion method

	def _compute_transform(self):
		if self.pixel_coords:
			# No scaling: JSON coordinates are in pixels already
			self.scale = 1.0
			self.offset_x = self.margin
			self.offset_y = self.margin
			return
		# Map world (stars x,y) to screen coordinates (auto-fit)
		xs = [s.x for s in self.graph.stars.values()] or [0]
		ys = [s.y for s in self.graph.stars.values()] or [0]
		min_x, max_x = min(xs), max(xs)
		min_y, max_y = min(ys), max(ys)
		span_x = max(1.0, max_x - min_x)
		span_y = max(1.0, max_y - min_y)
		# Enforce mínimo 200x200 unidades: expandir bounds si es menor
		MIN_SPAN = 200.0
		if span_x < MIN_SPAN:
			pad = (MIN_SPAN - span_x) / 2.0
			min_x -= pad
			max_x += pad
			span_x = MIN_SPAN
		if span_y < MIN_SPAN:
			pad = (MIN_SPAN - span_y) / 2.0
			min_y -= pad
			max_y += pad
			span_y = MIN_SPAN
		draw_w = self.width - 2 * self.margin
		draw_h = self.height - 2 * self.margin
		sx = draw_w / span_x
		sy = draw_h / span_y
		self.scale = min(sx, sy) if (sx > 0 and sy > 0) else 1.0
		self.offset_x = self.margin - self.scale * min_x + (draw_w - self.scale * span_x) / 2
		self.offset_y = self.margin - self.scale * min_y + (draw_h - self.scale * span_y) / 2

	def world_to_screen(self, x: float, y: float) -> Tuple[int, int]:
		sc = self.scale * self.cam_scale_mul
		sx = int(sc * x + self.offset_x + self.cam_off_x)
		sy = int(sc * y + self.offset_y + self.cam_off_y)
		# Pygame's Y axis grows downward already; no flip needed
		return sx, sy

	def screen_to_world(self, sx: int, sy: int) -> Tuple[float, float]:
		sc = self.scale * self.cam_scale_mul
		if sc == 0:
			return 0.0, 0.0
		x = (sx - self.offset_x - self.cam_off_x) / sc
		y = (sy - self.offset_y - self.cam_off_y) / sc
		return x, y

	def draw(self, screen):
		# Fondo: imagen si está disponible, si no color sólido
		if self._bg_image_original:
			if (not self._bg_image_scaled) or (self._bg_image_scaled.get_size() != (self.width, self.height)):
				try:
					self._bg_image_scaled = pygame.transform.smoothscale(self._bg_image_original, (self.width, self.height))
				except Exception:
					self._bg_image_scaled = None
			if self._bg_image_scaled:
				screen.blit(self._bg_image_scaled, (0, 0))
			else:
				screen.fill(self.bg_color)
		else:
			screen.fill(self.bg_color)

		# Optional background grid (screen-space), to help spatial orientation
		if self.show_grid:
			self._draw_grid(screen)
		# Top stat bars
		self._draw_top_bars(screen)
		# Draw edges (unique undirected) with focus mode dimming
		route_edges: Set[Tuple[int, int]] = set()
		if self.planned_route and len(self.planned_route) > 1:
			for i in range(len(self.planned_route) - 1):
				a = self.planned_route[i]
				b = self.planned_route[i + 1]
				route_edges.add((min(a, b), max(a, b)))
		edge_layer = None
		if self._focus_mode and self.planned_route:
			try:
				edge_layer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
			except Exception:
				edge_layer = None
		drawn: Set[Tuple[int, int]] = set()
		for u, nbrs in self.graph.adjacency.items():
			for v, edge in nbrs.items():
				key = (min(u, v), max(u, v))
				if key in drawn:
					continue
				drawn.add(key)
				su = self.graph.stars.get(u)
				sv = self.graph.stars.get(v)
				if not su or not sv:
					continue
				x1, y1 = self.world_to_screen(su.x, su.y)
				x2, y2 = self.world_to_screen(sv.x, sv.y)
				# Enfoque por constelación
				if self.active_constellation:
					in_active = (self.active_constellation in su.constellations) and (self.active_constellation in sv.constellations)
					base_color = self.edge_blocked_color if edge.blocked else self.edge_color
					color = base_color if in_active else (90, 90, 110)
					width = 3 if in_active else 1
				else:
					color = self.edge_blocked_color if edge.blocked else self.edge_color
					width = 2
				pygame.draw.line(screen, color, (x1, y1), (x2, y2), width)
		# Draw stars (usar sprite si existe, si no, fallback a círculo)
		for cname, const in self.graph.constellations.items():
			color = self.constellation_colors.get(cname, (180, 180, 180))
			for sid in const.stars:
				star = self.graph.stars.get(sid)
				if not star:
					continue
				x, y = self.world_to_screen(star.x, star.y)
				active = (self.active_constellation is None) or (self.active_constellation in star.constellations)
				# Tamaño base en píxeles influenciado por radio y foco
				# Tamaño aumentado configurable
				base_px = self.STAR_BASE_ACTIVE if active else self.STAR_BASE_INACTIVE
				size = max(10, int(base_px + star.radius * (self.STAR_RADIUS_MULT_ACTIVE if active else self.STAR_RADIUS_MULT_INACTIVE)))
				if (star.hypergiant and self._img_star_hg) or (self._img_star):
					img_key = ("star_hg" if (star.hypergiant and self._img_star_hg) else "star", size, size)
					# Cache de escalado
					img_scaled = self._img_cache.get(img_key)
					if not img_scaled:
						src_img = self._img_star_hg if (star.hypergiant and self._img_star_hg) else self._img_star
						try:
							img_scaled = pygame.transform.smoothscale(src_img, (size, size)) if src_img else None
						except Exception:
							img_scaled = None
						if img_scaled:
							self._img_cache[img_key] = img_scaled
					if img_scaled:
						rect = img_scaled.get_rect(center=(x, y))
						screen.blit(img_scaled, rect.topleft)
						continue
				# Fallback: círculo
				cc = color if active else (120, 120, 130)
				pygame.draw.circle(screen, cc, (x, y), size // 2)

		# Overlay: resaltar estrellas que pertenecen a varias constelaciones (rojo)
		for star in self.graph.stars.values():
			multi = False
			try:
				multi = len(getattr(star, 'constellations', [])) > 1
			except Exception:
				multi = False
			if multi:
				x, y = self.world_to_screen(star.x, star.y)
				r = max(3, int(3 + star.radius * 6))
				pygame.draw.circle(screen, (255, 60, 60), (x, y), r + 3, 3)
		# Overlay adicional (compat): si viene flag JSON 'shared', dibujar anillo azul
		for star in self.graph.stars.values():
			if getattr(star, "shared", False):
				x, y = self.world_to_screen(star.x, star.y)
				r = max(2, int(2 + star.radius * 5))
				pygame.draw.circle(screen, self.shared_color, (x, y), r + 3, 2)

		# Draw origin highlight
		if self.selected_origin is not None and self.selected_origin in self.graph.stars:
			so = self.graph.stars[self.selected_origin]
			x, y = self.world_to_screen(so.x, so.y)
			pygame.draw.circle(screen, (255, 220, 0), (x, y), 10, 2)  # amarillo origen

		# Show path to hovered star if enabled and computed
		if self.show_path_to_hover and self.selected_origin is not None:
			hover_sid = self._star_at_pixel(*self.mouse_pos, threshold=12)
			if hover_sid is not None and hover_sid in self.parents:
				path = reconstruct_path(self.parents, hover_sid)
				for i in range(len(path) - 1):
					a = path[i]
					b = path[i + 1]
					if a in self.graph.stars and b in self.graph.stars:
						sa = self.graph.stars[a]
						sb = self.graph.stars[b]
						x1, y1 = self.world_to_screen(sa.x, sa.y)
						x2, y2 = self.world_to_screen(sb.x, sb.y)
						pygame.draw.line(screen, (0, 255, 0), (x1, y1), (x2, y2), 4)
		elif self.hover_edge is not None:
			# Highlight hovered edge when no full selection
			u, v = self.hover_edge
			if u in self.graph.stars and v in self.graph.stars:
				su = self.graph.stars[u]
				sv = self.graph.stars[v]
				x1, y1 = self.world_to_screen(su.x, su.y)
				x2, y2 = self.world_to_screen(sv.x, sv.y)
				pygame.draw.line(screen, (200, 120, 255), (x1, y1), (x2, y2), 3)

		# Draw star ID labels on top of geometry (but under HUD)
		self._draw_star_labels(screen)

		# Draw planned route segmented and moving marker
		if self.planned_route and len(self.planned_route) > 1:
			visited_count = 0
			if self.simulator:
				visited_count = max(0, int(self._anim_index))
			# Detect unreachable next leg (dynamic block)
			self._unreachable_flag = False
			if self.simulator and not self.simulator.state.finished:
				leg = self.simulator.index
				if leg < len(self.planned_route) - 1:
					src = self.planned_route[leg]
					dst = self.planned_route[leg + 1]
					# comprobar si hay camino ignorando bloqueadas
					try:
						dist_map, _p = dijkstra(self.graph, src)
						if dst not in dist_map:
							self._unreachable_flag = True
					except Exception:
						pass
			# Drawing legs with styling
			for i in range(len(self.planned_route) - 1):
				a = self.planned_route[i]
				b = self.planned_route[i + 1]
				if a not in self.graph.stars or b not in self.graph.stars:
					continue
				sa = self.graph.stars[a]
				sb = self.graph.stars[b]
				x1, y1 = self.world_to_screen(sa.x, sa.y)
				x2, y2 = self.world_to_screen(sb.x, sb.y)
				# Determine style bucket
				if i < visited_count:
					color = (30, 160, 90)  # visited subdued green
					width = 2
					alpha = 160
				elif i == visited_count:
					color = (255, 200, 40)  # current bright yellow
					width = 5
					alpha = 255
				elif i == visited_count + 1:
					color = (0, 210, 190)  # next leg teal
					width = 4
					alpha = 230
				elif i == visited_count + 2:
					color = (0, 170, 220)  # next+1
					width = 3
					alpha = 210
				else:
					# farther futures
					color = (120, 140, 150)
					width = 2
					alpha = 110
				# Clean mode hides far futures
				if self._clean_mode and i > visited_count + 2:
					continue
				# Unreachable highlight (first pending only)
				if self._unreachable_flag and i == visited_count:
					color = (255, 70, 70)
					width = 6
					alpha = 255
				# Simplified: draw solid line for all legs (no dashed/arrow toggles)
				pygame.draw.line(screen, color, (x1, y1), (x2, y2), width)
			# Step numbers (compact: show only vicinity unless no simulator)
			if self.small_font:
				for idx, sid in enumerate(self.planned_route):
					if self._clean_mode and self.simulator and (idx < visited_count - 1 or idx > visited_count + 3):
						continue
					st = self.graph.stars.get(sid)
					if not st:
						continue
					x, y = self.world_to_screen(st.x, st.y)
					col = (200, 230, 255) if idx >= visited_count else (140, 180, 170)
					img = self.small_font.render(str(idx), True, col)
					screen.blit(img, (x + 6, y + 6))
			# Moving marker if animating
			if self._anim_active and self._anim_src is not None and self._anim_dst is not None:
				src = self.graph.stars.get(self._anim_src)
				dst = self.graph.stars.get(self._anim_dst)
				if src and dst:
					now = pygame.time.get_ticks()
					t = 0.0 if self._anim_duration_ms <= 0 else max(0.0, min(1.0, (now - self._anim_start_ms) / self._anim_duration_ms))
					x1, y1 = self.world_to_screen(src.x, src.y)
					x2, y2 = self.world_to_screen(dst.x, dst.y)
					# Si el tramo excede la vida restante, limitar el avance visual a la fracción de vida
					death_frac = 1.0
					try:
						st = self.simulator.state if self.simulator else None
						if st and self._anim_src in self.graph.adjacency and self._anim_dst in self.graph.adjacency[self._anim_src]:
							leg_dist = float(self.graph.adjacency[self._anim_src][self._anim_dst].distance)
							if leg_dist > 0 and st.life_remaining < leg_dist:
								death_frac = max(0.0, min(1.0, st.life_remaining / leg_dist))
					except Exception:
						death_frac = 1.0
					t_eff = min(t, death_frac)
					x = int(x1 + (x2 - x1) * t_eff)
					y = int(y1 + (y2 - y1) * t_eff)
					# draw partial progress line on current segment
					pygame.draw.line(screen, (255, 215, 0), (x1, y1), (x, y), 5)
					# Donkey sprite si disponible, si no marcador
					self._last_anim_pos = (x, y)
					if self._img_donkey:
						# Escala dinámica del burro considerando zoom de cámara
						burro_size = int(self.DONKEY_BASE_SIZE * max(0.6, min(1.8, self.cam_scale_mul)))
						key = ("donkey", burro_size, burro_size)
						img = self._img_cache.get(key)
						if not img:
							try:
								img = pygame.transform.smoothscale(self._img_donkey, (burro_size, burro_size))
							except Exception:
								img = None
							if img:
								self._img_cache[key] = img
						if img:
							rect = img.get_rect(center=(x, y))
							screen.blit(img, rect.topleft)
						else:
							pygame.draw.circle(screen, (255, 255, 0), (x, y), 6)
					else:
						pygame.draw.circle(screen, (255, 255, 0), (x, y), 6)
			else:
				# Fallback marker when not animating: draw at current star or origin
				if self.simulator and self.simulator.state and self.simulator.state.dead and self._death_marker and self._img_donkey:
					# Dibujar burro patas arriba en la posición de muerte
					x, y = self._death_marker
					burro_size = int(self.DONKEY_BASE_SIZE * max(0.6, min(1.8, self.cam_scale_mul)))
					rot_key = ("donkey_rot90", burro_size, burro_size)
					rot_img = self._img_cache.get(rot_key)
					if not rot_img:
						try:
							base_key = ("donkey", burro_size, burro_size)
							base_img = self._img_cache.get(base_key)
							if not base_img and self._img_donkey:
								base_img = pygame.transform.smoothscale(self._img_donkey, (burro_size, burro_size))
							rot_img = pygame.transform.rotate(base_img, 90) if base_img else None
						except Exception:
							rot_img = None
						if rot_img:
							self._img_cache[rot_key] = rot_img
					if rot_img:
						rect = rot_img.get_rect(center=(x, y))
						screen.blit(rot_img, rect.topleft)
					else:
						pygame.draw.circle(screen, (255, 255, 0), (x, y), 6)
				elif self.simulator and self.simulator.state and self.simulator.state.current_star in self.graph.stars:
					cs = self.graph.stars[self.simulator.state.current_star]
					x, y = self.world_to_screen(cs.x, cs.y)
					if self._img_donkey:
						burro_size = int(self.DONKEY_BASE_SIZE * max(0.6, min(1.8, self.cam_scale_mul)))
						key = ("donkey", burro_size, burro_size)
						img = self._img_cache.get(key)
						if not img:
							try:
								img = pygame.transform.smoothscale(self._img_donkey, (burro_size, burro_size))
							except Exception:
								img = None
							if img:
								self._img_cache[key] = img
						if img:
							rect = img.get_rect(center=(x, y))
							screen.blit(img, rect.topleft)
						else:
							pygame.draw.circle(screen, (255, 255, 0), (x, y), 6)
					else:
						pygame.draw.circle(screen, (255, 255, 0), (x, y), 6)
				elif self.selected_origin is not None and self.selected_origin in self.graph.stars:
					cs = self.graph.stars[self.selected_origin]
					x, y = self.world_to_screen(cs.x, cs.y)
					if self._img_donkey:
						burro_size = int(self.DONKEY_BASE_SIZE * max(0.6, min(1.8, self.cam_scale_mul)))
						key = ("donkey", burro_size, burro_size)
						img = self._img_cache.get(key)
						if not img:
							try:
								img = pygame.transform.smoothscale(self._img_donkey, (burro_size, burro_size))
							except Exception:
								img = None
							if img:
								self._img_cache[key] = img
						if img:
							rect = img.get_rect(center=(x, y))
							screen.blit(img, rect.topleft)
						else:
							pygame.draw.circle(screen, (255, 255, 0), (x, y), 6)
					else:
						pygame.draw.circle(screen, (255, 255, 0), (x, y), 6)

		# Dwell visualization: show progress ring on current star during estadía
		if self._dwell_active and self._dwell_star is not None and self._dwell_star in self.graph.stars:
			st = self.graph.stars[self._dwell_star]
			x, y = self.world_to_screen(st.x, st.y)
			r = 16
			rect = pygame.Rect(x - r, y - r, 2 * r, 2 * r)
			elapsed = max(0.0, pygame.time.get_ticks() - self._dwell_start_ms)
			p = 0.0 if self._dwell_duration_ms <= 0 else max(0.0, min(1.0, elapsed / self._dwell_duration_ms))
			# arc from -90 degrees (upwards), angle = 2*pi*p
			start_ang = -math.pi / 2
			end_ang = start_ang + 2 * math.pi * p
			pygame.draw.arc(screen, (255, 200, 0), rect, start_ang, end_ang, 4)

		# HUD mejorado
		self._draw_hud(screen)
		# Modal de selección de archivos (GUI)
		if getattr(self, '_data_modal_active', False):
			self._draw_data_modal(screen)

		# Modal de selección de hipersalto si está activo
		if self.hyperjump_active:
			self._draw_hyperjump_modal(screen)

		# Overlay edición de estrella
		if self._edit_mode and self._edit_star is not None and self._edit_star in self.graph.stars and self.small_font:
			st = self.graph.stars[self._edit_star]
			x, y = self.world_to_screen(st.x, st.y)
			pygame.draw.circle(screen, (255, 0, 0), (x, y), 12, 2)
			panel = [
				f"Edit Star {st.id}",
				f"lifeDelta={getattr(st, 'life_delta', 0.0):.2f}",
				f"healthMod={getattr(st, 'health_modifier', None)}",
				f"energyBonusPct={getattr(st, 'energy_bonus_pct', 0.0):.2f}",
				"J/K: lifeDelta -/+ 0.5 | M: ciclo salud",
				"U/I: energyBonus -/+ 0.05 | E: salir",
			]
			rendered = [self.small_font.render(t, True, (255,255,255)) for t in panel]
			pw = max(r.get_width() for r in rendered)
			ph = sum(r.get_height()+2 for r in rendered)
			bx = min(self.width - pw - 10, max(10, x + 14))
			by = min(self.height - ph - 10, max(10, y - ph - 14))
			pygame.draw.rect(screen, (0,0,0), (bx-4, by-4, pw+8, ph+8))
			cy = by
			for r in rendered:
				screen.blit(r, (bx, cy))
				cy += r.get_height()+2

		# Panel de edición de vida al llegar a una estrella (modal centrado)
		if self._arrival_input_active and (self.font or self.small_font):
			f = self.font or self.small_font
			field_names = {
				"life_delta": "Δ Vida (años luz)",
				"investigation_energy_cost": "Costo Energía Invest.",
				"energy_bonus_pct": "Bonus Energía (%)",
			}
			current_field = self._arrival_fields[self._arrival_field_index]
			header = field_names.get(current_field, current_field)
			lines = [
				"Edición de efectos en estrella",
				f"Estrella: {self._arrival_star_id}",
				f"Campo: {header}",
				f"Valor: {self._arrival_input_value}",
				"Enter=Guardar  Esc=Cancelar  Backspace=Borrar  [ / ] Cambiar campo",
			]
			rendered = [f.render(t, True, (255,255,255)) for t in lines]
			pw = max(r.get_width() for r in rendered)
			ph = sum(r.get_height()+6 for r in rendered) + 24
			bx = max(20, (self.width - pw)//2 - 12)
			by = max(20, (self.height - ph)//2 - 12)
			pygame.draw.rect(screen, (0,0,0), (bx-8, by-8, pw+32, ph+32))
			pygame.draw.rect(screen, (120,120,120), (bx-8, by-8, pw+32, ph+32), 2)
			y = by
			for r in rendered:
				screen.blit(r, (bx, y))
				y += r.get_height()+6
			# Caja de entrada destacada
			ibox_w = max(160, pw)
			ibox_h = 28
			pygame.draw.rect(screen, (20,20,20), (bx, y+4, ibox_w, ibox_h))
			pygame.draw.rect(screen, (0,200,120), (bx, y+4, ibox_w, ibox_h), 1)
			val_surf = f.render(self._arrival_input_value or "0", True, (0, 255, 180))
			screen.blit(val_surf, (bx+6, y+6))

		# Overlay de alertas efímeras
		self._draw_alerts(screen)

		# Hypergiant selection overlay
		if self._hyper_modal_active:
			self._draw_hyper_modal(screen)

		# Overlay de reporte en vivo
		if self._live_report_enabled:
			self._draw_live_report(screen)

		# Modal de reporte final inline
		if self._report_modal_active:
			self._draw_report_modal(screen)

	def _draw_grid(self, screen):
		"""Draw a simple screen-space grid inside the margin box."""
		if self.grid_spacing <= 0:
			return
		x0, y0 = self.margin, self.margin
		x1, y1 = self.width - self.margin, self.height - self.margin
		# Vertical lines
		x = x0
		while x <= x1:
			pygame.draw.line(screen, self.grid_color, (x, y0), (x, y1), 1)
			x += self.grid_spacing
		# Horizontal lines
		y = y0
		while y <= y1:
			pygame.draw.line(screen, self.grid_color, (x0, y), (x1, y), 1)
			y += self.grid_spacing

	def _draw_star_labels(self, screen):
		"""Draw star IDs near their positions for easier identification."""
		if not self.font and not self.small_font:
			return
		label_font = self.small_font or self.font
		for sid, star in self.graph.stars.items():
			x, y = self.world_to_screen(star.x, star.y)
			text = str(sid)
			# Simple shadow for readability
			img_shadow = label_font.render(text, True, (0, 0, 0))
			screen.blit(img_shadow, (x + 1, y - 1))
			img = label_font.render(text, True, self.id_color)
			screen.blit(img, (x, y - 2))

	def _draw_text_block(self, screen, lines: list[str], topleft: Tuple[int, int]):
		x, y = topleft
		for line in lines:
			img = self.font.render(line, True, (230, 230, 230))
			screen.blit(img, (x, y))
			y += img.get_height() + 2

	def _draw_legend(self, screen, topleft: Tuple[int, int]):
		x, y = topleft
		for name, color in self.constellation_colors.items():
			pygame.draw.rect(screen, color, (x, y, 14, 14))
			img = self.small_font.render(name, True, (220, 220, 220)) if self.small_font else self.font.render(name, True, (220, 220, 220))
			screen.blit(img, (x + 18, y - 2))
			y += 18

	def _draw_progress_bar(self, screen, rect, pct, fg=(0,200,255), bg=(40,40,60), border=(180,180,200)):
		pct = max(0.0, min(1.0, pct))
		pygame.draw.rect(screen, bg, rect)
		fill = rect.copy()
		fill.width = int(rect.width * pct)
		pygame.draw.rect(screen, fg, fill)
		pygame.draw.rect(screen, border, rect, 1)

	def _draw_panel(self, screen, rect, title=None):
		pygame.draw.rect(screen, (10,10,16,200), rect)
		pygame.draw.rect(screen, (80,80,100), rect, 1)
		if title and self.small_font:
			cap = self.small_font.render(title, True, (230,230,230))
			screen.blit(cap, (rect.x + 8, rect.y + 6))

	def _draw_hud(self, screen):
		if not (self.font or self.small_font):
			return
		pad = 10
		# Top-left status panel (dinámico si hay info de última estrella)
		panel_w = 280
		extra_h = 0
		last_visit = None
		if self.simulator and self.simulator.state and self.simulator.state.stars_log:
			last_visit = self.simulator.state.stars_log[-1]
			extra_h = 70  # espacio para 4-5 líneas adicionales
		panel_h = 132 + extra_h
		panel = pygame.Rect(pad, pad, panel_w, panel_h)
		self._draw_panel(screen, panel, title="Estado")
		y = panel.y + 26
		# Origin and plan
		origin_txt = f"Origen: {self.selected_origin}" if self.selected_origin is not None else "Origen: (click en estrella)"
		_mode_map = {
			'pure': 'Puro',
			'enhanced': 'Mejorado',
			'mode1': 'Modo 1',
			'mode2': 'Modo 2',
			'mode2_beam': 'Modo 2++',
		}
		plan_txt = f"Plan: {_mode_map.get(self.last_plan_mode, '-')}"
		coord_txt = "Coords: Pixel" if self.pixel_coords else "Coords: Escala"
		for t in (origin_txt, plan_txt, coord_txt):
			img = self.small_font.render(t, True, (235,235,235)) if self.small_font else self.font.render(t, True, (235,235,235))
			screen.blit(img, (panel.x + 10, y)); y += img.get_height() + 4
		# Budget and route
		budget = energy_budget_from_donkey(self.donkey) if self.donkey else 0.0
		route_len = len(self.planned_route) if self.planned_route else 0
		img = (self.small_font or self.font).render(f"Presupuesto≈ {budget:.1f} | Ruta: {route_len}", True, (200,220,255))
		screen.blit(img, (panel.x + 10, y)); y += img.get_height() + 6
		# Detalle de la última visita a estrella (si existe)
		if last_visit is not None:
			try:
				sid = int(last_visit.get('star', -1))
				st_obj = self.graph.stars.get(sid)
				label = st_obj.label if st_obj else str(sid)
				enet = float(last_visit.get('energy_net', 0.0))
				kgc = float(last_visit.get('pasto_consumido', last_visit.get('kg_eaten', 0.0)))
				life_b = float(last_visit.get('life_before', 0.0))
				life_a = float(last_visit.get('life_after', life_b))
				life_d = float(last_visit.get('life_delta', 0.0))
				sb = str(last_visit.get('salud_before', ''))
				sa = str(last_visit.get('salud_after', ''))
				hg = bool(last_visit.get('hypergiant', False))
				lines = [
					f"Estrella: {sid} ({label})",
					f"ΔE {enet:+.1f}% | Pasto -{kgc:.1f}kg",
					f"Vida {life_b:.1f}→{life_a:.1f} ({life_d:+.1f})",
					f"Salud {sb}→{sa} | Hipergigante: {'Sí' if hg else 'No'}",
				]
				for t in lines:
					img = (self.small_font or self.font).render(t, True, (200,220,200))
					screen.blit(img, (panel.x + 10, y)); y += img.get_height() + 2
			except Exception:
				pass
		# Donkey stats panel
		dpanel = pygame.Rect(panel.right + pad, pad, 340, 132)
		self._draw_panel(screen, dpanel, title="Burro")
		cy = dpanel.y + 28
		# Salud
		salud = self.donkey.salud if self.donkey else "-"
		img = (self.small_font or self.font).render(f"Salud: {salud}", True, (235,235,235))
		screen.blit(img, (dpanel.x + 10, cy)); cy += img.get_height() + 6
		# Energy bar
		E = (self.simulator.state.energy_pct if (self.simulator) else (self.donkey.energia_pct if self.donkey else 0.0))
		bar = pygame.Rect(dpanel.x + 10, cy, dpanel.width - 20, 16)
		self._draw_progress_bar(screen, bar, E/100.0, fg=(30,200,120));
		etxt = (self.small_font or self.font).render(f"Energía {E:.1f}%", True, (15,15,18))
		screen.blit(etxt, (bar.x + 8, bar.y - 1)); cy += 24
		# Life bar
		if self.donkey:
			vida_total = max(0.1, float(self.donkey.vida_maxima) - float(self.donkey.edad))
			L = (self.simulator.state.life_remaining if self.simulator else vida_total)
			bar2 = pygame.Rect(dpanel.x + 10, cy, dpanel.width - 20, 16)
			self._draw_progress_bar(screen, bar2, min(1.0, L/vida_total), fg=(200,180,30))
			ltxt = (self.small_font or self.font).render(f"Vida {L:.1f}/{vida_total:.1f}", True, (15,15,18))
			screen.blit(ltxt, (bar2.x + 8, bar2.y - 1)); cy += 24
		# Pasto
		P = (self.simulator.state.pasto_kg if self.simulator else (self.donkey.pasto_kg if self.donkey else 0.0))
		img = (self.small_font or self.font).render(f"Pasto: {P:.1f} kg", True, (235,235,235))
		screen.blit(img, (dpanel.x + 10, cy)); cy += img.get_height() + 2
		# Sim panel
		spanel = pygame.Rect(dpanel.right + pad, pad, 260, 132)
		self._draw_panel(screen, spanel, title="Simulación")
		sy = spanel.y + 28
		if self.simulator:
			st = self.simulator.state
			status = "RUN" if self.sim_running and not st.finished else ("DONE" if st.finished else "PAUSE")
			for t in (f"Estado: {status}", f"Actual: {st.current_star}"):
				img = (self.small_font or self.font).render(t, True, (235,235,235))
				screen.blit(img, (spanel.x + 10, sy)); sy += img.get_height() + 4
			# Resumen de última visita (energía neta y pasto consumido)
			if st.stars_log:
				last = st.stars_log[-1]
				try:
					enet = float(last.get("energy_net", 0.0))
					kgc = float(last.get("pasto_consumido", last.get("kg_eaten", 0.0)))
					msg = f"Últ. visita: ΔE {enet:+.1f}% | Pasto -{kgc:.1f}kg"
					img = (self.small_font or self.font).render(msg, True, (200,220,200))
					screen.blit(img, (spanel.x + 10, sy)); sy += img.get_height() + 4
				except Exception:
					pass
			if self._dwell_active and self._dwell_star is not None:
				elapsed = max(0.0, pygame.time.get_ticks() - self._dwell_start_ms)
				p = 0.0 if self._dwell_duration_ms <= 0 else max(0.0, min(1.0, elapsed / self._dwell_duration_ms))
				img = (self.small_font or self.font).render(f"Estadía {self._dwell_star}: {p*100:.0f}%", True, (200,200,120))
				screen.blit(img, (spanel.x + 10, sy))
		else:
			img = (self.small_font or self.font).render("(Sin simulación)", True, (150,150,160))
			screen.blit(img, (spanel.x + 10, sy))
		# Legend panel (bottom-left)
		leg_h = min(200, 20 * (len(self.constellation_colors) or 1) + 16)
		lpanel = pygame.Rect(pad, self.height - leg_h - pad, 280, leg_h)
		self._draw_panel(screen, lpanel, title="Constelaciones")
		self._draw_legend(screen, (lpanel.x + 10, lpanel.y + 28))
		# Help panel (bottom-right)
		if self.show_help:
			hpanel = pygame.Rect(self.width - 500 - pad, self.height - 180 - pad, 500, 180)
			self._draw_panel(screen, hpanel, title="Ayuda (/? para ocultar)")
			help_lines = [
				"Click: Origen | C: Limpiar | B: Bloquear arista | Shift+G: Grid",
				"G: Ruta óptima (Modo 2) | Y: Óptima++ (Beam) | H: Máx. estrellas (Modo 1)",
				"Wheel: Zoom | RMB/MMB Drag: Pan | Quitar enfoque const: `",
				"TAB: Enfocar constelación | Space/N: Play/Paso | +/-: Velocidad | X: Turbo | A: Auto-plan click",
				"Shift+J: Auto-hipersalto | J: Selector hipersalto (en hipergigante)",
				"E: Editar estrella (J/K,U/I,M) | S: Guardar edits",
				"O: Recargar JSON (Shift abre selector) | F1/F2: Cargar burro/galaxias (Shift=selector interno)",
				"F3: Selector interno de archivos (burro/galaxies) | F: Coords | V: Live report",
				"[ / ]: Ajustar vida disponible (Shift = paso grande)",
				"T: Reporte | L: Exportar Log | ESC: Salir",
			]
			y = hpanel.y + 28
			for line in help_lines:
				img = (self.small_font or self.font).render(line, True, (230,230,230))
				screen.blit(img, (hpanel.x + 10, y)); y += img.get_height() + 4
		# Toast message (bottom-center)
		self._draw_toast(screen)

	def _draw_toast(self, screen):
		# Track message change time
		now = pygame.time.get_ticks()
		if self.last_message != self._last_message_snapshot:
			self._last_message_snapshot = self.last_message
			self._message_time = now
		if not self.last_message:
			return
		if now - self._message_time > 4000:
			return
		msg = self.last_message
		img = (self.small_font or self.font).render(msg, True, (245,245,245))
		w, h = img.get_width() + 20, img.get_height() + 12
		rect = pygame.Rect((self.width - w)//2, self.height - h - 12, w, h)
		pygame.draw.rect(screen, (0,0,0,180), rect)
		pygame.draw.rect(screen, (90,90,120), rect, 1)
		screen.blit(img, (rect.x + 10, rect.y + 6))

	def _star_at_pixel(self, px: int, py: int, threshold: int = 10) -> int | None:
		closest = None
		best_d2 = threshold * threshold
		for sid, star in self.graph.stars.items():
			sx, sy = self.world_to_screen(star.x, star.y)
			dx, dy = px - sx, py - sy
			d2 = dx * dx + dy * dy
			if d2 <= best_d2:
				best_d2 = d2
				closest = sid
		return closest

	@staticmethod
	def _point_segment_distance(px: int, py: int, x1: int, y1: int, x2: int, y2: int) -> float:
		# Distance from point to line segment
		vx, vy = x2 - x1, y2 - y1
		wx, wy = px - x1, py - y1
		len2 = vx * vx + vy * vy
		if len2 == 0:
			return math.hypot(px - x1, py - y1)
		t = max(0.0, min(1.0, (wx * vx + wy * vy) / len2))
		projx, projy = x1 + t * vx, y1 + t * vy
		return math.hypot(px - projx, py - projy)

	def _nearest_edge(self, px: int, py: int, threshold: float = 8.0) -> Tuple[int, int] | None:
		best = None
		best_d = threshold
		drawn: Set[Tuple[int, int]] = set()
		for u, nbrs in self.graph.adjacency.items():
			for v in nbrs.keys():
				key = (min(u, v), max(u, v))
				if key in drawn:
					continue
				drawn.add(key)
				su = self.graph.stars.get(u)
				sv = self.graph.stars.get(v)
				if not su or not sv:
					continue
				x1, y1 = self.world_to_screen(su.x, su.y)
				x2, y2 = self.world_to_screen(sv.x, sv.y)
				d = self._point_segment_distance(px, py, x1, y1, x2, y2)
				if d <= best_d:
					best_d = d
					best = (u, v)
		return best

	def _open_hyperjump_selector(self):
		"""Construye opciones de hipersalto desde la constelación actual hacia otras.

		Selecciona como candidatos todas las estrellas de constelaciones distintas a la(s)
		constelación(es) de la estrella actual, excluyendo ya visitadas en la ruta hasta el índice actual.
		"""
		if not self.simulator:
			return False
		cur = self.simulator.state.current_star
		star = self.graph.stars.get(cur)
		if not star:
			return False
		# Conjunto de constelaciones actuales (tratar constelación como galaxia)
		current_consts = set(getattr(star, 'constellations', []))
		# Derivar conjunto aproximado de visitadas desde la ruta hasta el índice actual
		visited = set(self.planned_route[: self.simulator.index + 1])
		candidates = []
		for cname, const in self.graph.constellations.items():
			if cname in current_consts:
				continue
			for sid in const.stars:
				if sid in visited:
					continue
				st = self.graph.stars.get(sid)
				if not st:
					continue
				label = getattr(st, 'label', str(sid))
				candidates.append((sid, label, cname))
		# Ordenar para UI estable
		candidates.sort(key=lambda x: (x[2], x[1]))
		self.hyperjump_options = candidates
		self.hyperjump_index = 0
		self.hyperjump_active = True
		self.sim_running = False
		return True

	def _apply_hyperjump_selection(self):
		if not (self.simulator and self.hyperjump_active and self.hyperjump_options):
			self.hyperjump_active = False
			return
		cur = self.simulator.state.current_star
		sel_sid, label, cname = self.hyperjump_options[self.hyperjump_index]
		# Insertar destino justo después del actual en la ruta planificada
		ins_at = self.simulator.index + 1
		self.planned_route = self.planned_route[:ins_at] + [sel_sid] + self.planned_route[ins_at:]
		# Marcar el tramo (cur -> sel_sid) como warp sin costo en el simulador
		try:
			self.simulator.warp_pairs.add((cur, sel_sid))
		except Exception:
			pass
		# Efecto visual de warp (animación muy corta)
		self._warp_next = True
		self.hyperjump_active = False
		self.last_message = f"Hipersalto a {label} ({cname})"
		# Reanudar
		self.sim_running = True

	def _draw_hyperjump_modal(self, screen):
		# Fondo translúcido
		over = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
		over.fill((0, 0, 0, 160))
		screen.blit(over, (0, 0))
		w, h = 520, 360
		rect = pygame.Rect((self.width - w)//2, (self.height - h)//2, w, h)
		self._draw_panel(screen, rect, title="Selecciona destino de hipersalto (↑/↓, Enter, Esc)")
		if not self.hyperjump_options:
			msg = (self.small_font or self.font).render("No hay destinos disponibles", True, (230,230,230))
			screen.blit(msg, (rect.x + 16, rect.y + 40))
			return
		# Mostrar lista con resaltado
		start_y = rect.y + 40
		max_rows = 12
		# Calcular ventana de scroll simple en base al índice
		top = max(0, self.hyperjump_index - max_rows//2)
		view = self.hyperjump_options[top: top + max_rows]
		for i, (sid, label, cname) in enumerate(view):
			y = start_y + i * 24
			text = f"[{sid}] {label}  -  {cname}"
			color = (30,220,120) if (top + i) == self.hyperjump_index else (230,230,230)
			img = (self.small_font or self.font).render(text, True, color)
			screen.blit(img, (rect.x + 16, y))

	def run(self):
		if pygame is None:
			raise RuntimeError(
				"Pygame no está disponible. Instálalo con: pip install pygame"
			)
		pygame.init()
		screen = pygame.display.set_mode((self.width, self.height))
		pygame.display.set_caption("Constellations Viewer")
		# Fuente desde manifest si existe, con fallback
		ui_font_path = (self.assets.get_font("ui") if self.assets else None)
		font_main = (load_pygame_font(ui_font_path, 18) if ui_font_path else None)
		font_small = (load_pygame_font(ui_font_path, 12) if ui_font_path else None)
		self.font = font_main or pygame.font.SysFont(None, 18)
		self.small_font = font_small or pygame.font.SysFont(None, 12)
		# Imagen de fondo desde manifest (se dibuja debajo de todo)
		bg_path = (self.assets.get_image("background") if self.assets else None)
		if bg_path:
			try:
				img = load_pygame_image(bg_path)
				self._bg_image_original = img.convert() if img else None
			except Exception:
				self._bg_image_original = None
		else:
			self._bg_image_original = None
		# Carga de imágenes (solo burro). Las estrellas se dibujan como círculos para evitar imagen encima.
		if self.assets:
			try:
				p_donkey = self.assets.get_image("donkey")
				if p_donkey:
					img = load_pygame_image(p_donkey)
					self._img_donkey = img.convert_alpha() if img else None
			except Exception:
				self._img_donkey = None
		clock = pygame.time.Clock()
		running = True
		while running:
			for event in pygame.event.get():
				# Modal de selección de archivos tiene máxima prioridad si activo
				if getattr(self, '_data_modal_active', False):
					if event.type == pygame.KEYDOWN:
						if event.key in (pygame.K_ESCAPE,):
							self._data_modal_active = False
							self.last_message = "Carga cancelada"
							continue
						elif event.key == pygame.K_TAB:
							self._data_focus_section = 'galaxies' if self._data_focus_section == 'burro' else 'burro'
							continue
						elif event.key in (pygame.K_UP, pygame.K_w):
							if self._data_focus_section == 'burro':
								self._data_sel_index_burro = max(0, self._data_sel_index_burro - 1)
							else:
								self._data_sel_index_galaxies = max(0, self._data_sel_index_galaxies - 1)
							continue
						elif event.key in (pygame.K_DOWN, pygame.K_s):
							if self._data_focus_section == 'burro':
								self._data_sel_index_burro = min(max(0, len(self._data_files_burro)-1), self._data_sel_index_burro + 1)
							else:
								self._data_sel_index_galaxies = min(max(0, len(self._data_files_galaxies)-1), self._data_sel_index_galaxies + 1)
							continue
						elif event.key in (pygame.K_r,):
							self._scan_data_files()
							self.last_message = "Listado actualizado"
							continue
						elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
							try:
								try:
									from src.core.loader import Loader as _Loader
								except ModuleNotFoundError:
									from core.loader import Loader as _Loader
								burro_path = self._data_files_burro[self._data_sel_index_burro] if self._data_files_burro else None
								galaxies_path = self._data_files_galaxies[self._data_sel_index_galaxies] if self._data_files_galaxies else None
								if burro_path and galaxies_path:
									loader = _Loader(path_burro=burro_path, path_galaxies=galaxies_path)
									self.donkey, self.graph = loader.load()
									_ = loader.load_ui_config(required=True)
									self._compute_palette()
									self._compute_transform()
									self._data_modal_active = False
									self.last_message = f"Cargado: {os.path.basename(burro_path)}, {os.path.basename(galaxies_path)}"
								else:
									self.last_message = "No hay archivos seleccionables"
							except Exception as e:
								self.last_message = f"Error cargando: {e}"
							continue
					# Consumir eventos mientras activo
					continue
				# Report modal has priority when active: handle close and scroll
				if getattr(self, '_report_modal_active', False):
					if event.type == pygame.KEYDOWN:
						if event.key in (pygame.K_ESCAPE, pygame.K_q):
							self._report_modal_active = False
							self.last_message = "Reporte cerrado"
							continue
						elif event.key == pygame.K_PAGEUP:
							self._report_scroll = max(0, self._report_scroll - 200)
							continue
						elif event.key == pygame.K_PAGEDOWN:
							self._report_scroll = self._report_scroll + 200
							continue
						elif event.key in (pygame.K_UP, pygame.K_w):
							self._report_scroll = max(0, self._report_scroll - 40)
							continue
						elif event.key in (pygame.K_DOWN, pygame.K_s):
							self._report_scroll = self._report_scroll + 40
							continue
					elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4,5):
						# Wheel scroll
						delta = -80 if event.button == 4 else 80
						self._report_scroll = max(0, self._report_scroll + delta)
						continue
				# Hypergiant modal has highest priority when active
				if getattr(self, '_hyper_modal_active', False):
					if event.type == pygame.KEYDOWN:
						if event.key in (pygame.K_ESCAPE,):
							self._hyper_modal_active = False
							self.last_message = "Salto cancelado"
							continue
						elif event.key in (pygame.K_UP, pygame.K_w):
							self._hyper_selected_idx = max(0, self._hyper_selected_idx - 1)
							continue
						elif event.key in (pygame.K_DOWN, pygame.K_s):
							self._hyper_selected_idx = min(max(0, len(self._hyper_candidates) - 1), self._hyper_selected_idx + 1)
							continue
						elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
							if 0 <= self._hyper_selected_idx < len(self._hyper_candidates):
								sid, _label, _cname = self._hyper_candidates[self._hyper_selected_idx]
								try:
									# Ejecutar teletransporte inmediato
									if self.simulator:
										self.simulator.teleport_and_visit(sid)
										# preparar una breve estadía/visual
										now_ms = pygame.time.get_ticks()
										self._dwell_active = True
										self._dwell_star = sid
										self._dwell_start_ms = now_ms
										self._dwell_duration_ms = 600
										self._prepare_animation(reset_index=True)
									self.last_message = f"Teleport a {sid}"
								except Exception as e:
									self.last_message = f"Error teleport: {e}"
							self._hyper_modal_active = False
							continue
					# Consume events while modal active
					continue
				try:
					# Panel de edición activo: captura entrada exclusivamente
					if self._arrival_input_active:
						if event.type == pygame.KEYDOWN:
							if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
								# Aplicar cambios y reanudar (ajuste retroactivo según campo)
								try:
									new_val = float(self._arrival_input_value or 0)
									field = self._arrival_fields[self._arrival_field_index]
									if self._arrival_star_id is not None and self._arrival_star_id in self.graph.stars and self.simulator:
										star = self.graph.stars[self._arrival_star_id]
										last = self.simulator.state.stars_log[-1] if self.simulator.state.stars_log else None
										if last and last.get("star") == self._arrival_star_id:
											if field == "life_delta":
												prev = float(last.get("life_delta", 0.0))
												adj = new_val - prev
												last["life_delta"] = new_val
												if "life_after" in last:
													last["life_after"] = max(0.0, float(last["life_after"]) + adj)
												self.simulator.state.life_remaining = max(0.0, float(self.simulator.state.life_remaining) + adj)
											elif field == "investigation_energy_cost":
												portion_invest = float(last.get("portion_invest", 0.0))
												prev_cost = float(last.get("invest_cost", 0.0))
												new_cost = portion_invest * new_val
												energy_after = float(last.get("energy_after", self.simulator.state.energy_pct))
												energy_after += prev_cost
												energy_after -= new_cost
												energy_after = max(0.0, min(100.0, energy_after))
												last["invest_cost"] = new_cost
												last["energy_after"] = energy_after
												self.simulator.state.energy_pct = energy_after
											elif field == "energy_bonus_pct":
												kg_eaten = float(last.get("kg_eaten", 0.0))
												base_gain_per_kg = self.donkey.energy_gain_per_kg()
												prev_gain = float(last.get("energy_gain", 0.0))
												new_gain = kg_eaten * base_gain_per_kg * (1.0 + max(0.0, new_val))
												energy_after = float(last.get("energy_after", self.simulator.state.energy_pct))
												energy_after -= prev_gain
												energy_after += new_gain
												energy_after = max(0.0, min(100.0, energy_after))
												last["energy_gain"] = new_gain
												last["energy_after"] = energy_after
												self.simulator.state.energy_pct = energy_after
										setattr(star, field, float(new_val))
									if field == "life_delta":
										self.last_message = f"Vida ajustada {self._arrival_star_id}: {new_val:+.2f}"
									elif field == "investigation_energy_cost":
										self.last_message = f"Costo investigación ajustado {self._arrival_star_id}: {new_val:.2f}"
									elif field == "energy_bonus_pct":
										self.last_message = f"Bonus energía ajustado {self._arrival_star_id}: {new_val:.2f}"
								except Exception as e:
									self.last_message = f"Error aplicando valor: {e}"
								# Cerrar panel y reanudar SOLO al confirmar con Enter
								self._arrival_input_active = False
								self._arrival_star_id = None
								self._arrival_input_value = ""
								self.sim_running = True
						elif event.key == pygame.K_ESCAPE:
							# Cancelar sin cambios (también cierra panel)
							self._arrival_input_active = False
							self._arrival_star_id = None
							self._arrival_input_value = ""
							# Mantener sim en pausa; el usuario la reanudará con Space
							# (no forzamos sim_running=True al cancelar)
						elif event.key in (pygame.K_BACKSPACE,):
							self._arrival_input_value = self._arrival_input_value[:-1]
						elif event.key == pygame.K_LEFTBRACKET:
							# Cambiar al campo anterior
							self._arrival_field_index = (self._arrival_field_index - 1) % len(self._arrival_fields)
							# Rellenar valor actual del campo seleccionado
							star = self.graph.stars.get(self._arrival_star_id) if self._arrival_star_id is not None else None
							if star:
								val = getattr(star, self._arrival_fields[self._arrival_field_index], 0.0)
								self._arrival_input_value = f"{float(val):.2f}"
						elif event.key == pygame.K_RIGHTBRACKET:
							# Cambiar al siguiente campo
							self._arrival_field_index = (self._arrival_field_index + 1) % len(self._arrival_fields)
							star = self.graph.stars.get(self._arrival_star_id) if self._arrival_star_id is not None else None
							if star:
								val = getattr(star, self._arrival_fields[self._arrival_field_index], 0.0)
								self._arrival_input_value = f"{float(val):.2f}"
						else:
							ch = None
							if pygame.K_0 <= event.key <= pygame.K_9:
								ch = chr(event.key)
							elif event.key in (pygame.K_PERIOD, pygame.K_KP_PERIOD):
								ch = '.'
							elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
								ch = '-'
							elif pygame.K_KP0 <= event.key <= pygame.K_KP9:
								ch = str(event.key - pygame.K_KP0)
							if ch is not None:
								buf = self._arrival_input_value
								if ch == '-' and buf:
									pass
								elif ch == '.' and '.' in buf:
									pass
								else:
									self._arrival_input_value += ch
						continue
				except Exception as e:
					# No cerrar el juego por errores de UI; mostrar mensaje y seguir
					self.last_message = f"Error UI: {e}"
					continue
				except Exception as e:
					# No cerrar el juego por errores de UI; mostrar mensaje y seguir
					self.last_message = f"Error UI: {e}"
					continue
				if event.type == pygame.QUIT:
					running = False
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
					running = False
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_f:
					# Alternar modo de coordenadas (píxeles vs escala lógica)
					self.pixel_coords = not self.pixel_coords
					self._compute_transform()
					self.last_message = "Coordenadas: pixel" if self.pixel_coords else "Coordenadas: escaladas (>=200um)"
				elif event.type == pygame.MOUSEMOTION:
					self.mouse_pos = event.pos
					self.hover_edge = self._nearest_edge(*self.mouse_pos)
					if self._panning:
						dx = event.pos[0] - self._pan_last[0]
						dy = event.pos[1] - self._pan_last[1]
						self.cam_off_x += dx
						self.cam_off_y += dy
						self._pan_last = event.pos
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_SLASH:
					self.show_help = not self.show_help
					self.last_message = "Ayuda visible" if self.show_help else "Ayuda oculta"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_a:
					self.auto_plan_on_click = not self.auto_plan_on_click
					self.last_message = "Auto-plan ON (click)" if self.auto_plan_on_click else "Auto-plan OFF (click)"
				elif event.type == pygame.KEYDOWN and (event.key == pygame.K_j) and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
					# Shift+J: alternar auto-apertura de hipersalto
					self.auto_open_hyperjump = not self.auto_open_hyperjump
					self.last_message = "Auto-hipersalto ON" if self.auto_open_hyperjump else "Auto-hipersalto OFF"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_x:
					# Alternar turbo
					self.turbo = not self.turbo
					self.last_message = "Turbo ON" if self.turbo else "Turbo OFF"
				elif event.type == pygame.MOUSEBUTTONDOWN:
					# Botón medio (2) o derecho (3): iniciar pan
					if event.button in (2, 3):
						self._panning = True
						self._pan_last = event.pos
					# Rueda del mouse: zoom
					elif event.button in (4, 5):
						factor = 1.2 if event.button == 4 else (1/1.2)
						mx, my = event.pos
						xw, yw = self.screen_to_world(mx, my)
						self.cam_scale_mul = max(0.1, min(5.0, self.cam_scale_mul * factor))
						# Mantener el punto bajo el cursor fijo
						sc = self.scale * self.cam_scale_mul
						self.cam_off_x = mx - self.offset_x - sc * xw
						self.cam_off_y = my - self.offset_y - sc * yw
					# Click izquierdo: seleccionar origen o limpiar si vacío
					elif event.button == 1:
						sid = self._star_at_pixel(*event.pos)
						if sid is not None:
							self.selected_origin = sid
							self.dists = {}
							self.parents = {}
							self.planned_route = []
							self.simulator = None
							self.sim_running = False
							# Mensaje inicial
							self.last_message = f"Origen establecido: {sid}" if not self.auto_plan_on_click else f"Origen {sid} (auto-planificando...)"
							# Auto-plan sólo si flag activo
							if self.auto_plan_on_click and self.donkey:
									try:
										# Usar Modo 2 por defecto para auto-plan: vida pura, sin repetir estrellas
										# Preferimos la variante Beam por robustez; cae a DFS si no está disponible
										try:
											route, used = optimal_max_visits_life_beam(self.graph, self.selected_origin, self.donkey)
											self.last_plan_mode = 'mode2_beam'
										except Exception:
											route, used = optimal_max_visits_life(self.graph, self.selected_origin, self.donkey)
											self.last_plan_mode = 'mode2'
										self.planned_route = route
										# Modo 2: simulación con consumo de energía y pasto (no es solo movimiento)
										self.simulator = Simulator(self.graph, self.donkey, self.planned_route)
										self._prepare_animation(reset_index=True)
										self.sim_running = True
										self.last_message = f"Auto-plan listo: {len(route)} nodos (dist≈{used:.1f})"
									except Exception as e:
										self.last_message = f"Auto-plan falló: {e}"
						else:
							self.selected_origin = None
							self.dists = {}
							self.parents = {}
							self.planned_route = []
							self.simulator = None
							self.sim_running = False
							self.last_message = "Origen limpiado"
				elif event.type == pygame.MOUSEBUTTONUP:
					if event.button in (2, 3):
						self._panning = False
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_c:
					# Limpiar origen y cálculos
					self.selected_origin = None
					self.dists = {}
					self.parents = {}
					self.planned_route = []
					self.simulator = None
					self.sim_running = False
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_b:
					# Toggle block on selected edge or nearest edge to mouse
					try:
						acted = False
						px, py = self.mouse_pos
						edge = self._nearest_edge(px, py)
						if edge:
							u, v = edge
							prev = self.graph.adjacency.get(u, {}).get(v)
							self.graph.toggle_edge_block(u, v)
							acted = True
							new_state = self.graph.adjacency.get(u, {}).get(v)
							if new_state is not None:
								action = "BLOCK" if new_state.blocked else "UNBLOCK"
								self._edge_events.append((action, u, v))
						self.last_message = "Arista bloqueada/habilitada" if acted else "No se encontró arista cercana"
						# Replan automático si hay plan activo
						if acted and self.selected_origin is not None and self.donkey and self.planned_route:
							try:
								if self.last_plan_mode in ('pure', 'mode1'):
									try:
										from src.core.planner import max_stars_before_death as _mode1
									except ModuleNotFoundError:
										from core.planner import max_stars_before_death as _mode1
									route, used = _mode1(self.graph, self.selected_origin, self.donkey)
									self.planned_route = route
									self.simulator = None
									self._anim_active = False
									self._dwell_active = False
									if len(self.planned_route) > 1 and self.donkey:
										try:
											self.simulator = Simulator(self.graph, self.donkey, self.planned_route)
											self._prepare_animation(reset_index=True)
											self.sim_running = True
										except Exception:
											self.simulator = None
											self.sim_running = False
									self.last_message += f" | Replan Modo1 {len(route)}"
								else:
									# Replan para Modo 2
									route, used = optimal_max_visits_life(self.graph, self.selected_origin, self.donkey)
									self.planned_route = route
									self.simulator = None
									self._anim_active = False
									self._dwell_active = False
									if len(self.planned_route) > 1 and self.donkey:
										try:
											# Modo 2: simulación con consumo de energía y pasto
											self.simulator = Simulator(self.graph, self.donkey, self.planned_route)
											self._prepare_animation(reset_index=True)
											self.sim_running = True
										except Exception:
											self.simulator = None
											self.sim_running = False
									self.last_message += f" | Replan Modo2 {len(route)}"
							except Exception as e:
								self.last_message = f"Error al recalcular plan: {e}"
					except Exception as e:
						self.last_message = f"Error al bloquear: {e}"
				# Eliminado: teclas R (Dijkstra manual) y P (ruta hover)
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_g:
					# Modo 2: Ruta óptima (DFS limitado por vida) maximizando estrellas sin repetir
					if self.selected_origin is None:
						self.last_message = "Selecciona origen antes de G"
					else:
						try:
							if not self.donkey:
								self.last_message = "Burro no disponible para plan"
							else:
								route, used = optimal_max_visits_life(self.graph, self.selected_origin, self.donkey)
								self.planned_route = route
								# Si no hay movimiento posible, forzar tramo mortal a la estrella más cercana
								if len(self.planned_route) <= 1:
									fr, fd = self._force_death_route()
									if fr:
										self.planned_route = fr
								# Preparar simulador (con energía y pasto activos para Modo 2)
								try:
									self.simulator = Simulator(self.graph, self.donkey, self.planned_route)
									self._set_stat_baselines()
									self._prepare_animation(reset_index=True)
									self.sim_running = True
									self._last_step_time = 0.0
									self._focus_mode = True
								except Exception:
									self.simulator = None
									self.sim_running = False
								vida_rest = max(0.0, float(self.donkey.vida_maxima) - float(self.donkey.edad)) if self.donkey else 0.0
								self.last_message = f"Modo 2 listo: {len(self.planned_route)} nodos, distancia≃{used:.1f} / vida {vida_rest:.1f}"
								self.last_plan_mode = 'mode2'
						except Exception as e:
							self.last_message = f"Error Modo 2: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_h:
					# Modo 1: Mayor cantidad de estrellas antes de morir (solo vida por desplazamientos)
					if self.selected_origin is None:
						self.last_message = "Selecciona origen antes de H"
					else:
						try:
							route, used = max_stars_before_death(self.graph, self.selected_origin, self.donkey)
							self.planned_route = route
							# Preparar simulación para el nuevo plan (auto-run si hay más de 1 nodo)
							self.simulator = None
							self._anim_active = False
							self._dwell_active = False
							# Si no hay movimiento posible, forzar tramo mortal a la estrella más cercana
							if len(self.planned_route) <= 1:
								fr, fd = self._force_death_route()
								if fr:
									self.planned_route = fr
							if len(self.planned_route) > 1 and self.donkey:
								try:
									self.simulator = Simulator(self.graph, self.donkey, self.planned_route, pure_movement_only=True)
									self._prepare_animation(reset_index=True)
									self.sim_running = True
								except Exception:
									self.simulator = None
									self.sim_running = False
							vida_rest = max(0.0, float(self.donkey.vida_maxima) - float(self.donkey.edad)) if self.donkey else 0.0
							# Mensaje claro: si forzamos tramo mortal, indicarlo
							if len(self.planned_route) <= 1:
								self.sim_running = False
								self.last_message = (
									f"Modo 1: sin movimientos (vida insuficiente). Vida {vida_rest:.1f}; "
									"elige otra estrella de origen o aumenta deathAge/startAge"
								)
							else:
								self.last_message = f"Modo 1 listo: {len(self.planned_route)} nodos, distancia≃{used:.1f} / vida {vida_rest:.1f}"
							self.last_plan_mode = 'mode1'
						except Exception as e:
							self.last_message = f"Error Modo 1: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_t:
					# Mostrar reporte inline y guardar JSON
					if not self.planned_route:
						self.last_message = "No hay plan para reportar"
					else:
						try:
							budget = energy_budget_from_donkey(self.donkey) if self.donkey else 0.0
							state = self.simulator.state if self.simulator else None
							log = self.simulator.export_log() if self.simulator else []
							report = build_final_report(self.graph, self.donkey, self.planned_route, state, log)
							report["total_cost_estimate"] = budget
							# Abrir modal inline
							self._open_report_modal(report)
							# Guardar automáticamente a carpeta reports
							try:
								os.makedirs("reports", exist_ok=True)
								stamp = time.strftime('%Y%m%d_%H%M%S')
								path = os.path.join("reports", f"final_report_{stamp}.json")
								with open(path, "w", encoding="utf-8") as f:
									json.dump(report, f, ensure_ascii=False, indent=2)
								self.last_message = f"Reporte mostrado y guardado en {path}"
							except Exception:
								self.last_message = "Reporte mostrado (no se pudo guardar)"
						except Exception as e:
							self.last_message = f"Error mostrando reporte: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_l:
					# Exportar log de simulación si existe
					try:
						if not self.simulator:
							self.last_message = "No hay simulación para exportar"
						else:
							log = self.simulator.export_log()
							with open("simulation_log.json", "w", encoding="utf-8") as f:
								json.dump(log, f, ensure_ascii=False, indent=2)
							self.last_message = "Log exportado: simulation_log.json"
					except Exception as e:
						self.last_message = f"Error exportando log: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_v:
					# Toggle live report overlay (único toggle visual que preservamos)
					self._live_report_enabled = not self._live_report_enabled
					self.last_message = "Live report ON" if self._live_report_enabled else "Live report OFF"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_o:
					# Reload JSON (burro y galaxias) desde UI
					try:
						try:
							from src.core.loader import Loader as _UILoader
						except ModuleNotFoundError:
							from core.loader import Loader as _UILoader
						ld = _UILoader()
						self.donkey, self.graph = ld.load()
						ui_cfg = ld.load_ui_config(required=True)
						# Reaplicar UI y transform/paleta
						self._compute_palette()
						self._compute_transform()
						# Reset plan/sim
						self.planned_route = []
						self.simulator = None
						self._anim_active = False
						self._dwell_active = False
						# Reset baselines
						self._max_life = float(getattr(self.donkey, 'vida_maxima', 100.0)) - float(getattr(self.donkey, 'edad', 0.0)) if self.donkey else 100.0
						self._max_pasto = float(getattr(self.donkey, 'pasto_kg', 100.0)) if self.donkey else 100.0
						self._alerts.clear()
						self.last_message = "JSON recargado"
						# Carga automática: abrir modal de selección si se mantiene Shift presionado
						if pygame.key.get_mods() & pygame.KMOD_SHIFT:
							self._scan_data_files()
							self._data_modal_active = True
							self.last_message = "Selector de archivos abierto (Shift+O)"
					except Exception as e:
						self.last_message = f"Error recargando JSON: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_F1:
					# Seleccionar burro.json desde un diálogo
					try:
						import tkinter as _tk
						from tkinter import filedialog as _fd
						root = _tk.Tk(); root.withdraw()
						path = _fd.askopenfilename(title="Selecciona burro.json", filetypes=[("JSON","*.json")])
						root.destroy()
						if path:
							try:
								from src.core.loader import Loader as _UILoader
							except ModuleNotFoundError:
								from core.loader import Loader as _UILoader
							ld = _UILoader(path_burro=path)
							self.donkey, _ = ld.load()
							self.last_message = f"Burro cargado: {os.path.basename(path)}"
						else:
							self.last_message = "Selección cancelada"
						# Shift+F1: abrir modal interno
						if pygame.key.get_mods() & pygame.KMOD_SHIFT:
							self._scan_data_files()
							self._data_modal_active = True
							self.last_message = "Selector interno abierto (Shift+F1)"
					except Exception as e:
						self.last_message = f"Error al cargar burro.json: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_F2:
					# Seleccionar galaxies.json desde un diálogo
					try:
						import tkinter as _tk
						from tkinter import filedialog as _fd
						root = _tk.Tk(); root.withdraw()
						path = _fd.askopenfilename(title="Selecciona galaxies.json", filetypes=[("JSON","*.json")])
						root.destroy()
						if path:
							try:
								from src.core.loader import Loader as _UILoader
							except ModuleNotFoundError:
								from core.loader import Loader as _UILoader
							ld = _UILoader(path_galaxies=path)
							_, self.graph = ld.load()
							self._compute_palette()
							self._compute_transform()
							self.last_message = f"Galaxias cargadas: {os.path.basename(path)}"
						else:
							self.last_message = "Selección cancelada"
						# Shift+F2: abrir modal interno en lugar de diálogo TK
						if pygame.key.get_mods() & pygame.KMOD_SHIFT:
							self._scan_data_files()
							self._data_modal_active = True
							self.last_message = "Selector interno abierto (Shift+F2)"
					except Exception as e:
						self.last_message = f"Error al cargar galaxies.json: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_s and not self._edit_mode:
					# Guardar parámetros editados de estrellas a JSON
					try:
						data = []
						for sid, st in self.graph.stars.items():
							data.append({
								"id": sid,
								"lifeDelta": float(getattr(st, 'life_delta', 0.0)),
								"healthModifier": getattr(st, 'health_modifier', None),
								"energyBonusPct": float(getattr(st, 'energy_bonus_pct', 0.0)),
							})
						os.makedirs("exports", exist_ok=True)
						path = os.path.join("exports", "edited_stars.json")
						with open(path, "w", encoding="utf-8") as f:
							json.dump({"stars": data}, f, ensure_ascii=False, indent=2)
						self.last_message = f"Parámetros de estrellas guardados en {path}"
					except Exception as e:
						self.last_message = f"Error guardando parámetros: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_e:
					# Alternar edición
					# Toggle edit mode on star under mouse
					try:
						sid = self._star_at_pixel(*self.mouse_pos, threshold=12)
						if not self._edit_mode:
							if sid is not None:
								self._edit_mode = True
								self._edit_star = sid
								self.last_message = f"Editando estrella {sid}"
							else:
								self.last_message = "No hay estrella bajo el cursor para editar"
						else:
							self._edit_mode = False
							self._edit_star = None
							self.last_message = "Edición desactivada"
					except Exception as e:
						self.last_message = f"Error en edición: {e}"
				elif event.type == pygame.KEYDOWN and self._edit_mode and self._edit_star is not None:
					# Ajustes de campos editables
					try:
						st = self.graph.stars.get(self._edit_star)
						if st:
							if event.key == pygame.K_j:
								st.life_delta = float(getattr(st, 'life_delta', 0.0)) - 0.5
							elif event.key == pygame.K_k:
								st.life_delta = float(getattr(st, 'life_delta', 0.0)) + 0.5
							elif event.key == pygame.K_u:
								st.energy_bonus_pct = float(getattr(st, 'energy_bonus_pct', 0.0)) - 0.05
							elif event.key == pygame.K_i:
								st.energy_bonus_pct = float(getattr(st, 'energy_bonus_pct', 0.0)) + 0.05
							elif event.key == pygame.K_m:
								cycle = [None, "Excelente", "Regular", "Mala", "Moribundo"]
								cur = getattr(st, 'health_modifier', None)
								try:
									idx = cycle.index(cur)
								except ValueError:
									idx = 0
								st.health_modifier = cycle[(idx + 1) % len(cycle)]
							self.last_message = f"Edit {st.id}: lifeDelta={st.life_delta:.2f} healthMod={st.health_modifier} energyBonusPct={st.energy_bonus_pct:.2f}"
					except Exception as e:
						self.last_message = f"Error ajustando valores: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
					# Ciclar constelación activa para enfocar
					names = list(self.graph.constellations.keys())
					if not names:
						self.active_constellation = None
						self.last_message = "Sin constelaciones"
					else:
						if self.active_constellation not in names:
							self.active_constellation = names[0]
						else:
							idx = names.index(self.active_constellation)
							self.active_constellation = names[(idx + 1) % len(names)]
						self.last_message = f"Enfoque: {self.active_constellation}" if self.active_constellation else "Enfoque: Todas"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN and self.hyperjump_active:
					# Confirmar selección de hipersalto
					self._apply_hyperjump_selection()
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self.hyperjump_active:
					# Cancelar hipersalto
					self.hyperjump_active = False
					self.sim_running = True
					self.last_message = "Hipersalto cancelado"
				elif event.type == pygame.KEYDOWN and self.hyperjump_active and event.key in (pygame.K_UP, pygame.K_DOWN):
					# Navegar opciones
					if self.hyperjump_options:
						if event.key == pygame.K_UP:
							self.hyperjump_index = max(0, self.hyperjump_index - 1)
						elif event.key == pygame.K_DOWN:
							self.hyperjump_index = min(len(self.hyperjump_options) - 1, self.hyperjump_index + 1)
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_j and not self.hyperjump_active:
					# Abrir selector de hipersalto manual (atajo) si en estrella hipergigante
					# En Modo 1 (solo desplazamiento) los hipersaltos están deshabilitados
					if self.last_plan_mode == 'mode1':
						self.last_message = "Hipersaltos deshabilitados en Modo 1"
						pass
					elif self.simulator and self.simulator.state:
						cur = self.simulator.state.current_star
						st = self.graph.stars.get(cur)
						if st and getattr(st, 'hypergiant', False):
							if self._open_hyperjump_selector():
								self.last_message = "Selector de hipersalto abierto"
							else:
								self.last_message = "Sin destinos de hipersalto"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_BACKQUOTE:
					# Quitar enfoque rápido (tecla `)
					self.active_constellation = None
					self.last_message = "Enfoque limpiado"
				elif event.type == pygame.KEYDOWN and (event.key == pygame.K_g) and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
					# Shift+G: alternar grid
					self.show_grid = not self.show_grid
					self.last_message = "Grid ON" if self.show_grid else "Grid OFF"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_y:
					# Modo 2++: Ruta Óptima (Beam) basada solo en vida
					if self.selected_origin is None:
						self.last_message = "Selecciona origen antes de Y"
					else:
							try:
								route, used = optimal_max_visits_life_beam(self.graph, self.selected_origin, self.donkey)
								self.planned_route = route
								if len(self.planned_route) <= 1:
									fr, fd = self._force_death_route()
									if fr:
										self.planned_route = fr
								# Preparar simulador (con energía y pasto activos para Modo 2++)
								try:
									self.simulator = Simulator(self.graph, self.donkey, self.planned_route)
									self._prepare_animation(reset_index=True)
									self.sim_running = True
									self._last_step_time = 0.0
								except Exception:
									self.simulator = None
									self.sim_running = False
								vida_rest = max(0.0, float(self.donkey.vida_maxima) - float(self.donkey.edad)) if self.donkey else 0.0
								self.last_message = f"Modo 2++ listo: {len(self.planned_route)} nodos, distancia≃{used:.1f} / vida {vida_rest:.1f}"
								self.last_plan_mode = 'mode2_beam'
							except Exception as e:
								self.last_message = f"Error Modo 2++: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
					# Toggle play/pause simulation
					if not self.planned_route:
						self.last_message = "Calcula un plan (G) antes de simular"
					else:
						if not self.simulator:
							try:
								self.simulator = Simulator(self.graph, self.donkey, self.planned_route, pure_movement_only=(self.last_plan_mode=='mode1'))
								self._last_step_time = 0.0
								self._prepare_animation(reset_index=False)
								self.sim_running = True
								self.last_message = "Simulación iniciada"
							except Exception as e:
								self.last_message = f"No se pudo iniciar simulación: {e}"
						else:
							if self.simulator.state.finished:
								self.last_message = "Simulación ya finalizada"
							else:
								self.sim_running = not self.sim_running
								self._last_step_time = 0.0
								self.last_message = "Simulación reanudada" if self.sim_running else "Simulación en pausa"
				elif event.type == pygame.KEYDOWN and (event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS)):
					# Increase sim speed
					self.sim_speed = min(10.0, self.sim_speed * 1.5)
					self.last_message = f"Velocidad x{self.sim_speed:.2f}"
				elif event.type == pygame.KEYDOWN and event.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
					# Ajustar vida del burro: [ reduce, ] aumenta (Shift = paso grande)
					if not self.donkey:
						self.last_message = "Burro no disponible"
						continue
					step = 5.0
					if pygame.key.get_mods() & pygame.KMOD_SHIFT:
						step *= 5.0
					delta = step if event.key == pygame.K_RIGHTBRACKET else -step
					max_life = max(0.0, float(self.donkey.vida_maxima) - float(self.donkey.edad))
					current_life = self.simulator.state.life_remaining if self.simulator else max_life
					new_life = max(0.0, min(max_life, current_life + delta))
					# Ajustar edad para reflejar nueva vida disponible (vida_maxima - edad = new_life)
					self.donkey.edad = float(self.donkey.vida_maxima) - new_life
					if self.simulator:
						self.simulator.state.life_remaining = new_life
						# Reajustar animación actual si procede
						if self._anim_active:
							self._prepare_animation(reset_index=False)
					self.last_message = f"Vida ajustada a {new_life:.1f}"
				elif event.type == pygame.KEYDOWN and (event.key in (pygame.K_MINUS, pygame.K_KP_MINUS)):
					# Decrease sim speed
					self.sim_speed = max(0.1, self.sim_speed / 1.5)
					self.last_message = f"Velocidad x{self.sim_speed:.2f}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_n:
					# Single step
					if not self.simulator:
						if not self.planned_route:
							self.last_message = "Sin plan (G) para simular"
						else:
							try:
								self.simulator = Simulator(self.graph, self.donkey, self.planned_route, pure_movement_only=(self.last_plan_mode=='mode1'))
							except Exception as e:
								self.last_message = f"No se pudo preparar simulación: {e}"
					if self.simulator and not self.simulator.state.finished:
						st = self.simulator.step()
						# Si el simulador amplió la ruta automáticamente, sincronizar el plan mostrado
						try:
							if hasattr(self.simulator, 'route') and len(self.simulator.route) != len(self.planned_route or []):
								self.planned_route = list(self.simulator.route)
						except Exception:
							pass
						self.last_message = f"Tick {st.tick} en {st.current_star} E={st.energy_pct:.1f}% L={st.life_remaining:.1f}kg"
						if st.dead:
							self._sound.play_death()
							self.last_message += " | MUERTE"
							if self.auto_show_report_on_finish and not self._report_shown_once:
								self._show_final_report()
						elif st.finished:
							if self.auto_show_report_on_finish and not self._report_shown_once:
								self._show_final_report()
					# (removed erroneous else-block using undefined now_ms)

			# Actualización de simulación y animación (auto-run)
			try:
				if self.simulator and self.sim_running and not self.hyperjump_active:
					st = self.simulator.state
					if not st.finished and not st.dead:
						now_ms = pygame.time.get_ticks()
						# Si no hay animación ni estadía, preparar siguiente tramo
						if not self._anim_active and not self._dwell_active:
							self._prepare_animation(reset_index=False)
						# Si hay animación y terminó, ejecutar paso de simulación y entrar en estadía
						elif self._anim_active and (now_ms - self._anim_start_ms >= self._anim_duration_ms):
							self._anim_active = False
							# Avanzar la simulación un tramo
							st = self.simulator.step()
							# Sincronizar ruta si fue ampliada automáticamente
							try:
								if hasattr(self.simulator, 'route') and len(self.simulator.route) != len(self.planned_route or []):
									self.planned_route = list(self.simulator.route)
							except Exception:
								pass
							self._anim_index = self.simulator.index
							# Configurar estadía breve visual
							self._dwell_star = st.current_star
							base_dwell_ms = 260.0
							factor_speed = max(0.1, self.sim_speed) * (2.0 if self.turbo else 1.0)
							self._dwell_duration_ms = max(80.0, base_dwell_ms / factor_speed)
							self._dwell_start_ms = now_ms
							self._dwell_active = True
							self.last_message = f"Tick {st.tick} en {st.current_star} E={st.energy_pct:.1f}% L={st.life_remaining:.1f}kg"
							if st.dead:
								self._sound.play_death()
								self.last_message += " | MUERTE"
								self.sim_running = False
								# Mostrar reporte final automáticamente
								if hasattr(self, 'auto_show_report_on_finish') and self.auto_show_report_on_finish and not self._report_shown_once:
									self._show_final_report()
							elif st.finished:
								self.sim_running = False
								self.last_message += " | Ruta completada"
								# Mostrar reporte final automáticamente
								if hasattr(self, 'auto_show_report_on_finish') and self.auto_show_report_on_finish and not self._report_shown_once:
									self._show_final_report()
							else:
								# Auto-abrir selector de hipersalto si corresponde
								cur_star = self.graph.stars.get(st.current_star)
								if cur_star and getattr(cur_star, 'hypergiant', False) and getattr(self, 'auto_open_hyperjump', False):
									self._open_hyperjump_selector()
						# Si estamos en estadía y ya terminó, preparar siguiente tramo
						elif self._dwell_active and (now_ms - self._dwell_start_ms >= self._dwell_duration_ms):
							self._dwell_active = False
							if not self.simulator.state.finished and self.sim_running and not self.hyperjump_active:
								self._prepare_animation(reset_index=False)
			except Exception:
				# No romper el bucle por errores no críticos en la actualización
				pass

			self.draw(screen)
			pygame.display.flip()
			clock.tick(60)
		pygame.quit()

	def _prepare_animation(self, reset_index: bool = False):
		"""Configura animación del siguiente tramo según velocidad y distancia.

		reset_index: si True reinicia la animación desde el principio de la ruta.
		"""
		if not self.simulator or not self.planned_route:
			self._anim_active = False
			return
		if reset_index:
			self._anim_index = self.simulator.index
		# Determinar leg actual
		leg = max(self.simulator.index, self._anim_index)
		if leg >= len(self.planned_route) - 1:
			self._anim_active = False
			return
		src = self.planned_route[leg]
		dst = self.planned_route[leg + 1]
		self._anim_src = src
		self._anim_dst = dst
		# Distancia para duración
		dist = None
		if src in self.graph.adjacency and dst in self.graph.adjacency[src]:
			dist = float(self.graph.adjacency[src][dst].distance)
		else:
			sa = self.graph.stars.get(src)
			sb = self.graph.stars.get(dst)
			if sa and sb:
				dx = sb.x - sa.x
				dy = sb.y - sa.y
				dist = max(1.0, (dx*dx + dy*dy) ** 0.5)
			else:
				dist = 1.0
		base_ms_per_unit = 180.0  # ms por unidad de distancia a velocidad 1 (acelerado)
		# Si el tramo excede la vida restante, acortar duración proporcional a la fracción de vida
		death_frac = 1.0
		try:
			st = self.simulator.state if self.simulator else None
			if st and dist > 0 and st.life_remaining < dist:
				death_frac = max(0.1, min(1.0, st.life_remaining / dist))
		except Exception:
			death_frac = 1.0
		# Aplica turbo multiplicando el factor de velocidad
		factor_speed = max(0.1, self.sim_speed) * (2.0 if self.turbo else 1.0)
		dur = max(80.0, base_ms_per_unit * dist * death_frac / factor_speed)
		self._anim_duration_ms = dur
		self._anim_start_ms = pygame.time.get_ticks()
		self._anim_active = True

	def _prepare_hyper_modal(self, source_star_id: int):
		"""Prepara lista de candidatos de otras constelaciones para salto hiper."""
		self._hyper_source_star = source_star_id
		source = self.graph.stars.get(source_star_id)
		if not source:
			self._hyper_modal_active = False
			return
		source_consts = set(getattr(source, 'constellations', []) or [])
		cand: list[tuple[int,str,str]] = []
		for sid, st in self.graph.stars.items():
			if sid == source_star_id:
				continue
			cnames = list(getattr(st, 'constellations', []) or [])
			# Elegir aquellos que no comparten constelación con el origen
			if not source_consts.intersection(cnames):
				primary = cnames[0] if cnames else "?"
				cand.append((sid, st.label, primary))
		# Ordenar por constelación y luego por id
		cand.sort(key=lambda x: (x[2], x[0]))
		self._hyper_candidates = cand
		self._hyper_selected_idx = 0
		self._hyper_modal_active = True

	def _draw_hyper_modal(self, screen):
		"""Dibuja un panel modal para elegir destino de hiper salto."""
		f = self.font or self.small_font
		if not f:
			return
		w = min(640, int(self.width * 0.8))
		h = min(420, int(self.height * 0.7))
		bx = (self.width - w) // 2
		by = (self.height - h) // 2
		pygame.draw.rect(screen, (0, 0, 0), (bx, by, w, h))
		pygame.draw.rect(screen, (180, 180, 180), (bx, by, w, h), 2)
		title = f.render("Salto Hipergigante: elige destino (otra galaxia)", True, (255, 230, 120))
		screen.blit(title, (bx + 12, by + 10))
		if not self._hyper_candidates:
			msg = f.render("No hay destinos en otras galaxias.", True, (255, 120, 120))
			screen.blit(msg, (bx + 12, by + 50))
			return
		# Lista con scroll simple (mostrar hasta 12)
		max_rows = 12
		start = max(0, min(self._hyper_selected_idx - max_rows // 2, max(0, len(self._hyper_candidates) - max_rows)))
		view = self._hyper_candidates[start:start + max_rows]
		y = by + 48
		for i, (sid, label, cname) in enumerate(view):
			row = f"[{sid}] {label}  <{cname}>"
			col = (200, 230, 255) if (start + i) == self._hyper_selected_idx else (220, 220, 220)
			img = f.render(row, True, col)
			screen.blit(img, (bx + 20, y))
			y += img.get_height() + 6
		instr = (self.small_font or f).render("UP/DOWN=Seleccionar  Enter=Confirmar  Esc=Cancelar", True, (200, 200, 200))
		screen.blit(instr, (bx + 12, by + h - 28))

	def _auto_export_final_report(self):
		"""Exporta final_report.json con estado y log actuales."""
		try:
			if not self.planned_route:
				return
			state = self.simulator.state if self.simulator else None
			log = self.simulator.export_log() if self.simulator else []
			report = build_final_report(self.graph, self.donkey, self.planned_route, state, log)
			with open("final_report.json", "w", encoding="utf-8") as f:
				json.dump(report, f, ensure_ascii=False, indent=2)
			self.last_message = "Reporte final exportado (final_report.json)"
		except Exception as e:
			self.last_message = f"No se pudo exportar reporte final: {e}"

	def _show_final_report(self):
		"""Genera y muestra el reporte final en modal inline (solo una vez)."""
		if self._report_shown_once:
			return
		try:
			if not self.planned_route:
				self._report_shown_once = True
				return
			state = self.simulator.state if self.simulator else None
			log = self.simulator.export_log() if self.simulator else []
			report = build_final_report(self.graph, self.donkey, self.planned_route, state, log)
			try:
				budget = energy_budget_from_donkey(self.donkey) if self.donkey else 0.0
				report["total_cost_estimate"] = budget
			except Exception:
				pass
			self._open_report_modal(report)
			os.makedirs("reports", exist_ok=True)
			stamp = time.strftime('%Y%m%d_%H%M%S')
			path = os.path.join("reports", f"final_report_{stamp}.json")
			with open(path, "w", encoding="utf-8") as f:
				json.dump(report, f, ensure_ascii=False, indent=2)
			self.last_message = f"Reporte final guardado en {path}"
		except Exception as e:
			self.last_message = f"Error reporte final: {e}"
		finally:
			self._report_shown_once = True

	def _open_report_modal(self, report: dict):
			# Construye líneas de texto legibles del dict
			self._report_lines = []
			self._report_lines.append("== REPORTE DEL RECORRIDO ==")
			self._report_lines.append(f"Generado: {report.get('generated_at','')}")
			self._report_lines.append(f"Ruta: {report.get('route_length')} estrellas | Costo estimado: {report.get('total_cost_estimate')}")
			self._report_lines.append("-- Estrellas --")
			for s in report.get('stars', []):
				flags = []
				if s.get('hypergiant'): flags.append('H')
				if s.get('shared'): flags.append('S')
				fl = '['+','.join(flags)+']' if flags else ''
				self._report_lines.append(f"[{s.get('index')}] id={s.get('id')} {s.get('label')} {fl} const={','.join(s.get('constellations',[]))}")
			final = report.get('final', {})
			if final:
				self._report_lines.append("-- Estado final --")
				self._report_lines.append(f"E%={final.get('final_energy_pct')} Pasto={final.get('final_pasto_kg')} VidaRest={final.get('final_life_remaining')} Dead={final.get('dead')} Finished={final.get('finished')}")
			visit_detail = report.get('stars_visit_detail', [])
			if visit_detail:
				self._report_lines.append("-- Visitas --")
				for d in visit_detail[:100]:  # limitar para no saturar
					self._report_lines.append(
						f"Star {d['star']} kg={d.get('kg_eaten',0):.2f} ΔE={d.get('energy_gain',0):.2f} invCost={d.get('invest_cost',0):.2f} vidaΔ={d.get('life_delta',0):.2f} E:{d.get('energy_before',0):.1f}->{d.get('energy_after',0):.1f}"
					)
			log = report.get('simulation_log', [])
			if log:
				self._report_lines.append("-- Log eventos --")
				for e in log[:120]:
					if e.get('event') == '...trimmed...':
						self._report_lines.append(f"... {e.get('count')} eventos omitidos ...")
					else:
						self._report_lines.append(f"tick={e.get('tick')} star={e.get('star')} evt={e.get('event')} E={e.get('energy_pct'):.1f} Vida={e.get('life_remaining'):.1f}")
			self._report_lines.append("ESC/Q: cerrar | PageUp/PageDown/Wheel: scroll")
			self._report_modal_active = True
			self._report_scroll = 0

	def _draw_report_modal(self, screen):
			if not (self.font or self.small_font):
				return
			f = self.small_font or self.font
			w = int(self.width * 0.92)
			h = int(self.height * 0.88)
			bx = (self.width - w)//2
			by = (self.height - h)//2
			# Fondo translúcido
			over = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
			over.fill((0,0,0,180))
			screen.blit(over, (0,0))
			pygame.draw.rect(screen, (10,10,16), (bx,by,w,h))
			pygame.draw.rect(screen, (160,160,190), (bx,by,w,h), 2)
			# Área de texto con scroll
			clip = screen.get_clip()
			text_area = pygame.Rect(bx+12, by+12, w-24, h-24)
			screen.set_clip(text_area)
			y = text_area.y - self._report_scroll
			for line in self._report_lines:
				img = f.render(line, True, (230,230,230) if not line.startswith('==') else (255,220,90))
				screen.blit(img, (text_area.x, y))
				y += img.get_height()+4
			screen.set_clip(clip)
			# Indicador de scroll
			pygame.draw.rect(screen, (50,50,70), (bx+w-20, by+12, 8, h-24))
			content_h = y - (text_area.y - self._report_scroll)
			if content_h > text_area.height:
				p = min(1.0, max(0.0, self._report_scroll / (content_h - text_area.height)))
				bar_h = max(24, int(text_area.height * (text_area.height / content_h)))
				bar_y = int(by+12 + (h-24 - bar_h) * p)
				pygame.draw.rect(screen, (180,180,210), (bx+w-20, bar_y, 8, bar_h))

	def _scan_data_files(self):
			"""Escanea la carpeta 'data' para listar candidatos burro*.json y galaxies*.json."""
			try:
				files = [f for f in os.listdir('data') if f.lower().endswith('.json')]
			except Exception:
				files = []
			burro = [os.path.join('data', f) for f in files if 'burro' in f.lower()]
			galax = [os.path.join('data', f) for f in files if 'galax' in f.lower() or 'constell' in f.lower()]
			self._data_files_burro = sorted(burro)
			self._data_files_galaxies = sorted(galax)
			self._data_sel_index_burro = 0 if self._data_files_burro else 0
			self._data_sel_index_galaxies = 0 if self._data_files_galaxies else 0

	def _draw_data_modal(self, screen):
			f = self.small_font or self.font
			w = int(self.width * 0.85)
			h = int(self.height * 0.75)
			bx = (self.width - w)//2
			by = (self.height - h)//2
			over = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
			over.fill((0,0,0,200))
			screen.blit(over, (0,0))
			pygame.draw.rect(screen, (15,15,25), (bx,by,w,h))
			pygame.draw.rect(screen, (140,140,180), (bx,by,w,h), 2)
			title = f.render("Cargar archivos (F3) - TAB cambia sección - Enter aplica - R recarga - Esc cierra", True, (230,230,80))
			screen.blit(title, (bx+12, by+12))
			# Secciones
			section_w = (w - 36) // 2
			burro_rect = pygame.Rect(bx+12, by+44, section_w, h-56)
			galax_rect = pygame.Rect(bx+24+section_w, by+44, section_w, h-56)
			pygame.draw.rect(screen, (25,25,40), burro_rect)
			pygame.draw.rect(screen, (25,25,40), galax_rect)
			pygame.draw.rect(screen, (100,100,130), burro_rect, 1 if self._data_focus_section=='burro' else 0)
			pygame.draw.rect(screen, (100,100,130), galax_rect, 1 if self._data_focus_section=='galaxies' else 0)
			bh = f.render("burro.json", True, (200,200,220))
			gh = f.render("galaxies.json", True, (200,200,220))
			screen.blit(bh, (burro_rect.x+8, burro_rect.y+4))
			screen.blit(gh, (galax_rect.x+8, galax_rect.y+4))
			# Listas
			yb = burro_rect.y + 28
			for i, path in enumerate(self._data_files_burro):
				name = os.path.basename(path)
				col = (40,220,140) if i == self._data_sel_index_burro and self._data_focus_section=='burro' else (220,220,220)
				img = f.render(name, True, col)
				screen.blit(img, (burro_rect.x+8, yb)); yb += img.get_height()+4
			yg = galax_rect.y + 28
			for i, path in enumerate(self._data_files_galaxies):
				name = os.path.basename(path)
				col = (40,220,140) if i == self._data_sel_index_galaxies and self._data_focus_section=='galaxies' else (220,220,220)
				img = f.render(name, True, col)
				screen.blit(img, (galax_rect.x+8, yg)); yg += img.get_height()+4
			if not self._data_files_burro:
				img = f.render("(sin burro*.json)", True, (200,100,100))
				screen.blit(img, (burro_rect.x+8, yb))
			if not self._data_files_galaxies:
				img = f.render("(sin galaxies*.json)", True, (200,100,100))
				screen.blit(img, (galax_rect.x+8, yg))


	def _set_stat_baselines(self):
		"""Fija los máximos para las barras (vida, pasto) al inicio de la simulación."""
		if self.simulator:
			self._max_life = float(self.simulator.state.life_remaining)
			self._max_pasto = float(self.simulator.state.pasto_kg)
		else:
			self._max_life = float(getattr(self.donkey, 'vida_maxima', 100.0)) - float(getattr(self.donkey, 'edad', 0.0)) if self.donkey else 100.0
			self._max_pasto = float(getattr(self.donkey, 'pasto_kg', 100.0)) if self.donkey else 100.0

	def _emit_visit_alerts(self):
		"""Crea alertas visuales con las variaciones de energía, vida y pasto.

		Se apoya en el último registro de stars_log y en los snapshots previos al step.
		"""
		try:
			if not self.simulator:
				return
			st = self.simulator.state
			last = st.stars_log[-1] if st.stars_log else None
			now = pygame.time.get_ticks()
			dur = 2200
			# Deltas por movimiento (antes de la visita): requiere snapshot
			if self._pre_step_energy is not None and self._pre_step_life is not None and last:
				energy_before_visit = float(last.get('energy_before', self._pre_step_energy))
				life_before_visit = float(last.get('life_before', self._pre_step_life))
				move_e_loss = self._pre_step_energy - energy_before_visit
				move_l_loss = self._pre_step_life - life_before_visit
				if move_e_loss > 0.01:
					self._alerts.append({"text": f"- {move_e_loss:.1f}% energía (mov)", "color": (255,90,90), "t0": now, "dur": dur})
				if move_l_loss > 0.01:
					self._alerts.append({"text": f"- {move_l_loss:.1f} vida (mov)", "color": (255,160,90), "t0": now, "dur": dur})
			# Deltas de la visita
			if last:
				kg = float(last.get('kg_eaten', 0.0))
				if kg > 0.0:
					self._alerts.append({"text": f"Comió {kg:.1f} kg", "color": (90,220,160), "t0": now, "dur": dur})
				gain = float(last.get('energy_gain', 0.0))
				cost = float(last.get('invest_cost', 0.0))
				if gain > 0.01:
					self._alerts.append({"text": f"+ {gain:.1f}% energía", "color": (120,240,120), "t0": now, "dur": dur})
				if cost > 0.01:
					self._alerts.append({"text": f"- {cost:.1f}% energía (invest)", "color": (255,120,120), "t0": now, "dur": dur})
				ld = float(last.get('life_delta', 0.0))
				if abs(ld) > 0.01:
					col = (120,200,255) if ld > 0 else (255,140,80)
					self._alerts.append({"text": f"Δ vida {ld:+.1f}", "color": col, "t0": now, "dur": dur})
				if bool(last.get('hypergiant', False)):
					self._alerts.append({"text": "Recarga hipergigante", "color": (255,230,120), "t0": now, "dur": dur})
		except Exception:
			pass

	def _draw_top_bars(self, screen):
		"""Dibuja barras de Energía, Vida y Pasto en la parte superior."""
		pad = 8
		x = pad
		y = pad
		h = 14
		sep = 8
		def draw_bar(label, value, max_value, color):
			max_value = max(0.001, float(max_value))
			value = max(0.0, float(value))
			w = int(self.width * 0.28)
			pct = max(0.0, min(1.0, value / max_value))
			# fondo
			pygame.draw.rect(screen, (20,20,25), (x, y, w, h))
			pygame.draw.rect(screen, (120,120,130), (x, y, w, h), 1)
			# barra
			pygame.draw.rect(screen, color, (x+1, y+1, int((w-2) * pct), h-2))
			# texto
			if self.small_font:
				text = f"{label}: {value:.1f} / {max_value:.1f}"
				img = self.small_font.render(text, True, (230,230,230))
				screen.blit(img, (x + 6, y - 14))
			return w
		# Valores actuales
		if self.simulator:
			curE = float(self.simulator.state.energy_pct)
			curL = float(self.simulator.state.life_remaining)
			curP = float(self.simulator.state.pasto_kg)
		else:
			curE = float(getattr(self.donkey, 'energia_pct', 100.0)) if self.donkey else 0.0
			curL = float(getattr(self.donkey, 'vida_maxima', 100.0)) - float(getattr(self.donkey, 'edad', 0.0)) if self.donkey else 0.0
			curP = float(getattr(self.donkey, 'pasto_kg', 0.0)) if self.donkey else 0.0
		# Energía (0..100)
		w1 = draw_bar("Energía", curE, 100.0, (90,200,120) if curE>50 else (220,180,80) if curE>20 else (230,80,80))
		x += w1 + sep
		# Vida (años luz)
		w2 = draw_bar("Vida", curL, max(self._max_life, curL), (120,180,255))
		x += w2 + sep
		# Pasto (kg)
		_ = draw_bar("Pasto", curP, max(self._max_pasto, curP), (170,220,120))

	def _draw_alerts(self, screen):
		"""Renderiza alertas efímeras en la parte superior, debajo de las barras."""
		if not (self.small_font or self.font):
			return
		f = self.small_font or self.font
		now = pygame.time.get_ticks()
		# mantener solo vivas
		self._alerts = [a for a in self._alerts if now - a.get('t0', 0) <= a.get('dur', 2000)]
		if not self._alerts:
			return
		# base position (centro superior)
		base_y = 30
		spacing = 18
		for i, a in enumerate(self._alerts[-5:]):
			age = now - a['t0']
			dur = max(1, a['dur'])
			alpha = 255
			if age > dur * 0.6:
				alpha = int(255 * (1 - (age - dur * 0.6) / (dur * 0.4)))
			alpha = max(0, min(255, alpha))
			col = a.get('color', (255,255,255))
			text = a.get('text', '')
			surf = f.render(text, True, col)
			try:
				s = surf.convert_alpha()
				s.set_alpha(alpha)
			except Exception:
				s = surf
			x = (self.width - s.get_width()) // 2
			y = base_y + i * spacing
			# sombra
			pygame.draw.rect(screen, (0,0,0), (x-6, y-2, s.get_width()+12, s.get_height()+4))
			screen.blit(s, (x, y))

