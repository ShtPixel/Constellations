"""Interactive report viewer window.

Attempts multi-window using pygame._sdl2.video if available; falls back to full-screen overlay in the
existing display if multiple windows are not supported.
"""
from __future__ import annotations
import math
from typing import Dict, List, Any

try:
    import pygame
except Exception:
    pygame = None  # type: ignore

# Try SDL2 multi-window support
try:
    from pygame._sdl2.video import Window, Renderer
    SDL2_AVAILABLE = True
except Exception:
    SDL2_AVAILABLE = False

FONT_NAME = None
FONT_SIZE = 16
SCROLL_SPEED = 30
BG_COLOR = (18, 18, 22)
TEXT_COLOR = (235, 235, 235)
SEPARATOR_COLOR = (90, 90, 90)
ACCENT_COLOR = (255, 200, 0)


class ReportViewer:
    def __init__(self, report: Dict[str, Any], title: str = "Reporte Final", size=(800, 600)):
        self.report = report
        self.title = title
        self.size = size
        self.offset_y = 0
        self.running = False
        self.lines: List[str] = []
        self._prepare_lines()
        self.font = None

    def _prepare_lines(self):
        r = self.report
        self.lines.append(f"{self.title}")
        self.lines.append(f"Generado: {r.get('generated_at','')} ")
        donkey = r.get('donkey', {})
        self.lines.append("--- Burro inicial ---")
        self.lines.append(f"Salud: {donkey.get('salud')} Energía%: {donkey.get('energia_pct_inicial')} PastoKg: {donkey.get('pasto_kg_inicial')} Edad: {donkey.get('edad_inicial')}/{donkey.get('vida_maxima')}")
        self.lines.append("--- Ruta ---")
        self.lines.append(f"Longitud ruta: {r.get('route_length')} Estimación costo: {r.get('total_cost_estimate')}")
        self.lines.append("Estrellas:")
        for s in r.get('stars', []):
            flags = []
            if s.get('hypergiant'): flags.append('Hiper')
            if s.get('shared'): flags.append('Shared')
            fl = ("["+",".join(flags)+"]") if flags else ""
            self.lines.append(f"  #{s.get('index')} id={s.get('id')} {s.get('label')} {fl} const={','.join(s.get('constellations',[]))}")
        final = r.get('final', {})
        if final:
            self.lines.append("--- Estado final ---")
            self.lines.append(f"E%={final.get('final_energy_pct')} PastoKg={final.get('final_pasto_kg')} VidaRest={final.get('final_life_remaining')} Ticks={final.get('ticks')} Dead={final.get('dead')} Finished={final.get('finished')} Visitadas={final.get('visited_unique')}")
        detail = r.get('stars_visit_detail', [])
        if detail:
            self.lines.append("--- Detalle visitas por estrella ---")
            for d in detail:
                self.lines.append(f"* Star {d['star']} {d['label']} H={d['hypergiant']} lifeΔ={d['life_delta']} kg={d['kg_eaten']:.2f} gain={d['energy_gain']:.2f} investCost={d['invest_cost']:.2f} eatT={d['portion_eat']:.2f} invT={d['portion_invest']:.2f} E:{d['energy_before']:.1f}->{d['energy_after']:.1f} P:{d['pasto_before']:.1f}->{d['pasto_after']:.1f} L:{d['life_before']:.1f}->{d['life_after']:.1f} Salud:{d['salud_before']}->{d['salud_after']}")
        log = r.get('simulation_log', [])
        if log:
            self.lines.append("--- Log eventos (recortado) ---")
            for e in log:
                if e.get('event') == '...trimmed...':
                    self.lines.append(f"  ... {e.get('count')} eventos omitidos ...")
                else:
                    self.lines.append(f"  tick={e.get('tick')} star={e.get('star')} evt={e.get('event')} E={e.get('energy_pct'):.1f} Vida={e.get('life_remaining'):.1f} Pasto={e.get('pasto_kg'):.1f}")
        self.lines.append("--- Fin reporte ---")
        self.lines.append("ESC / Q: cerrar | Flechas / rueda: scroll")

    def _render_lines(self, surface):
        y = 10 - self.offset_y
        for i, line in enumerate(self.lines):
            color = TEXT_COLOR
            if i == 0:
                color = ACCENT_COLOR
            if line.startswith('---'):
                color = SEPARATOR_COLOR
            text_surf = self.font.render(line, True, color)
            surface.blit(text_surf, (16, y))
            y += text_surf.get_height() + 4

    def run(self):
        if pygame is None:
            return  # no display available
        if SDL2_AVAILABLE:
            # Multi-window approach
            win = Window(self.title, size=self.size)
            renderer = Renderer(win)
            # Basic font
            pygame.font.init()
            self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE)
            self.running = True
            clock = pygame.time.Clock()
            while self.running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_ESCAPE, pygame.K_q):
                            self.running = False
                        elif event.key == pygame.K_UP:
                            self.offset_y = max(0, self.offset_y - SCROLL_SPEED)
                        elif event.key == pygame.K_DOWN:
                            self.offset_y = self.offset_y + SCROLL_SPEED
                    elif event.type == pygame.MOUSEWHEEL:
                        self.offset_y = max(0, self.offset_y - event.y * SCROLL_SPEED)
                renderer.color = BG_COLOR
                renderer.clear()
                # Create a temporary surface to render text, then copy
                surf = pygame.Surface(self.size)
                surf.fill(BG_COLOR)
                self._render_lines(surf)
                tex = pygame.image.frombuffer(pygame.image.tostring(surf, 'RGB'), self.size, 'RGB')
                renderer.copy(tex)
                renderer.present()
                clock.tick(60)
            win.destroy()
        else:
            # Fallback: modal overlay on existing display
            screen = pygame.display.get_surface()
            if not screen:
                return
            pygame.font.init()
            self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE)
            overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            self.running = True
            clock = pygame.time.Clock()
            while self.running:
                for event in pygame.event.get():
                    if event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_ESCAPE, pygame.K_q):
                            self.running = False
                        elif event.key == pygame.K_UP:
                            self.offset_y = max(0, self.offset_y - SCROLL_SPEED)
                        elif event.key == pygame.K_DOWN:
                            self.offset_y += SCROLL_SPEED
                    elif event.type == pygame.MOUSEWHEEL:
                        self.offset_y = max(0, self.offset_y - event.y * SCROLL_SPEED)
                overlay.fill((0, 0, 0, 220))
                self._render_lines(overlay)
                screen.blit(overlay, (0, 0))
                pygame.display.flip()
                clock.tick(60)
            # Clear overlay at exit (force redraw by caller on next frame)
            screen.fill((0,0,0))
            pygame.display.flip()

__all__ = ["ReportViewer"]
