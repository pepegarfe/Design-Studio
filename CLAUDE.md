# CLAUDE.md — Plotter Antike

Leer **antes** de tocar el código: solo **invariantes y trampas** que no se deducen leyéndolo. La
arquitectura se descubre en `plotter_control.py` — no se documenta aquí para que no se pudra.

**Historia, decisiones y estado del trabajo → [[MEMORY]]** (`.claude/memoria/`, empezar por `estado.md`).

> Verificado contra el código el 21-jul-2026. Si ves algo que el código contradice, **corrígelo aquí**.

---

## Qué es

App de escritorio **Python/tkinter** (un solo archivo, `plotter_control.py`, ~3600 líneas) que
controla un **plotter de corte** por puerto serial/USB. Abre un vector (SVG, DXF, AI), deja
acomodarlo y lo envía al plotter en **HPGL**. Corre en Windows, Mac y Linux.

**Se distribuye compilada** (PyInstaller). No es una librería ni tiene módulos propios: todo vive en
ese archivo. **No separar en varios archivos sin pedido explícito.**

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
  hace que funcione igual como script y como exe de PyInstaller (config en AppData en Windows).
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

### Design Studio (`design_studio.py`, pywebview) — lo que costó tres días

- ⚠️ **NUNCA cuelgues del objeto `js_api` un atributo PÚBLICO que sea un objeto**: pywebview
  **recorre** ese objeto para exponer sus métodos y **se mete dentro**. Con la ventana colgada ahí
  toca `window.width`, cuyo getter pide el tamaño **a la ventana nativa que aún nace en otro hilo**
  → **abrazo mortal: "No responde" para siempre** (~2 de 3 arranques, solo Windows; es una carrera
  y en Mac se gana). Por eso **`api._window`** — pywebview salta los nombres con `_`. **Ese guion
  bajo no es estilo, es el arreglo.**
- **No quitar `arranque.log` ni el vigilante `faulthandler`** de `main()`. La app se distribuye
  **sin consola**: sin ese registro, un cuelgue al arrancar **no deja ningún rastro** y solo queda
  adivinar. En un arranque sano escribe seis líneas y se desarma solo.
- **Regla:** fallo **intermitente** = dos cosas compitiendo; fallo en **una sola máquina** = mide ahí, no deduzcas.
- ⚠️ **Plotter en el navegador: en ANDROID no usar `navigator.serial`.** Existe, pero solo ve
  puertos **Bluetooth**: el plotter nunca aparecería, sin error. Allá el cable va por **WebUSB**
  con un driver FTDI propio (`serieUsb`/`abrirFtdi` en `<script id="motor-plotter">`) disfrazado
  de puerto Web Serial, y lo elige `serieDelNavegador()`. En computadora es al revés: WebUSB no
  sirve (el driver del sistema tiene tomado el chip). Solo FTDI; CH340/Prolific/CP210x no están.
  Probado en el Galaxy de Jose (Android 16). Prueba: `node web/test_plotter_web.mjs`.

---

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

## Distribución y auto-actualización (operativo, no obvio)

**Desde el 25-jul-2026 solo se distribuye Design Studio** (decisión de Jose). La app tkinter sigue
en el repo como motor y como respaldo, pero **ya no se compila ni se publica**.

- **CI** (`.github/workflows/release.yml`): al publicar un tag compila Design Studio para **Windows
  y Mac (Apple Silicon)** y sube `DesignStudio-Windows.zip` / `DesignStudio-Mac.zip` al release.
- **⚠️ La etiqueta del release debe ser SOLO números** (`v2026.07.25`, `v2026.07.25.2`). La CI lo
  valida y aborta si no. Motivo: las versiones se comparan **número a número** (`vkey()` en
  `updater.py`) — una letra al final se ignora y dos releases empatarían. **Nunca comparar
  versiones como texto**: `'2026.7.10' > '2026.7.9'` es FALSO en texto (era un bug real, corregido
  en ambas apps).
