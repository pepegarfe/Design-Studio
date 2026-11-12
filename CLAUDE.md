# CLAUDE.md — Plotter Antike

Leer **antes** de tocar el código: solo **invariantes y trampas** que no se deducen leyéndolo. La
arquitectura se descubre en `plotter_control.py` — no se documenta aquí para que no se pudra.

**Historia, decisiones y estado del trabajo → [[MEMORY]]** (`.claude/memoria/`, empezar por `estado.md`).

> Verificado contra el código el 21-jul-2026. Si ves algo que el código contradice, **corrígelo aquí**.

---

## Qué es

**Design Studio**: una app **web** (servidor `studio_server.py` + interfaz `studio_ui.html`) para
diseñar vectores y cortarlos en **plotter** (HPGL por cable, desde el navegador) o en **CNC**
(exporta `.tap`). Vive en línea en Railway y se instala como **dos PWA**: el editor (`/`) y la
estación de corte (`/estacion`).

⚠️ **Desde el 11-nov-2026 NO hay app de escritorio** (decisión de Jose): se borraron
`design_studio.py` (pywebview), el instalador, la CI de releases y `updater.py`. Consecuencias que
NO se deducen del código:
- **`plotter_control.py` se queda**: es el MOTOR (parsers, HPGL, config) que importan el backend y
  el servidor. Dentro todavía trae la app tkinter vieja (`PlotterApp`), que ya nadie abre — por eso
  el servidor necesita `libtk`. **No separar el archivo sin pedido explícito.**
- **`studio_ui.html` conserva las ramas `api()`** (el puente de pywebview): hoy `api()` siempre es
  falso y esas ramas son código muerto. No construir sobre ellas.
- Las apps de escritorio ya instaladas siguen abriendo, pero **no reciben nada nuevo**.

---

## Modelo de datos y coordenadas (convenciones, no obvias)

- **Todos los parsers devuelven coordenadas en milímetros.** Excepción interna en `SVGParser`:
  `_parse_d` y los parsers de shapes devuelven **user units** crudas; la conversión a mm la hace la
  **matriz afín** (`_root_mtx` mete el factor `PX_TO_MM`). ⚠️ **Nunca agregar `* PX_TO_MM`** en esos
  métodos: duplicarías la conversión.
- El canvas usa **Y-invertido**: en mm la Y crece hacia arriba; en pixels crece hacia abajo.
- Al cargar un archivo, el diseño se **normaliza al cuadrante positivo** (X≥0, Y≥0). Si reseteas
  posiciones, **re-aplica esa normalización** — no dejes offsets en `[0,0]` crudos, o el diseño
  aparece en Y negativa.
- **HPGL**: `UNITS_PER_MM = 40`. Serial con **XON/XOFF** activado.
- Un **"styled path"** es un dict con exactamente estas llaves útiles:
  ```python
  { "pts": [(x_mm, y_mm), ...],   # ≥2 puntos
    "fill":   (r,g,b) | None,
    "stroke": (r,g,b) | None }
  ```
  (Verás una llave `_pinched` escrita a `None` en algunos sitios: es un **vestigio muerto**, nadie
  la lee — ver "Código muerto" abajo.)

---

## Invariantes / Qué NO hacer (todo verificado contra el código)

- **No agregar `* PX_TO_MM`** en `_parse_d`, `_parse_rect`, `_parse_circle`, `_parse_line`,
  `_parse_poly` — la matriz ya convierte.
- **No usar `svgpathtools` como parser primario.** `SVGParser.parse()` siempre llama
  `_parse_basic()`, que usa `xml.etree` de la stdlib. `_parse_with_lib()` existe pero **no se
  invoca** (por eso el flag `HAS_SVG` casi no importa: el parser primario no depende de esa librería).
- **No romper el `Z/z` de `_parse_d`**: cierra el subpath actual y **continúa** parseando (no hace
  `break`).
