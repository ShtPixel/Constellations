try:
	# When executed as a module: python -m src.app
	from src.core.loader import Loader
except ModuleNotFoundError:
	# When executed directly: python src/app.py
	from core.loader import Loader

loader = Loader(path_burro="data/burro.json", path_galaxies="data/galaxies.json")
donkey, graph = loader.load()

# donkey: objeto Donkey
# graph: objeto Graph con stars y adjacency list
