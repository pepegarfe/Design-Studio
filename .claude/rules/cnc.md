---
paths:
  - cnc_gcode.py
  - auditar_gcode.py
  - studio_backend.py
  - studio_ui.html
---
# CNC: generador de G-code (`.tap`) y lo que la interfaz le pide

Verificado contra el código el 18-nov-2026 (movido del `CLAUDE.md`). Historia: [[cnc-richauto]],
[[rebaba-microsegmentos]], [[esquinas-bruscas]]. Pruebas: `python3 auditar_gcode.py`.

- ⚠️ **CNC: el cajeado ENCADENA anillos contiguos** (`_chain_rings`): en vez de retirarse a
  altura de seguridad entre uno y otro, pasa al siguiente con un movimiento corto a
  profundidad de corte. **La condición de unión es de SEGURIDAD, no de optimización**: solo
  se une si el tramo recto se queda dentro de `poly.buffer(-radio)` (por donde el CENTRO de
  la fresa puede andar). Si un cajeado se parte en ISLAS, unirlas en línea recta **arruina la
  pieza**. Se usa `covers` y no `contains` (el anillo exterior va justo sobre ese borde).
  Una cadena es un trayecto **ABIERTO**: entra con `_open_pass` (no `_ring_pass`, que da la
  vuelta con `s % perim`) y **entre pasadas de profundidad DEBE subir y volver al inicio por
  el aire** — sin eso cortaría en línea recta del extremo lejano al principio.
  ⚠️ **CADA pasada de un trayecto abierto con rampa REGRESA sobre la rampa a fondo**
  (`back=True`) antes de recorrerlo entero: en un anillo cerrado la vuelta completa repasa la
  rampa, pero en uno abierto nada lo hace. Sin eso (25-nov-2026) la última dejaba una CUÑA en el
  fondo (una línea a 8 mm quedaba de 5.3 a 8 mm en sus primeros 25 mm) y cada pasada intermedia
  bajaba en VERTICAL en material sin cortar. Lo vigilan `caso_rampa_abierta` y
  `caso_barrido_25nov` en `auditar_gcode.py`.
- ⚠️ **Tres más del barrido del 25-nov-2026** (3341 combinaciones medidas punto por punto):
  - **Espiral + acabado**: el anillo de acabado también necesita la vuelta plana final (se la
    saltaba con `and not finish`: quedaba la pared en tornillo y 8 de 8 mm sin cortar tras el
    arranque).
  - **`_zigzag_pass` mete los bordes de los puentes como vértices** (igual que `_ring_pass`):
    sin ellos el vaivén cruzaba el puente en línea recta y le comía hasta 0.9 mm.
  - **Derecha/Izquierda sobre una figura CERRADA se desplaza como polígono** (`cerrada()` en
    `_offset_side`): `offset_curve` la dejaba ABIERTA por el lado convexo y se cortaba como
    línea, con todas las trampas de los abiertos.
  Queda, MENOR: con puentes, si una pasada arranca sobre la subida de un puente, baja en
  vertical hasta 0.38 mm (49 de 3341 casos). El barrido está en la memoria
  ([[barrido-cnc-25-nov]]).
- ⚠️ **Rendimiento del Corte (12-nov-2026).** Tres causas de "calcular tarda segundos", y su arreglo:
  (1) `_point_at()` va por **búsqueda binaria** (`bisect`): se llama una vez POR VÉRTICE de cada
  pasada y de corrido era cuadrática — un cajeado con rampa tardaba 8× (1.06 s → 0.17 s; G-code
  idéntico). ⚠️ Cualquier función nueva que se llame por vértice NO puede recorrer la polilínea.
  (2) **Memoria de recorridos en la UI** (`memoPrev`, `memoTap`): cada Calcular, Revisar y la vista
  3D pedían de nuevo TODOS los cortes; la llave es el pedido entero, así que se invalida sola.
  (3) **Vista 3D**: los `.tap` se piden A LA VEZ (antes en fila) y, mientras llegan, **se oculta el
  resultado anterior y Reproducir queda apagado** (`S3.tok`): si no, parecía que "no actualizaba" y
  animaba el corte VIEJO hasta saltar al nuevo. Señal para la próxima: en la Mac todo esto tarda
  décimas; **Railway es varias veces más lento**, así que lo que aquí es 1 s allá se siente roto.
