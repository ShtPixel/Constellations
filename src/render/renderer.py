from typing import Dict, Tuple, Set
import math

# Import application settings (colors, etc.)
try:
	from src import settings as app_settings
except ModuleNotFoundError:
	import settings as app_settings

try:
	import pygame
except Exception:  
	pygame = None


class GraphRenderer:
	#Recibe el grafo (modelo construido por el loader) y parámetros de ventana y márgenes.
	# pixel_coords=True: interpreta las coordenadas del JSON como píxeles de pantalla (origen arriba-izquierda).
	# pixel_coords=False: ajusta y escala automáticamente para encajar todo el mundo dentro de la ventana.
	def __init__(self, graph, width: int = 800, height: int = 600, min_size: int = 200, margin: int = 0, pixel_coords: bool = True):
		self.graph = graph
		self.width = max(width, min_size)
		self.height = max(height, min_size)
		self.margin = margin
		self.pixel_coords = bool(pixel_coords)
		# Use centralized color settings to avoid duplication
		self.bg_color = getattr(app_settings, "BACKGROUND", (10, 10, 20))
		self.edge_color = getattr(app_settings, "EDGE", (200, 200, 220))
		self.edge_blocked_color = getattr(app_settings, "EDGE_BLOCKED", (140, 140, 160))
		self.shared_color = getattr(app_settings, "SHARED", (220, 40, 40))
		# Grid and labeling settings (with safe defaults if not in settings)
		self.grid_color = getattr(app_settings, "GRID_COLOR", (35, 35, 50))
		self.grid_spacing = int(getattr(app_settings, "GRID_SPACING", 50))
		self.id_color = getattr(app_settings, "ID_COLOR", (235, 235, 235))
		self.constellation_colors: Dict[str, Tuple[int, int, int]] = {}
		self.selected_origin: int | None = None
		self.selected_target: int | None = None
		self.mouse_pos: Tuple[int, int] = (0, 0)
		self.hover_edge: Tuple[int, int] | None = None
		self.font = None
		self.small_font = None
		self.last_message: str | None = None
		self._compute_palette()
		self._compute_transform()

	def _compute_palette(self):
		# Palette from settings only: use name-based mapping first, then cycle PALETTE.
		names = list(self.graph.constellations.keys())
		by_name = getattr(app_settings, "CONSTELLATION_COLORS", {}) or {}
		palette = getattr(app_settings, "PALETTE", [
			(255, 99, 132), (54, 162, 235), (255, 206, 86), (75, 192, 192),
			(153, 102, 255), (255, 159, 64), (99, 255, 132), (132, 99, 255), (255, 99, 255)
		])
		for i, name in enumerate(names):
			if name in by_name:
				self.constellation_colors[name] = by_name[name]
			else:
				self.constellation_colors[name] = palette[i % len(palette)]

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

		# Draw selection highlights
		if self.selected_origin is not None and self.selected_origin in self.graph.stars:
			so = self.graph.stars[self.selected_origin]
			x, y = self.world_to_screen(so.x, so.y)
			pygame.draw.circle(screen, (255, 220, 0), (x, y), 10, 2)  # amarillo
		if self.selected_target is not None and self.selected_target in self.graph.stars:
			st = self.graph.stars[self.selected_target]
			x, y = self.world_to_screen(st.x, st.y)
			pygame.draw.circle(screen, (0, 220, 255), (x, y), 10, 2)  # cian

		# If both selected, highlight edge if exists
		if self.selected_origin is not None and self.selected_target is not None:
			u, v = self.selected_origin, self.selected_target
			if u in self.graph.adjacency and v in self.graph.adjacency[u]:
				su = self.graph.stars[u]
				sv = self.graph.stars[v]
				x1, y1 = self.world_to_screen(su.x, su.y)
				x2, y2 = self.world_to_screen(sv.x, sv.y)
				pygame.draw.line(screen, (255, 200, 0), (x1, y1), (x2, y2), 4)
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

		# HUD: instructions and selection info
		if self.font:
			info_lines = [
				"Click: seleccionar origen/destino",
				"B: bloquear/habilitar arista (entre selección o arista más cercana)",
				"C: limpiar selección | ESC: salir",
			]
			if self.selected_origin is not None:
				info_lines.append(f"Origen: {self.selected_origin}")
			if self.selected_target is not None:
				info_lines.append(f"Destino: {self.selected_target}")
			if self.last_message:
				info_lines.append(self.last_message)
			self._draw_text_block(screen, info_lines, (10, 10))
			self._draw_legend(screen, (10, 80))

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
		self.font = pygame.font.SysFont(None, 18)
		self.small_font = pygame.font.SysFont(None, 12)
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
					# Left click: select origin then target; click vacío limpia selección
					sid = self._star_at_pixel(*event.pos)
					if sid is not None:
						if self.selected_origin is None or (self.selected_origin is not None and self.selected_target is not None):
							# start new selection
							self.selected_origin = sid
							self.selected_target = None
						elif self.selected_origin is not None and sid != self.selected_origin:
							self.selected_target = sid
					else:
						# Click en vacío: limpiar selección
						self.selected_origin = None
						self.selected_target = None
						self.last_message = "Selección limpiada"
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_c:
					# Clear selection
					self.selected_origin = None
					self.selected_target = None
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_b:
					# Toggle block on selected edge or nearest edge to mouse
					try:
						acted = False
						if self.selected_origin is not None and self.selected_target is not None:
							u, v = self.selected_origin, self.selected_target
							if u in self.graph.adjacency and v in self.graph.adjacency[u]:
								self.graph.toggle_edge_block(u, v)
								acted = True
							elif v in self.graph.adjacency and u in self.graph.adjacency[v]:
								self.graph.toggle_edge_block(v, u)
								acted = True
						if not acted:
							px, py = self.mouse_pos
							edge = self._nearest_edge(px, py)
							if edge:
								u, v = edge
								self.graph.toggle_edge_block(u, v)
								acted = True
						self.last_message = "Arista bloqueada/habilitada" if acted else "No se encontró arista cercana"
					except Exception as e:
						self.last_message = f"Error al bloquear: {e}"

			self.draw(screen)
			pygame.display.flip()
			clock.tick(60)
		pygame.quit()