- **Escalado de grupo (modos "Grupo" y "Todos"): el ancla es la esquina INFERIOR-IZQUIERDA** del bbox
  (`ax=min_x`, `ay=min_y`), **no el centro**. Usar el centro rompe las posiciones relativas entre
  trazados del grupo.
- **`_push_undo()` va en los métodos `_apply_*`, nunca en los `_nudge_*`** (los nudge delegan en
  apply, que ya empuja; hacerlo en ambos duplica el historial). **`open_file()` limpia ambos stacks**
  (`_undo_stack` y `_redo_stack`).
- **Rutas de recursos y config: usar `_resource()` y `_config_path()`**, nunca hardcodear. Es lo que
  hace que cada cuenta de la web lea SU carpeta (ver `.claude/rules/servidor-web.md`).
- ⚠️ **TODO JSON con `encoding='utf-8'` EXPLÍCITO**: sin él Python usa el codepage del SO (**cp1252
  en Windows**) y un `″` —lo llevan los nombres de fresa de fábrica— hace que `write_text` **trunque
  el archivo a 0 BYTES** y la config se pierda EN SILENCIO. **En Mac nunca falla**, así que no
  aparece probando aquí. `version.txt` con **`utf-8-sig`**: se come el BOM de PowerShell 5.1.
- **Refrescos de posición/escala/rotación: usar `_refresh_preview()`**, que NO resetea el zoom. **No
  llamar `set_paths()` ni `_auto_fit()`** para eso — perderías el zoom del usuario.
- **`set_paths()` y `_generate_hpgl()` siempre con `_effective_styled()`**, nunca con
  `current_styled` crudo. `_effective_styled()` aplica scale+rotación (sobre el centro del bbox
  original) y luego el offset, devolviendo dicts nuevos sin mutar el original.
- **Los `create_line` usan `smooth=False`** (con `joinstyle=MITER`, `capstyle=BUTT`). ⚠️ **No poner
  `smooth=True`**: fue eliminado a propósito para arreglar la fidelidad visual del corte. La
  suavidad de las curvas viene del **aplanado ADAPTATIVO por tolerancia** (desde 22-jul-2026):
  `_flat_cubic`/`_flat_quad`/`_arc_steps` (tolerancia relativa ~0.015% + piso 0.01 mm) y una
  pasada final `_simplify_mm` (Douglas-Peucker a 0.01 mm, en mm reales, a la salida de los TRES
  parsers). ⚠️ **No volver a muestrear curvas con N fijo de segmentos** — eso cuadriculaba los
  imports al escalarlos.
- ⚠️ **CNC: el cajeado ENCADENA anillos contiguos** (`_chain_rings`): en vez de retirarse a
  altura de seguridad entre uno y otro, pasa al siguiente con un movimiento corto a
  profundidad de corte. **La condición de unión es de SEGURIDAD, no de optimización**: solo
  se une si el tramo recto se queda dentro de `poly.buffer(-radio)` (por donde el CENTRO de
  la fresa puede andar). Si un cajeado se parte en ISLAS, unirlas en línea recta **arruina la
  pieza**. Se usa `covers` y no `contains` (el anillo exterior va justo sobre ese borde).
  Una cadena es un trayecto **ABIERTO**: entra con `_open_pass` (no `_ring_pass`, que da la
  vuelta con `s % perim`) y **entre pasadas de profundidad DEBE subir y volver al inicio por
  el aire** — sin eso cortaría en línea recta del extremo lejano al principio.
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
- ⚠️ **CNC: TODO movimiento que baja entrando al material va al avance de PICADA**, no al
  de corte — lo emite `_emit_cut()`, que decide **por segmento** (baja → `plunge`, llano →
  `feed`). Una rampa de entrada avanza y baja a la vez, así que para el control es un corte
  más; pero la fresa estrena material con su **punta**, que es donde peor corta. Emitirla al
  avance de corte la hundía a **686 mm/min verticales de mediana, con picos de 2499**, contra
  los 90/381 de Aspire en la misma pieza (ago-2026).
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
  `studio_backend.py`, desde nov-2026): corte fuera de la mesa, más hondo que el material, pasada
  mayor que el diámetro, contornos con menos puentes o sin ninguno (`tab_report`), figuras más
  chicas que la fresa (`count_unfit`). Llegan en `warnings` de la vista previa y del `.tap`; la UI
  los deja en una caja fija (`#tpWarn`) y **vuelve a pedirlos justo antes de guardar**. Son avisos,
  no errores (la cama de sacrificio es legítima). **Si agregas otra corrección silenciosa al
  generador, agrégale su aviso**: `_tab_zones` devolvía `None` y las piezas chicas salían sin
  puentes sin que nadie se enterara. El campo "Pasadas" vuelve a automático tras cada Calcular
  nuevo y al cambiar de fresa (`resetPasses`).
