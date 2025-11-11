from typing import Dict, Tuple, Set
import math

try:
	import pygame
except Exception:  
	pygame = None

try:
	from src.core.planner import (
		dijkstra,
		reconstruct_path,
		greedy_max_visits_enhanced,
		energy_budget_from_donkey,
	)
except ModuleNotFoundError:
	from core.planner import (
		dijkstra,
		reconstruct_path,
		greedy_max_visits_enhanced,
		energy_budget_from_donkey,
	)

try:
	from src.core.reporter import build_route_report, save_route_report
except ModuleNotFoundError:
	from core.reporter import build_route_report, save_route_report

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
		# Simulation fields
		self.simulator = None
		self.sim_running = False
		self.sim_speed = 1.0  # steps per second
		self._last_step_time = 0.0
		self._sound = SoundManager()
		# Assets (manifest opcional)
		self.assets = AssetManifest() if 'AssetManifest' in globals() and AssetManifest else None
		self._bg_image_original = None
		self._bg_image_scaled = None
		self._compute_palette()
		self._compute_transform()

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
		draw_w = self.width - 2 * self.margin
		draw_h = self.height - 2 * self.margin
		sx = draw_w / span_x
		sy = draw_h / span_y
		self.scale = min(sx, sy) if (sx > 0 and sy > 0) else 1.0
		self.offset_x = self.margin - self.scale * min_x + (draw_w - self.scale * span_x) / 2
		self.offset_y = self.margin - self.scale * min_y + (draw_h - self.scale * span_y) / 2

	def world_to_screen(self, x: float, y: float) -> Tuple[int, int]:
		sx = int(self.scale * x + self.offset_x)
		sy = int(self.scale * y + self.offset_y)
		# Pygame's Y axis grows downward already; no flip needed
		return sx, sy

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
		self._draw_grid(screen)

		# Draw edges (unique undirected)
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
				color = self.edge_blocked_color if edge.blocked else self.edge_color
				pygame.draw.line(screen, color, (x1, y1), (x2, y2), 2)

		# Draw stars
		for cname, const in self.graph.constellations.items():
			color = self.constellation_colors.get(cname, (180, 180, 180))
			for sid in const.stars:
				star = self.graph.stars.get(sid)
				if not star:
					continue
				x, y = self.world_to_screen(star.x, star.y)
				r = max(2, int(2 + star.radius * 5))
				pygame.draw.circle(screen, color, (x, y), r)

		# Overlay: draw shared rings based ONLY on JSON flag 'shared'
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

		# Draw planned route if exists (thick cyan segments + numbering)
		if self.planned_route and len(self.planned_route) > 1:
			for i in range(len(self.planned_route) - 1):
				a = self.planned_route[i]
				b = self.planned_route[i + 1]
				if a in self.graph.stars and b in self.graph.stars:
					sa = self.graph.stars[a]
					sb = self.graph.stars[b]
					x1, y1 = self.world_to_screen(sa.x, sa.y)
					x2, y2 = self.world_to_screen(sb.x, sb.y)
					pygame.draw.line(screen, (0, 200, 255), (x1, y1), (x2, y2), 3)
			# Optionally draw step numbers
			if self.small_font:
				for idx, sid in enumerate(self.planned_route):
					st = self.graph.stars.get(sid)
					if not st:
						continue
					x, y = self.world_to_screen(st.x, st.y)
					img = self.small_font.render(str(idx), True, (0, 220, 255))
					screen.blit(img, (x + 6, y + 6))

		# HUD: instructions and selection info (moved to bottom-right)
		if self.font:
			info_lines = []
			# Dynamic status first
			if self.selected_origin is not None:
				line_origin = f"Origen {self.selected_origin}"
				if self.planned_route:
					line_origin += f" | Plan {len(self.planned_route)}"
				info_lines.append(line_origin)
			# Simulation status
			if self.simulator:
				st = self.simulator.state
				status = "RUN" if self.sim_running and not st.finished else ("DONE" if st.finished else "PAUSE")
				info_lines.append(f"Sim {status} E={st.energy_pct:.1f}% L={st.life_remaining:.1f}kg P={st.pasto_kg:.1f}")
				hover_sid = self._star_at_pixel(*self.mouse_pos, threshold=12)
				if hover_sid is not None:
					if hover_sid in self.dists:
						info_lines.append(f"Hover {hover_sid} d={self.dists[hover_sid]:.1f}")
					else:
						info_lines.append(f"Hover {hover_sid} sin ruta")
			info_lines.append("RutaHover:" + ("ON" if self.show_path_to_hover else "OFF"))
			info_lines.append("Controles: Click=Origen R=Djk P=Ruta G=Plan T=Reporte B=Bloq C=Clear Space=Play N=Step +/-=Vel ESC")
			if self.last_message:
				info_lines.append(self.last_message)
			# Legend appended after a separator line if fits
			legend_lines = []
			for name, color in self.constellation_colors.items():
				legend_lines.append(f"{name}")
			# Compute block size
			all_lines = info_lines + ["-"] + legend_lines if legend_lines else info_lines
			# Render bottom-right
			pad = 8
			rendered = [self.font.render(line, True, (230, 230, 230)) for line in all_lines]
			height_block = sum(r.get_height()+2 for r in rendered)
			width_block = max(r.get_width() for r in rendered) if rendered else 0
			bx = self.width - width_block - pad - 4
			by = self.height - height_block - pad - 4
			# Background panel
			pygame.draw.rect(screen, (0, 0, 0, 160), (bx-4, by-4, width_block + 8, height_block + 8))
			y = by
			for line_surf, text in zip(rendered, all_lines):
				if text == "-":
					pygame.draw.line(screen, (90, 90, 90), (bx, y), (bx + width_block, y), 1)
					y += 4
					continue
				screen.blit(line_surf, (bx, y))
				y += line_surf.get_height() + 2

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
			img = self.font.render(name, True, (220, 220, 220))
			screen.blit(img, (x + 18, y - 2))
			y += 18

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
		# Imagen de fondo opcional
		bg_path = (self.assets.get_image("background") if self.assets else None)
		if bg_path:
			try:
				img = load_pygame_image(bg_path)
				self._bg_image_original = img.convert() if img else None
			except Exception:
				self._bg_image_original = None
		clock = pygame.time.Clock()
		running = True
		while running:
			for event in pygame.event.get():
				if event.type == pygame.QUIT:
					running = False
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
					running = False
				elif event.type == pygame.MOUSEMOTION:
					self.mouse_pos = event.pos
					self.hover_edge = self._nearest_edge(*self.mouse_pos)
				elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
					# Selección de origen; click en vacío limpia
					sid = self._star_at_pixel(*event.pos)
					if sid is not None:
						self.selected_origin = sid
						self.dists = {}
						self.parents = {}
						self.planned_route = []
						self.simulator = None
						self.sim_running = False
						self.last_message = f"Origen establecido: {sid}"
					else:
						self.selected_origin = None
						self.dists = {}
						self.parents = {}
						self.planned_route = []
						self.simulator = None
						self.sim_running = False
						self.last_message = "Origen limpiado"
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
							self.graph.toggle_edge_block(u, v)
							acted = True
						self.last_message = "Arista bloqueada/habilitada" if acted else "No se encontró arista cercana"
					except Exception as e:
						self.last_message = f"Error al bloquear: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
					# Recalcular Dijkstra desde el origen
					if self.selected_origin is None:
						self.last_message = "Define un origen antes de R"
					else:
						try:
							self.dists, self.parents = dijkstra(self.graph, self.selected_origin)
							self.last_message = f"Dijkstra listo ({len(self.dists)} alcanzables)"
						except Exception as e:
							self.last_message = f"Error Dijkstra: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_p:
					self.show_path_to_hover = not self.show_path_to_hover
					self.last_message = "Ruta hover activada" if self.show_path_to_hover else "Ruta hover desactivada"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_g:
					# Plan estático mejorado: presupuesto por burro + costo de visita por estrella
					if self.selected_origin is None:
						self.last_message = "Selecciona origen antes de G"
					else:
						try:
							if not self.donkey:
								self.last_message = "Burro no disponible para plan"
							else:
								route, used = greedy_max_visits_enhanced(self.graph, self.selected_origin, self.donkey)
								self.planned_route = route
								# Prepare simulator for the new plan
								try:
									self.simulator = Simulator(self.graph, self.donkey, self.planned_route)
									self.sim_running = False
									self._last_step_time = 0.0
								except Exception:
									self.simulator = None
									self.sim_running = False
								budget = energy_budget_from_donkey(self.donkey)
								self.last_message = f"Plan listo: {len(route)} nodos, costo≃{used:.1f} / presupuesto {budget:.1f}"
						except Exception as e:
							self.last_message = f"Error plan: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_t:
					# Exportar reporte de la ruta planeada
					if not self.planned_route:
						self.last_message = "No hay plan para exportar"
					else:
						try:
							budget = energy_budget_from_donkey(self.donkey) if self.donkey else 0.0
							report = build_route_report(self.graph, self.donkey, self.planned_route, total_cost=budget)
							save_route_report("plan_report.json", report)
							self.last_message = "Reporte exportado: plan_report.json"
						except Exception as e:
							self.last_message = f"Error exportando: {e}"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
					# Toggle play/pause simulation
					if not self.planned_route:
						self.last_message = "Calcula un plan (G) antes de simular"
					else:
						if not self.simulator:
							try:
								self.simulator = Simulator(self.graph, self.donkey, self.planned_route)
								self._last_step_time = 0.0
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
								self.simulator = Simulator(self.graph, self.donkey, self.planned_route)
							except Exception as e:
								self.last_message = f"No se pudo preparar simulación: {e}"
					if self.simulator and not self.simulator.state.finished:
						st = self.simulator.step()
						self.last_message = f"Tick {st.tick} en {st.current_star} E={st.energy_pct:.1f}% L={st.life_remaining:.1f}kg"
						if st.dead:
							self._sound.play_death()
							self.last_message += " | MUERTE"

			# Auto-stepping when running
			now_ms = pygame.time.get_ticks()
			if self.sim_running and self.simulator and not self.simulator.state.finished:
				interval = 1000.0 / max(0.1, self.sim_speed)
				if (now_ms - self._last_step_time) >= interval:
					st = self.simulator.step()
					self._last_step_time = now_ms
					if st.dead:
						self._sound.play_death()
						self.sim_running = False
						self.last_message = "El burro ha muerto"
					elif st.finished:
						self.sim_running = False
						self.last_message = "Simulación finalizada"

			self.draw(screen)
			pygame.display.flip()
			clock.tick(60)
		pygame.quit()

