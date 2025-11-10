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
           
Integré la simulación: ahora puedes generar un plan (G) y luego controlar la simulación con Space (play/pause), N (step), + / - (velocidad), y ver en el HUD energía, vida y pasto. El sonido de muerte se dispara automáticamente al morir el burro. Reporte (T) intacto. No hay errores de sintaxis en los archivos modificados.
falta: 
    Exportar log de simulación (tecla adicional).
    Mostrar progreso (%) del plan.
    Visualizar segmento actual en color distinto.
    Ajustar modelo de consumo (energía vs distancia más realista).

realizar clanup de los archivos existentes ya que hay cosas redundantes o sin uso

SOLID- FALTA APLICAR BIEN