- ⚠️ **Marchas de fábrica = las MEDIDAS girando el husillo** (`[100, 12000…18000]`, S1 parado),
  no las del menú del handle (`_GEARS_MENU`, que `cnc_get()` reemplaza si todavía está guardada).
- ⚠️ **Cambiar `CNC_DEFAULTS` NO llega a las instalaciones que ya existen**: `cnc_get()` toma la
  lista `tools` guardada ENTERA. Para corregir un dato de fábrica en el campo, agrega una entrada
  a `_PRESET_FIXES` (`studio_backend.py`): se aplica una sola vez por `preset_rev` y solo si la
  fresa conserva los números viejos de fábrica — lo que Jose ajustó a mano no se toca.
- **Tres modos de selección/transformación** según estado: **individual** (`_sel_idx >= 0`, escala y
  rotación ABSOLUTAS), **grupo manual** (`_sel_set` no vacío, RELATIVAS) y **todos** (ambos vacíos,
  RELATIVAS). Toda transformación debe respetar los tres.
- **El modo del botón izquierdo lo controla `pan_mode`** en `DesignCanvas` (False=selección/
  rubber-band, True=pan). El campo `sel_mode` **ya no existe** — no lo reintroduzcas. El botón
  central siempre hace pan.
- **Los vectores de corte son un OVERLAY dentro de `DesignCanvas`** (`show_cut` + `cut_paths`,
  dibujados en azul). **No abrir una ventana aparte para eso** — la clase `CutCanvas` y su andamiaje
  fueron eliminados. Mantener `cut_paths` sincronizado cada vez que cambie el diseño.
- **`_set_led` no debe tocar `self.sb_led` directo** — usar `_set_sb_led()`, que tiene guard
  `hasattr` (a `_set_led` se le llama antes de que exista el LED de la barra de estado).

### Reglas de diagnóstico y plotter en el navegador

- **Regla:** fallo **intermitente** = dos cosas compitiendo; fallo en **una sola máquina** = mide ahí, no deduzcas.
- ⚠️ **Plotter en el navegador: en ANDROID no usar `navigator.serial`.** Existe, pero solo ve
  puertos **Bluetooth**: el plotter nunca aparecería, sin error. Allá el cable va por **WebUSB**
  con un driver FTDI propio (`serieUsb`/`abrirFtdi` en `<script id="motor-plotter">`) disfrazado
  de puerto Web Serial, y lo elige `serieDelNavegador()`. En computadora es al revés: WebUSB no
  sirve (el driver del sistema tiene tomado el chip). Solo FTDI; CH340/Prolific/CP210x no están.
  Probado en el Galaxy de Jose (Android 16). Prueba: `node web/test_plotter_web.mjs`.

---

### Táctil y pantallas chicas (`studio_ui.html`, nov-2026)

