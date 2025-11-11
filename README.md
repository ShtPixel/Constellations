## Constellations: Visor y Simulador de Recorridos en Grafos

Este proyecto visualiza y simula recorridos sobre un grafo de estrellas agrupadas en constelaciones. Un "burro" (agente) se desplaza, investiga y come pasto en cada estrella mientras su energía y vida se modifican. Se incluyen distintos planificadores basados en Dijkstra para trazar rutas según criterios (máximas visitas, vida restante, versión pura con valores iniciales, beam search, etc.).

### Objetivos principales
1. Cargar constelaciones y atributos de estrellas desde JSON (`data/galaxies.json`).
2. Cargar el estado inicial del burro y configuración UI desde `data/burro.json`.
3. Dibujar el grafo y permitir interacción (bloqueo de aristas, selección de origen, hipersalto en hipergigantes).
4. Planificar rutas bajo diferentes estrategias (greedy mejorado, fase 2 pura, modos optimizados por vida, beam search).
5. Simular paso a paso el recorrido: consumo de vida por distancia, cambios de energía por comer/investigar, efectos especiales en hipergigantes.
6. Generar reportes JSON de ruta y reporte final de la simulación.
7. Proveer HUD con barras de energía, vida y pasto y detalles de visitas.

### Estructura actual del proyecto

```
assets/
    assets.manifest.json       # Mapeo lógico para imágenes/sonidos (background, donkey, death.mp3)
    images/
        background.png           # Fondo principal del visor
        donkey.png               # Sprite del burro (opcional, si no se usa círculo)
    sounds/
        death.mp3                # Sonido reproducido al morir el burro
data/
    galaxies.json              # Definición de constelaciones y estrellas (id, enlaces, atributos)
    burro.json                 # Estado inicial del burro + configuración UI
src/
    main.py                    # Punto de entrada principal (carga y lanza renderer)
    app.py                     # Entrada alternativa para ejecución modular
    core/
        models.py                # Clases: Star, Constellation, Donkey, Edge, Graph
        loader.py                # Lectura y normalización de JSON (burro y galaxias)
        planner.py               # Dijkstra + planificadores (greedy, puro, modos vida, beam)
        simulator.py             # Avance de la simulación, efectos por visita, hipersalto
        reporter.py              # Generación de reportes de ruta y final
        assets.py                # Carga opcional del manifest para imágenes/fuentes
    render/
        renderer.py              # Lógica de dibujo, HUD, animación, entrada de usuario
        hud.py                   # (Apoyo HUD; puede contener utilidades visuales)
        report_viewer.py         # Ventana emergente para ver reportes formateados
    sound/
        sound_manager.py         # Inicializa mixer y reproduce sonidos (muerte)
    utils/                     # (Actual vacío, reservado para utilidades futuras)
README.md
```

### Descripción de archivos clave

- `main.py`: Crea el `Loader`, carga burro y grafo, obtiene configuración UI y entrega todo a `GraphRenderer`.
- `app.py`: Punto de entrada alternativo compatible con `python -m src.app` (facilita ejecución modular). Reusa `main.run`.
- `core/models.py`: Define las entidades. `Graph` gestiona nodos, constelaciones y aristas bidireccionales; ofrece utilidades como `toggle_edge_block` y recomputar estrellas compartidas.
- `core/loader.py`: Parsea JSON, normaliza nombres de salud, mezcla links duplicados, garantiza bidireccionalidad y marca estrellas compartidas.
- `core/planner.py`: Implementa `dijkstra` y varios planificadores:
    - `dijkstra`: rutas más cortas desde un origen.
    - `greedy_max_visits_enhanced`: usa presupuesto de energía derivado del burro y costo estático de visita.
    - `greedy_max_visits_pure`: fase 2 estricta con valores iniciales (sin efectos ni recargas dinámicas).
    - `max_stars_before_death` / `optimal_max_visits_life`: optimizan número de estrellas usando vida restante como presupuesto.
    - `optimal_max_visits_life_beam`: variante beam search para mejorar rendimiento en grafos grandes.
- `core/simulator.py`: Avanza tramo a tramo una ruta planificada, aplica consumo de vida y energía, registra visitas (porciones de comer/investigar), actualiza salud según energía y maneja hipersalto en hipergigantes (recharge + duplicación de pasto). Emite estados que el renderer usa para animar.
- `core/reporter.py`: Construye reportes JSON (ruta y final). Reporte final agrega detalles por visita (energía antes/después, pasto consumido, deltas de vida, salud) y un log recortado.
- `core/assets.py`: Carga opcional del manifest y acceso cómodo a imágenes/sonidos/fuentes.
- `render/renderer.py`: Dibuja fondo, grid, estrellas (círculos escalados), ruta y burro animado. Gestiona HUD (barras de energía, vida y pasto), modales (hipersalto, edición de efectos), alertas efímeras y control de velocidad.
- `render/hud.py`: Complementos de HUD (si se usan utilidades separadas).
- `render/report_viewer.py`: Presenta un reporte final en ventana Pygame formateada.
- `sound/sound_manager.py`: Inicializa mixer; carga `death.mp3` vía manifest; reproduce al detectar muerte del burro.
- `utils/`: Actualmente vacío; mantenido para futuras funciones auxiliares (ej. cálculos estadísticos, formatos).

