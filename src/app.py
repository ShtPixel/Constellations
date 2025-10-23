try:
	# When executed as a module: python -m src.app
	from src.core.loader import Loader
	from src.main import run as run_main
except ModuleNotFoundError:
	# When executed directly: python src/app.py
	from core.loader import Loader
	from main import run as run_main

if __name__ == "__main__":
	# Ejecutado directamente
	loader = Loader(path_burro="data/burro.json", path_galaxies="data/galaxies.json")
	donkey, graph = loader.load()
	# Inicia visualización si pygame está disponible
	try:
		run_main()
	except RuntimeError as e:
		print(str(e))
else:
	# Ejecutado como módulo: exponer una ejecución rápida
	loader = Loader(path_burro="data/burro.json", path_galaxies="data/galaxies.json")
	donkey, graph = loader.load()