- **El lienzo sigue hablando "ratón"; el dedo se TRADUCE** (bloque "Táctil", junto al `wheel` del
  lienzo): un dedo = botón izquierdo, dos dedos = pellizco y desplazar, pulsación larga = clic
  derecho, doble toque = doble clic. ⚠️ **No reescribas los manejadores `mouse*` para "soportar
  touch"**: agrega el gesto al traductor. ⚠️ El `preventDefault()` de `touchstart` y el
  `touch-action:none` de `#cv` van juntos: sin ellos el navegador manda ADEMÁS sus eventos de
  ratón de compatibilidad y todo llega doble.
- **`TOQ`** multiplica las zonas de acierto (manijas, nodos, trazos): 1 con ratón, 2.6 con el dedo.
  Una tolerancia nueva en píxeles va `*TOQ`, o con el dedo será imposible de atinar.
- **≤ 820 px el panel de propiedades es un cajón** (`.app.insp`, botón `#btnInsp`) y la barra
  superior se desplaza con el botón de envío pegado a la derecha (`position:sticky`).
- **`three.bundle.js` se carga al abrir la Vista 3D**, no con la página. Código que use `THREE`
  fuera de `openSim()` y lo que cuelga de ella fallará con `THREE is not defined`.
- ⚠️ **El riel NO lleva `overflow`** salvo en pantallas muy bajas: con scroll recorta el menú
  desplegable de figuras, que sale por su derecha.
- Probado con toques SIMULADOS en Chrome de computadora (11-nov-2026), **no en un aparato real**.

### Reglas visuales de la interfaz web (`studio_ui.html`, 12-nov-2026)

- **El magenta relleno es para UNA cosa por pantalla: el siguiente paso.** La opción elegida de un
  interruptor (`.seg button.on`) y las casillas son **neutras**; solo `.mach` (en qué máquina
  estás), las pestañas y los botones `.acc`/`.cta` llevan acento. Con todo en magenta nada destacaba.
- **Dos encuadres automáticos** (`fitMode`): `'design'` al abrir un archivo (encuadra lo dibujado)
  y `'sheet'` con `fitSheet()` (botón de ajustar, cambio de máquina o de área). ⚠️ No llames
  `fitView()` a secas para "volver a la hoja": respeta el modo vigente, y el `ResizeObserver` lo
  llama en cada cambio de tamaño.
- **Los avisos (`.toast`) salen ARRIBA del lienzo**: abajo tapaban los botones de zoom.
- **Un interruptor lleva icono Y nombre** (decisión de Jose, 12-nov): el nombre solo en el texto
  emergente no existe con el dedo, y "Nº | mm" no lo entendía nadie.

### Diseño → Corte: la forma de la pantalla (maqueta aprobada por Jose, 12-nov-2026)

- **Las dos máquinas tienen los mismos dos pasos**, `Diseño | Corte` (`#modeSeg`). ⚠️ La variable
  se sigue llamando **`sideMode` y vale `'design'` o `'cnc'`**: `'cnc'` significa "paso Corte" en
  CUALQUIER máquina (nombre histórico). `cncStep()` sigue siendo "CNC **y** paso Corte".
- **La acción que termina el trabajo va SIEMPRE arriba a la derecha**: `#sendGrp` ("Enviar") en
  plotter, `#btnTapTop` ("Guardar G-code") en CNC. El `#btnSaveTap` del panel sigue en el HTML,
  **oculto**: no lo borres sin mover su lógica.
- **Ya no existe la ventana "Plotter"** (`#plotterModal`): cuchilla, conexión, mover el cabezal y
  "Dónde se corta" viven en `#panePlot`, el paso Corte del plotter. `openPlotter()` ahora **lleva
  a ese paso** (y abre el cajón en pantallas chicas); no abre nada encima del diseño.