### Explicación detallada de Dijkstra en este proyecto

La función `dijkstra(graph, source, include_blocked=False)` en `core/planner.py` implementa el algoritmo clásico de caminos más cortos de un solo origen sobre un grafo ponderado sin pesos negativos.

Pasos clave:
1. Inicializa `dist[source]=0` y usa una cola de prioridad (heap) con tuplas `(distancia, nodo)`.
2. Extrae el nodo con distancia mínima pendiente. Si la distancia extraída es mayor que la registrada (ya se encontró mejor), se descarta.
3. Para cada vecino `v` de `u` se calcula `nd = d + edge.distance`. Si `nd` mejora `dist[v]`, se actualiza `dist[v]` y `parent[v]=u` y se reinserta en el heap.
4. Si `include_blocked=False`, se saltan aristas marcadas como bloqueadas (permitiendo planificación bajo condiciones dinámicas). Si es True, se ignoran los bloqueos y el grafo se considera totalmente transitable.
5. Al terminar, `dist` contiene las distancias mínimas alcanzadas y `parent` define el árbol de rutas óptimas para reconstruir caminos con `reconstruct_path`.

Caracteristicas particulares de esta implementación:
- Usa `graph.adjacency[u][v].distance` como peso directo.
- No introduce heurísticas (no es A*), garantizando óptimo para cada par alcanzable.
- La complejidad es O((V+E) log V) gracias a `heapq`.
- El diseño permite acumular distancia real y luego sobre ella se construyen capas de lógica de planificación (sumando costos de visita, factores de energía/vida, filtrando bloqueadas, etc.).
- La tabla `parent` devuelve camino exacto incluyendo intermedios, lo que algunos planificadores usan para expandir la ruta con nodos transitados.

Ejemplo conceptual de uso interno:
```python
dist, parent = dijkstra(graph, origen)
for destino, d in dist.items():
        camino = reconstruct_path(parent, destino)
        # 'camino' es la secuencia óptima de nodos desde origen a destino
```

### Estrategias de planificación (resumen)
- Greedy mejorado: mezcla costo de movimiento + costo estático de visitar; recalcula presupuesto si visita hipergigante.
- Puro (fase 2): usa snapshot inicial, separa presupuesto de energía y vida, ignora efectos dinámicos y no añade intermedios como visitas.
- Modo 1 / Óptimos por vida: buscan maximizar estrellas antes de consumir vida, usando DFS/Backtracking y evitando repetir cualquier nodo (incluye intermedios).
- Beam Search: poda expansiones manteniendo sólo los estados más prometedores, acelerando en grafos medianos/grandes.

### Simulación y efectos
- Cada tramo consume vida igual a la distancia del tramo; energía se ajusta por comer/investigar según salud y configuración.
- Hipergigantes: recarga parcial energía y duplica pasto (en planificadores dinámicos).
- Salud se recalcula por percentil de energía (Moribundo/Mala/Buena/Excelente) y puede cambiar por efectos de estrellas si se edita.

### Controles básicos (en renderer)
- Click: seleccionar origen y autoplan (si se habilita auto-plan).
- G / H: distintos modos de planificación (enhanced / puro).
- N / Space: avanzar un tick / ejecutar simulación continua.
- B: bloquear/desbloquear arista cercana.
- R: calcular distancias (Dijkstra) y mostrar cercanas.
- T: abrir reporte final.
- +/-: ajustar velocidad.
- Hipersalto: modal al llegar a hipergigante (si se activa).

### Cómo ejecutar
```powershell
python src/main.py
```
Requisitos: Python 3.12+, `pygame` instalado (`pip install pygame`). Si falta audio o assets, el sistema degrada con fallbacks.

### Reportes
Al finalizar (muerte o ruta completa) se genera un reporte JSON con:
- Resumen del burro inicial.
- Longitud y orden de la ruta.
- Conjunto de constelaciones visitadas.
- Detalle por estrella (energía/vida antes y después, pasto consumido, investigación, salud).
- Log de eventos recortado si excede un límite.

### Limpieza y estado actual
- Se eliminaron referencias a sprites de estrellas (ahora círculos vectoriales).
- Fondo `background.png` activo bajo las estrellas.
- Sonido de muerte ahora usa `death.mp3`.
- Carpeta `utils/` vacía pero reservada.

### Próximas mejoras sugeridas
- Replan automático al detectar tramo bloqueado.
- Persistencia y replay de simulaciones.
- Panel de métricas agregadas en tiempo real (densidad, clustering, etc.).
- Tests unitarios para planners (validar óptimos en grafos pequeños).

---
Este README refleja el estado corregido y actual del proyecto, reemplazando el contenido previo y aclarando responsabilidades de cada módulo.