- ⚠️ **CNC, cajeado (12-nov-2026):** tres cosas sobre los anillos de siempre.
  (1) **Pasada de acabado en la pared** (`make_pocket(last_pass=…)`, mismo campo que la "última
  pasada separada" del perfil): el vaciado deja esa cáscara y al final va un anillo a la medida,
  en UNA pasada a profundidad completa (sale como `(anillo, True)`, igual que en perfiles). Sin
  ella la pared se corta en cada nivel y quedan las líneas de las pasadas.
  (2) **El primer anillo de cada cadena va a `_SLOT_FEED` (60 %) del avance**: ahí la fresa abre
  camino a todo su ancho. La cadena sale como `(puntos, False, mm_a_ranura)` y lo lee `_rslot()`;
  ⚠️ `_rot_to_nearest` debe conservar TODOS los elementos de la tupla, no solo los dos primeros.
  Con el acabado apagado el RECORRIDO es idéntico al de antes; solo cambia esa F (≈2 % del largo).
  (3) **Paso lateral > 50 % = islas sin cortar** entre anillos: se avisa (`_cnc_warnings`), no se
  corrige. En la UI un cajeado NUEVO nace con rampa y acabado encendidos (`nuevaTp`).
  Descartado a propósito: rayado en zigzag (peor pared, mismo recorrido) y desbaste
  adaptativo/trocoidal (miles de movimientos cortos: justo lo que hace tartamudear al RichAuto).
- ⚠️ **CNC: `_passes()` reparte la profundidad POR IGUAL**, y `pass_depth` es el **máximo**
  de una pasada, no su altura fija. **No volver a "pasadas llenas + lo que sobre"**: 6 mm con
  pasada de 5 daba `[5, 6]` — una segunda pasada de **1 mm** que a todo el ancho de la fresa
  **frota en vez de morder** (quema, desafila, deja rebaba) y cuesta la vuelta entera igual.
- ⚠️ **CNC: la salida de TODO `buffer()`/`offset_curve()` pasa por `_simplify()`**
  (`cnc_gcode.py`, Douglas-Peucker a `_SIMPLIFY_MM` = 0.01 mm). **No lo quites: no es cosmética.**
  Shapely redondea CADA vértice con un arco, así que en un contorno curvo (giros de ~1°) siembra
  un segmento de ~0.05 mm pegado a cada segmento bueno — el 30 % de la trayectoria. A 4000 mm/min
  ese movimiento dura medio milisegundo, el RichAuto **no puede ejecutarlo y frena**: la máquina
  tartamudea cientos de veces por contorno, el bocado de cada filo se vuelve errático y **la madera
  sale con rebaba** (caso real, ago-2026). Señal: si dos archivos cortan la MISMA geometría y uno
  vibra, no compares las trayectorias — **compara el largo de los movimientos**; un patrón
  largo-corto-largo-corto es geometría de computadora que nadie limpió.
- ⚠️ **CNC: TODO movimiento que baja entrando al material baja, como MÁXIMO, a la velocidad
  de PICADA (componente VERTICAL)** — lo emite `_emit_cut()`, por segmento: F = avance de corte
  recortado a `plunge × largo3D / bajada`; una bajada vertical pura va a `plunge`. Una rampa
  avanza y baja a la vez; la fresa estrena material con su **punta**, donde peor corta.
  Emitirla al avance de corte SIN límite la hundía a **686 mm/min verticales de mediana, con
  picos de 2499**, contra los 90/381 de Aspire (ago-2026). ⚠️ Pero **no volver a mandar la
  rampa ENTERA a `plunge`** (así estuvo de ago a nov-2026): casi en plano, a 381 mm/min y 16000
  RPM la viruta era 0.012 mm/filo, la fresa RASPABA y humeaba — el 28 % del tiempo del
  `gato-2 doble.tap` (25-nov-2026; Jose tuvo que bajar a S4). La auditoría vigila las dos
  cosas (velocidad vertical ≤ picada y F entre picada y corte).
- ⚠️ **CNC: la salida del `.tap` es MODAL** (`_modal()`, la última pasada de `build_jobs`):
  el `G01` y la `F` solo se escriben cuando cambian, los ejes que no cambian se omiten y los
  movimientos de **largo cero se borran** (frenan al control sin cortar nada). **No la quites:
  no es cosmética** — el DSP lee y ejecuta bloque a bloque, así que cada carácter compite con
  el movimiento, el mismo mecanismo de `_simplify`. Bajó de **32.3 a 17.6 caracteres por
  bloque** (Aspire: 17.1). Dos cautelas a respetar: **los G00 conservan SIEMPRE su palabra G**
  (son cuatro docenas, no ahorran nada y no vale dejar un rápido al estado modal), y **tras
  cada G00 se reescribe la F** aunque no haya cambiado.
- ⚠️ **Todo lector del `.tap` debe arrastrar el modo vigente.** `parseTap()` (vista 3D, en
  `studio_ui.html`) descartaba las líneas que no empiezan con `G` y al hacer modal la salida
  **se quedó viendo 68 movimientos de 8812** — vista 3D casi vacía, **sin ningún error**. Si
  agregas otro lector de G-code, la prueba es correr el MISMO archivo en los dos formatos y
  exigir la misma lista de movimientos.
- ⚠️ **CNC: el avance del archivo tiene que ser alcanzable, o es fantasía.** Para llegar a
  4000 mm/min la máquina necesita **3.7–11 mm solo de aceleración**, y el segmento típico de
  un diseño curvo mide **0.7 mm**: pedir F4000 dejaba a la máquina **el 94 % del recorrido
  acelerando o frenando** (contra el 57 % de Aspire a F1270) para ahorrar **48 segundos** —
  bocado errático y rebaba. Señal: **compara el avance pedido contra la distancia que hay
  para acelerar** (`v²/2a`); si el segmento típico es más corto, el número del archivo no lo
  va a ver nadie. Esto vive en los **presets de fresa**, no en el código: el código no valida
  esa relación (candidato a aviso en la UI).
- ⚠️ **CNC: la profundidad por pasada se fija en DOS sitios, y gana el del formulario.** La
  biblioteca de fresas trae `pass_depth` (el máximo), pero el campo **"Pasadas"** de la
  operación pasa por `effPassDepth()` (`studio_ui.html`), que devuelve **`profundidad / N`**
  en cuanto escribes un N distinto del automático — y **ese N sobrevive a que cambies la
  biblioteca**. Caso real (ago-2026): la biblioteca en 5.0 mm daría 3 pasadas de 4.07 en un
  corte de 12.2, pero el archivo salió con **2 de 6.10** porque el formulario tenía un 2
  escrito a mano. **Antes de culpar al preset, mira cuál de los dos manda**; la cuenta del
  archivo lo delata (12.2/2 = 6.1 exacto es imposible con `pass_depth` 5.0).
- ⚠️ **CNC: lo que el generador corrige u omite, lo AVISA** (`_cnc_warnings()` en
  `studio_backend.py`, desde nov-2026): corte fuera de la mesa o de la PLACA (`material.sheet`), más hondo que el material, pasada
  mayor que el diámetro, contornos con menos puentes o sin ninguno (`tab_report`), figuras más
  chicas que la fresa (`count_unfit`). Llegan en `warnings` de la vista previa y del `.tap`; la UI
  los deja en una caja fija (`#tpWarn`) y **vuelve a pedirlos justo antes de guardar**. Son avisos,
  no errores (la cama de sacrificio es legítima). **Si agregas otra corrección silenciosa al
  generador, agrégale su aviso**: `_tab_zones` devolvía `None` y las piezas chicas salían sin
  puentes sin que nadie se enterara. El campo "Pasadas" vuelve a automático tras cada Calcular
  nuevo y al cambiar de fresa (`resetPasses`).
- ⚠️ **Marchas de fábrica = las MEDIDAS girando el husillo** (`[100, 12000…18000]`, S1 parado),
  no las del menú del handle (`_GEARS_MENU`, que `cnc_get()` reemplaza si todavía está guardada).
  ✅ Confirmadas por Jose leyendo el variador (25-nov-2026): S4=14000, S6=16000, S8=18000.
- ⚠️ **Un archivo puede CAMBIAR DE MARCHA entre cortes** (`build_jobs`, 26-nov-2026): cada
  trabajo usa la marcha de SU fresa; al cambiar, ya en Z segura, manda `M03 S<n>` y repite la
  espera del arranque. Antes valía la del primer trabajo EN SILENCIO. Lo avisan
  `studio_backend._avisos_marcha` y la tarjeta de Revisar (`avisoMarchas`). ⏳ Falta confirmar
  en la máquina que el A11E obedece el cambio con el husillo girando. Con una sola marcha el
  archivo sale idéntico al de antes (`caso_cambio_de_marcha` en `auditar_gcode.py`).
- ⚠️ **Cambiar `CNC_DEFAULTS` NO llega a las instalaciones que ya existen**: `cnc_get()` toma la
  lista `tools` guardada ENTERA. Para corregir un dato de fábrica en el campo, agrega una entrada
  a `_PRESET_FIXES` (`studio_backend.py`): se aplica una sola vez por `preset_rev` y solo si la
  fresa conserva los números viejos de fábrica — lo que Jose ajustó a mano no se toca.

## Puentes a mano y lo que se decidió NO hacer

- ⚠️ **CNC: puentes "A mano"** (`tabs.mode == 'manual'`, `tabs.pts` = puntos `[x, y]` en mm sobre
  el recorrido). `_ring_zones()` es el ÚNICO sitio que decide las zonas de puente de un contorno:
  lo usan el corte (`_contour_body`), los avisos (`tab_report`) y las marcas del lienzo
  (`tab_points` → `tabs_xy`). **No calcules zonas por otro lado**, o lo que se dibuja dejará de
  ser lo que se corta. Un punto vale para todo contorno a menos de medio diámetro (así el
  desbaste y el anillo de "última pasada" comparten puente). **El centro se acota para que la
  zona NUNCA cruce el empalme del anillo**: `_ring_pass` solo inserta los bordes de zona dentro
  de la vuelta, y un puente partido por el empalme podría no levantarse en un tramo recto largo.
  Punto que ya no cae sobre el corte (se movió la pieza) = se ignora **y se avisa**. En la UI:
  `tabPts` (del formulario, se aplican al Calcular), `tabEdit()`, `tabClick()`; en ese modo el
  clic en el lienzo se consume siempre (un clic fallado no debe cerrar el formulario).
  Pruebas: `caso_puentes_a_mano` en `auditar_gcode.py`. El G-code con puentes automáticos salió
  idéntico al de antes en 80 combinaciones (puentes × rampa × última pasada × lado).
- **Decidido NO hacer (12-nov-2026), no lo agregues sin hablarlo con Jose:** (a) una "pasada
  final delgada en el fondo" como la de Aspire — contradice la regla medida de `_passes()` de
  arriba (una pasada de ~1 mm frota y deja rebaba); (b) entradas laterales (*leads*) — con
  piezas acomodadas a 5 mm, una entrada por fuera puede morder la pieza vecina; necesita antes
  una comprobación de choque contra las demás figuras.