- **Corte de la CNC = propuesta "D" (aprobada por Jose, 12-nov-2026): dos pasos, `1 · Cortes` y
  `2 · Revisar`** (`#stepBar`). Tres vistas, nunca dos a la vez (`pintarVista()`): la LISTA
  (`#cutList`), el FORMULARIO de un corte (`#cutForm`, `formOpen`) y REVISAR (`#cutRev`, `revOpen`).
  El **material ya no es una pestaña**: es el encabezado `#cutSum` con "Cambiar", que lleva a
  `#paneCncCfg` (grosores a un toque, cero de Z con dibujo). `#tabsBar` se oculta en Corte.
  `#opSeg` sigue en el HTML, oculto, porque `curOp()` lo lee. Los campos conservan sus `id`.
  **El formulario es FIJO, sin "Más opciones"** (pedido de Jose, 12-nov): todo a la vista, en el
  orden en que se decide un corte — lado → profundidad (Prof./Pasadas, P. inicial/Holgura) →
  fresa y sentido → entrada en rampa → puentes → última pasada → nombre. Cancelar/Calcular van
  pegados al fondo del panel (`.formbtns`, `position:sticky`) porque el formulario es largo.
- **Un corte se crea desde `#addRow`** (Perfil, Cajeado, Taladro), sobre las figuras seleccionadas
  en el lienzo (ninguna = todas). Cada corte tiene **color** (`colorTp()`, `TP_COLORES`), el mismo
  en su fila y en el lienzo, y su **número de orden** pintado donde arranca (`pintarInsignias()`).
  ⚠️ `draw` está **envuelta** (`_dibujar`): lo que deba seguir a cada redibujo va en esa envoltura.
- **Quitado a pedido de Jose (12-nov-2026), no lo vuelvas a poner sin preguntarle:** la barra de
  acciones que aparecía junto a la figura seleccionada, el botón "Atravesar el material", el
  dibujo del material de canto con las pasadas, las **plantillas** de trayectoria y el plegable
  "Más opciones". Los probó y no le gustaron.
- **Las figuras de un corte se pueden cambiar**: con el formulario abierto, el clic en el lienzo
  selecciona FIGURAS (no suelta el corte ni salta a otro) y "Usar las seleccionadas" las deja en
  `formUids`, que se aplican al Calcular. Al abrir un corte, sus figuras quedan seleccionadas.
- **"Ver recorrido" y "Ver en 3D" viven SOLO en Revisar** (`#revPrev`, `#revSim`; pedido de Jose,
  12-nov). Los de antes (`#btnTpPrev`, `#btnSim3d`) siguen en el HTML, **ocultos**, porque tienen
  la lógica y los de Revisar los pulsan. Al abrir un corte para editarlo, su recorrido se enciende
  solo (hace falta para poner puentes a mano). **El botón dice lo que hace**: en Cortes "Revisar",
  en Revisar "Guardar G-code" — no "Revisar y guardar" para un paso que solo revisa.
- **Revisar es el único camino para guardar** (`abrirRev()` → `guardarRev()`). Vuelve a pedir los
  avisos al entrar y **`revDatos` se anula al empezar cada revisión**: nunca se guarda con el
  resumen de una anterior. Hace dos cosas que antes no existían: **un archivo por fresa**
  (`gruposPorFresa()`; el RichAuto no cambia de herramienta solo) y el **aviso de orden**
  (`ordenMalo()`: un perfil que atraviesa la pieza antes que un cajeado, un taladro o un perfil
  por dentro de esa misma pieza) con "Ordenar" (`ordenarCortes()`). `saveTap()`/`tapResumen()`
  siguen en el archivo pero ya nada visible los llama.
- **La fresa se elige dentro del formulario** (`#tpTool`), que es un **espejo** de `#toolPick`
  (Configuración): al cambiarlo PULSA aquel. No dupliques la lógica de `tool_sel`/`resetPasses`.
