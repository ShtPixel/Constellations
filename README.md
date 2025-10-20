proyecto_grafos_pygame/
├─ assets/
│  ├─ sounds/
│  ├─ icons/
│  └─ fonts/
├─ data/
│  ├─ constellations.json
│  ├─ galaxies.json
│  └─ burro.json
├─ src/
│  ├─ main.py
│  ├─ settings.py
│  ├─ app.py
│  ├─ core/
│  │  ├─ models/
│  │  │  ├─ star.py
│  │  │  ├─ constellation.py
│  │  │  ├─ galaxy.py
│  │  │  ├─ donkey.py
│  │  │  └─ graph.py
│  │  ├─ services/
│  │  │  ├─ json_loader.py
│  │  │  ├─ graph_builder.py
│  │  │  ├─ simulator.py
│  │  │  └─ report_generator.py
│  │  └─ interfaces/
│  │     ├─ i_loader.py
│  │     ├─ i_renderer.py
│  │     └─ i_simulator.py
│  ├─ render/
│  │  ├─ renderer.py
│  │  ├─ animator.py
│  │  └─ hud.py
│  ├─ gui/
│  │  ├─ ui_manager.py
│  │  ├─ buttons.py
│  │  └─ panels.py
│  ├─ sound/
│  │  └─ sound_manager.py
│  └─ utils/
│     ├─ math_utils.py
│     └─ colors.py
└─ tests/



Las siguientes son laas descripciones y el uso de la etiquetas con base a las constelaciones en el archivo .JSON

Campo            Descripción                                          Uso                          

`id`             Identificador único                                  Clave principal              
`label`          Nombre visible                                       Mostrar en el mapa           
`linkedTo`       Lista de conexiones y distancias                     Aristas                      
`radius`         Tamaño del nodo                                      Escala visual                
`timeToEat`      Tiempo para consumir 1 kg de pasto                   Cálculo energético           
`amountOfEnergy` Energía obtenida por pasto (parecido a bonificación) Factor para comer            
`coordenates`    Posición (x, y)                                      Dibujado en Pygame           
`hypergiant`     Si la estrella es hipergigante                       Permite salto entre galaxias 

y estas las de el burro o nave

 Campo                  Interpretación                      Uso                                    

 `burroenergiaInicial`  % de energía inicial (1–100)        `Donkey.energy_pct`                    
 `estadoSalud`          Salud inicial                       define rendimiento al comer/investigar 
 `pasto`                kg disponibles en bodega            `Donkey.fodder_kg`                     
 `startAge`             Edad actual                         opcional para visualización            
 `deathAge`             Edad máxima o vida útil (años luz)  límite del viaje                       
 `number`               Número de identificación del burro  sin impacto funcional                  
