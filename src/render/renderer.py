from typing import Dict, Tuple, Set

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
	def __init__(self, graph, width: int = 800, height: int = 600, min_size: int = 200, margin: int = 40):
		self.graph = graph
		self.width = max(width, min_size)
		self.height = max(height, min_size)
		self.margin = margin
		# Use centralized color settings to avoid duplication
		self.bg_color = getattr(app_settings, "BACKGROUND", (10, 10, 20))
		self.edge_color = getattr(app_settings, "EDGE", (200, 200, 220))
		self.edge_blocked_color = getattr(app_settings, "EDGE_BLOCKED", (140, 140, 160))
		self.shared_color = getattr(app_settings, "SHARED", (220, 40, 40))
		self.constellation_colors: Dict[str, Tuple[int, int, int]] = {}
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
		# Map world (stars x,y) to screen coordinates
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
				# highlight shared
				if star.shared or len(star.constellations) > 1:
					pygame.draw.circle(screen, self.shared_color, (x, y), r + 3, 2)

	def run(self):
		if pygame is None:
			raise RuntimeError(
				"Pygame no está disponible. Instálalo con: pip install pygame"
			)
		pygame.init()
		screen = pygame.display.set_mode((self.width, self.height))
		pygame.display.set_caption("Constellations Viewer")
		clock = pygame.time.Clock()
		running = True
		while running:
			for event in pygame.event.get():
				if event.type == pygame.QUIT:
					running = False
				elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
					running = False

			self.draw(screen)
			pygame.display.flip()
			clock.tick(60)
		pygame.quit()