- **Tiempo por trayectoria** (`t._secs`) y total (`#tpTotal`): salen de la ÚLTIMA vista previa; si
  no se ha pedido "Ver recorrido" tras cambiar el diseño, son de antes (por eso llevan "≈").
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
- **Menú "Archivo"** (`#btnFile`): Abrir, Importar, Guardar y Exportar. Los cuatro botones de antes
  siguen en el HTML con `hidden` y el menú los **pulsa** (`.click()`), así su lógica y su estado
  activo/inactivo no se duplican. Atajos: Cmd/Ctrl+S guarda, Cmd/Ctrl+O abre.
- **Transformar: un renglón por acción** (`.xrow`, opción elegida por Jose, 12-nov): **Girar**
  (`#orgRotL` izquierda, `#orgRot` derecha, campo `#fr`), **Escalar** (campo `#fs`, `#scHalf` ½,
  `#scDouble` ×2) y **Voltear** (`#orgFlipH`, `#orgFlipV`). ⚠️ Con Y hacia arriba, **girar a la
  derecha (manecillas) es `rotate90(-1)`**. `#rotPreset` (el desplegable de grados) sigue en el
  HTML, oculto. ⚠️ No uses la clase `.trow` para renglones nuevos: ya es de la biblioteca de
  fresas y trae su propio relleno (me separó los renglones al estrenarlos).
- **Organizar está repartido por significado** (opción elegida por Jose, 12-nov): girar y
  voltear van en **Transformar** (renglón de arriba); en
  **Organizar** queda un renglón de cinco fichas con nombre (`.otile`: Agrupar, Separar, Al
  frente, Atrás, Copias); y el **candado vive en cada capa** (`lockBtn()` en `layerRow` y
  `groupHeader`) — es el único sitio visible para desbloquear UNA figura. Todo llama a las
  mismas funciones que el clic derecho. El **botón "Imagen"** del riel junta calcar y referencia.
- **Los avisos al pasar el ratón los dibuja la app** (`#tipBox`, bloque "avisos"): al entrar el
  ratón el `title` se muda a `data-tip` y al salir se devuelve, así que **sigue poniendo y
  leyendo `.title` como siempre** — no hay que usar otra propiedad. No actúa con el dedo (`TOQ>1`).
- **Teléfono (≤ 520 px)**: arriba, Plotter/CNC en icono; abajo, UN renglón sobre el lienzo —
  **deshacer/rehacer se mudan** de la barra a `#undoFloat` (bloque "barraMovil": los MISMOS
  botones, cambiados de padre) y a la derecha quedan relleno, ajustar y el %. **− y + se ocultan**
  (el zoom es con dos dedos) y el engrane del área de trabajo (`.wapill.wa`) también: está en el
  menú Archivo. ⚠️ Si agregas un botón a `.top` o a `.pillbar`, mide a 360 px.
- ⚠️ **Lo de teléfono se prueba con puntero TÁCTIL, no con una ventana angosta.** Bajo
  `@media (pointer:coarse)` los botones crecen para el dedo: una ventana de 390 px con ratón NO lo
  reproduce, y así se me pasó que los botones de abajo ocupaban 292 de 338 px (12-nov-2026). En
  Playwright: contexto con `hasTouch:true, isMobile:true`.
- **El botón del panel (`#btnInsp`) existe en TODOS los tamaños** (pedido de Jose): en ≤ 820 px
  abre/cierra el cajón (`.app.insp`); en pantallas anchas pliega la columna (`.app.noinsp`, se
  recuerda en `localStorage`). El código que necesita el panel a la vista llama **`mostrarPanel()`**,
  no `classList.add('insp')`: si la columna estaba plegada, eso solo no la despliega.

## Aspecto visual — sistema de diseño (tokens)

Desde jul-2026 la UI tiene **un sistema de diseño centralizado** al inicio del archivo. **No
hardcodear colores ni fuentes en los widgets** — todo sale de aquí:

- **Colores:** la clase `UI` (un neutro, el acento magenta `UI.ACCENT`, colores de estado, y los del
  lienzo). Cambiar el look = cambiar esos valores, no cazar hex por el archivo.