- **Auto-update** (`updater.py`, compartido escritorio/servidor): consulta
  `releases/latest`, elige el .zip por sistema (y por procesador si hubiera varios), descarga con
  avance y **lanza un ayudante externo** (bash en Mac, PowerShell en Windows) que espera a que la
  app muera, la reemplaza y la relanza. Un programa **no puede sobrescribirse a sí mismo**.
  - **Solo actúa con `sys.frozen`**; como script se niega y manda a `git pull`.
  - `version.txt = "dev"` = modo desarrollo: nunca ofrece actualizar.
  - ⚠️ El ayudante espera por el **estado** del proceso (`ps -o stat=`), no con `kill -0`: un
    proceso **zombi** sigue "existiendo" y la espera no terminaría nunca (pasó en pruebas).
- **⚠️ En Mac, comprimir/descomprimir un `.app` SIEMPRE con `ditto`** (`-c -k --keepParent` /
  `-x -k`), nunca con el `zipfile` de Python ni `zip` a secas: se pierden los **enlaces simbólicos**
  y el **permiso de ejecución**, y la app llega rota al otro lado.
- **Recetas de compilación** (`DesignStudio.spec` — **sí va a git**, ya no es el auto-generado):
  `crear_icono_studio.py` (iconos) y `preparar_potrace.py` (mete potrace y su dylib en `vendor/`,
  reapuntados a `@loader_path` y re-firmados). Sin ese `vendor/`, **el calco B/N no existe** en la
  máquina del usuario final: potrace es un programa aparte que aquí solo está por Homebrew.
- **`DesignStudio --diagnostico`** imprime qué piezas trae la app y cuáles faltan. La CI lo corre
  tras compilar: una app puede arrancar perfecta y tener el texto o el acomodo muertos porque una
  librería no quedó empaquetada.
- ⚠️ **`pymupdf<2` fijo en la CI.** PyMuPDF 2.0 (oct-2026) arrastra `pymupdf-layout`, que se
  activa al importar y busca un modelo `.yaml` que PyInstaller no empaqueta: **la app no arranca**
  (`v2026.10.28` salió así). Antes de quitar el tope, compila y corre `--diagnostico` en local.
  En Windows el diagnóstico va con `Start-Process -Wait`: llamado a secas, el código de error del
  `.exe` de ventana se perdía y la app rota pasó como "éxito".
- **Mac sin firmar** (Jose no tiene cuenta de Apple): la primera vez hay que abrirla con
  **clic derecho → Abrir**, o `xattr -cr` si dice "está dañada". Va explicado en las notas del release.
- ⚠️ **Windows: `instalar_studio.ps1` DEBE hacer `Unblock-File` recursivo** tras copiar. Windows
  marca (`Zone.Identifier`) todo lo que sale de un `.zip` del navegador y **.NET se NIEGA a cargar
  un ensamblado marcado**: sin pythonnet, pywebview no dibuja ventana y **la app no arranca**.
  Síntoma: *"Failed to resolve Python.Runtime.Loader.Initialize"* **con la ruta del DLL** — está
  ahí, solo bloqueado. La auto-actualización no se ve afectada (`urllib`+`zipfile` no marcan). El
  `.bat` lanza el `.ps1` con `-ExecutionPolicy Bypass`, que ignora la marca. **El `.ps1` se
  mantiene 100% ASCII**: PowerShell 5.1 lee UTF-8 sin BOM como ANSI y destroza los acentos.

---

## Código muerto (no construir sobre esto; candidato a borrar)

- **`_pinch_corners()`** y la llave **`_pinched`**: vestigios de cuando se usaba `smooth=True`. Hoy
  nadie llama a la función y nadie lee la llave (solo se escribe a `None`). Si tocas esa zona, no
  asumas que hacen algo.

---

## Ejecución (desarrollo)

```bash
python plotter_control.py          # Python 3.8+ con tkinter
pip install pyserial ezdxf pymupdf # o instalar_dependencias.bat
```

- **En macOS: usar un Python con Tk 8.6+ (no el del sistema).** El Tk 8.5.9 de `/usr/bin/python3`
  se rompe con el Modo Oscuro y pinta todos los fondos en negro. Detalles y la config de la Mac de
  Jose en [[MEMORY]] (`estado.md`).
- **No quitar el bloque `if sys.platform == 'darwin':`** del inicio de `PlotterApp.__init__` (fuerza
  tema `clam` + paleta clara). Solo aplica en Mac a propósito: en Windows/Linux el tema nativo se ve
  bien y no debe alterarse (el `.exe` distribuido debe verse nativo).
