proyecto_grafos_pygame/
├─ assets/
│  ├─ sounds/
│  ├─ icons/
│  └─ fonts/
├─ data/
│  ├─ galaxies.json
│  └─ burro.json
├─ src/
│  ├─ main.py                      # punto de entrada
│  ├─ app.py                       # loop principal pygame
│  ├─ settings.py                  # configuraciones globales
│  ├─ core/
│  │  ├─ models.py                 # Donkey, Star, Edge, Constellation, Graph
│  │  ├─ loader.py                 # carga y validación del JSON
│  │  ├─ simulator.py              # lógica de rutas, energía, salud, etc.
│  │  └─ report.py                 # registro de resultados
│  ├─ render/
│  │  ├─ renderer.py               # dibuja el grafo, el burro y las animaciones
│  │  └─ hud.py                    # interfaz (botones, paneles, etc.)
│  ├─ sound/
│  │  └─ sound_manager.py          # sonidos (muerte, click, etc.)
│  └─ utils/
│     ├─ math_utils.py
│     └─ colors.py
└─ README.md
           