- **Fuentes:** constantes `F_SECTION`, `F_LABEL`, `F_BODY`, `F_ICON`, `F_MONO`, etc., construidas con
  la **familia nativa por plataforma** (`_UI_FAMILY`/`_MONO_FAMILY`). ⚠️ **Nunca volver a poner
  `'Segoe UI'` o `'Consolas'` literales**: no existen en Mac y caen en una fuente tosca.
- **Tema:** `_setup_theme()` configura TODOS los widgets ttk (pestañas, botones, listas, spinboxes,
  barra de progreso, iconos) con la paleta, sobre el tema `clam`. Estilos propios: `Accent.TButton`
  (acciones primarias), `Icon.TButton` / `Icon.Toolbutton` (barra de iconos).
- ⚠️ **En macOS, `tk.Button` y `tk.Checkbutton` IGNORAN el color de fondo** (se dibujan como botón
  nativo). Para botones con color de marca o de estado, usar **ttk con un estilo del tema**, no tk
  clásico. (Por eso "Enviar Diseño" y la barra de iconos son ttk.)
- ⚠️ **Los `tk.Toplevel` necesitan `bg=UI.PANEL`** o en modo oscuro de macOS salen con fondo negro.
- **No quitar** el bloque de tema/paleta al inicio de `PlotterApp.__init__` ni `_setup_theme()`.

### Fuentes (Design Studio)

- **La app NO tiene carpeta propia de tipografías**: lee las instaladas en el sistema
  (`_font_dirs()` en `text_vector.py`). Agregar una fuente = instalarla en el SO. El caché
  (`fonts_cache.json`) se invalida solo con una firma de esas carpetas (`_dirs_sig`), pero **esa
  firma solo mira el PRIMER NIVEL**: fuentes metidas dentro de una subcarpeta que ya existía
  pueden no detectarse — instalarlas sueltas, o borrar el caché.
- ⚠️ **En la web el navegador NO tiene las fuentes: el catálogo vive en el servidor.** Pintar
  cada nombre "con su tipografía" solo por CSS (`font-family` = nombre de la familia) cae en la
  letra de reserva en todo aparato que no las tenga instaladas — en la Mac de Jose no se notaba
  porque ahí SÍ están (12-nov-2026). El servidor manda una **muestra** por fila
  (`/api/font_muestra?i=`: la fuente recortada a las letras de su nombre, ~2 KB, `font_sample()`)
  cuando la fila entra a la vista (`IntersectionObserver`), y la fuente **entera** solo de la
  elegida (`/api/font_archivo?i=`), para el recuadro donde se escribe. Las dos van **por índice
  de la lista**, nunca por ruta. Para probarlo hay que usar fuentes que el navegador de prueba
  NO tenga (`DS_FUENTES` con familias renombradas); con las del sistema el fallo no aparece.
- ⚠️ **El selector de fuentes dibuja POR TANDAS y agrupado por familia** (`fillFontList`/
  `fpDrawRows` en `studio_ui.html`). **No volver a pintar una fila por archivo de fuente**: cada
  fila se dibuja con su propia tipografía, así que la lista completa obliga al motor web a cargar
  cientos de fuentes cada vez que se abre el menú. Con el catálogo grande instalado (ago-2026:
  969 fuentes / 343 familias) eso se sentiría al abrir el desplegable.

## Dependencias opcionales

La app **arranca sin ninguna dependencia** y solo deshabilita la función que falte:

| Flag | Librería | Habilita |
|---|---|---|
| `HAS_SERIAL` | pyserial | Conexión al plotter y envío HPGL |
| `HAS_DXF` | ezdxf | Abrir `.dxf` |
| `HAS_MUPDF` | pymupdf (fitz) | Abrir `.ai` |
| `HAS_SVG` | svgpathtools | Solo `_parse_with_lib()`, que **no se usa** (el SVG primario va con stdlib) |

