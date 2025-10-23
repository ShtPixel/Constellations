try:
	from src.core.loader import Loader
except ModuleNotFoundError:
	from core.loader import Loader

try:
	from src.render.renderer import GraphRenderer
except ModuleNotFoundError:
	from render.renderer import GraphRenderer

from typing import Optional


def run(path_burro: str = "data/burro.json", path_galaxies: str = "data/galaxies.json",
		width: int = 900, height: int = 700):
	"""Carga datos y abre una ventana para visualizar el grafo.

	Requiere pygame instalado. Si no está disponible, lanza RuntimeError con instrucciones.
	"""
	loader = Loader(path_burro=path_burro, path_galaxies=path_galaxies)
	donkey, graph = loader.load()
	renderer = GraphRenderer(graph, width=width, height=height)
	renderer.run()


if __name__ == "__main__":
	run()