---

## Distribución: dos PWA y actualización automática (operativo, no obvio)

- **Desplegar = `git push` a `master`**: Railway reconstruye el `Dockerfile` y reinicia (~1 min).
- **Dos apps instalables en el mismo sitio**, cada una con su manifiesto, su `id` y su logo
  (`MANIFIESTOS` en `studio_server.py`): **Design Studio** (`/`, cuadro magenta con la cabeza de
  corte) y **Estación de corte** (`/estacion`, cuadro oscuro con el botón de cortar). Los logos
  salen de `python3 web/crear_iconos_pwa.py` → `iconos/` (**sí va a git**: el servidor los sirve).
- ⚠️ **El manifiesto, `/favicon.ico` y `/iconos/*` son PÚBLICOS** (`PUBLICAS` y el prefijo en
  `_guardia`): el navegador los pide **sin cookie** y antes de entrar. Si un recurso nuevo de la
  PWA queda detrás de la sesión, recibe un 302 a `/entrar` y la app **deja de ser instalable sin
  ningún error visible**.
- ⚠️ **Cada página enlaza SU icono con `<link rel="icon">`** (editor, estación y las de
  `web_auth._marco`). Sin ese enlace Chrome muestra lo que tenga guardado para el dominio.
- ⚠️ **A propósito NO hay service worker que guarde copias.** La app necesita al servidor para
  todo, y una copia guardada es justo lo que deja a un teléfono con la versión vieja. La
  actualización va así: `/` se sirve con `no-cache`, el servidor publica `BUILD` (huella de sus
  `.py/.html/.js`, cambia en cada despliegue) en `/api/update_check` y en la fila de la estación;
  la estación **se recarga sola cuando no está cortando**, y el editor se recarga solo **si no hay
  diseño abierto** (si lo hay, deja un botón "Actualizar": recargar tiraría lo no guardado).
  **Si agregas un service worker, esta garantía se rompe**: mídelo antes.
- ⚠️ **Para probar si una página es instalable, el oyente de `beforeinstallprompt` va DENTRO de la
  página**: puesto después desde fuera llega tarde y parece que no es instalable (pasó con la
  estación, 11-nov-2026).
- ⚠️ **`pymupdf<2` fijo** (`requirements-servidor.txt`): PyMuPDF 2.0 arrastra `pymupdf-layout`,
  que al importar busca un modelo `.yaml`. Antes de quitar el tope, construye la imagen y prueba.

---

## Código muerto (no construir sobre esto; candidato a borrar)

- **`_pinch_corners()`** y la llave **`_pinched`**: vestigios de cuando se usaba `smooth=True`. Hoy
  nadie llama a la función y nadie lee la llave (solo se escribe a `None`). Si tocas esa zona, no
  asumas que hacen algo.

---

## Ejecución (desarrollo)

```bash
/opt/homebrew/bin/python3 studio_server.py     # el sitio, en http://127.0.0.1:8765
pip install -r requirements-servidor.txt
```

Pruebas: `python3 web/auditar_servidor.py` (sobre una copia), `python3 auditar_gcode.py`,
`node web/test_plotter_web.mjs`, `node web/test_estacion.mjs`, `node web/test_webusb.mjs`.

- **En macOS: usar un Python con Tk 8.6+ (no el del sistema).** El Tk 8.5.9 de `/usr/bin/python3`
  se rompe con el Modo Oscuro y pinta todos los fondos en negro. Detalles y la config de la Mac de
  Jose en [[MEMORY]] (`estado.md`).
- **No quitar el bloque `if sys.platform == 'darwin':`** del inicio de `PlotterApp.__init__` (fuerza
  tema `clam` + paleta clara). Solo aplica en Mac a propósito: en Windows/Linux el tema nativo se ve
  bien y no debe alterarse.
