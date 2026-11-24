---
paths:
  - plotter_control.py
  - text_vector.py
---
# Motor (`plotter_control.py`) y la app tkinter vieja que lleva dentro

Verificado contra el código el 18-nov-2026 (movido del `CLAUDE.md`).

⚠️ **Casi todo lo de abajo es de `PlotterApp`/`DesignCanvas` (tkinter), que ya nadie abre**
(no hay app de escritorio desde el 11-nov-2026). Solo aplica si te piden tocar esa app. Lo que SÍ
usa la web de este archivo es el MOTOR: parsers, aplanado de curvas, HPGL y config.

## Motor (lo usa la web)

- **No usar `svgpathtools` como parser primario.** `SVGParser.parse()` siempre llama
  `_parse_basic()`, que usa `xml.etree` de la stdlib. `_parse_with_lib()` existe pero **no se
  invoca** (por eso el flag `HAS_SVG` casi no importa).
- **`SVGParser` NO descarta los `<text>`** (24-nov-2026): los anota en `parser.texts` (texto,
  posición, tamaño y matriz; un renglón por `<tspan>` con posición propia) y
  `studio_backend.load_vector` los convierte en trazos marcados `nota`. Cada trazo lleva `capa`:
  el `<g>` con nombre más cercano (`inkscape:label` o id; Illustrator codifica `_` como `_x5F_`;
  los ids automáticos como `g12` o `Layer_1` no cuentan).
- **`DXFParser` y `AIParser` tampoco descartan textos** (24-nov-2026): `parser.texts` con el formato
  común `{txt, org, cap, rot, anchor, dy}` — YA en mm y Y-arriba (`cap` = altura de mayúscula,
  `rot` en radianes, `dy` = cuánto baja la línea base). DXF: `TEXT`, `MTEXT` (un renglón por
  línea), y los de bloques (`INSERT` → `virtual_entities` + `attribs`); escalados con `$INSUNITS`.
  AI/PDF: `page.get_text('dict')`; ⚠️ se saltan los de `alpha 0` (la capa INVISIBLE de
  reconocimiento de texto de un PDF escaneado: si no, un escaneo se llenaría de notas).
  Los trazos de corte salieron idénticos a los de antes con y sin textos.
- **No romper el `Z/z` de `_parse_d`**: cierra el subpath actual y **continúa** parseando (no hace
  `break`).
- **Aplanado de curvas ADAPTATIVO por tolerancia** (desde 22-jul-2026): `_flat_cubic`/`_flat_quad`/
  `_arc_steps` (tolerancia relativa ~0.015% + piso 0.01 mm) y una pasada final `_simplify_mm`
  (Douglas-Peucker a 0.01 mm, en mm reales, a la salida de los TRES parsers). ⚠️ **No volver a
  muestrear curvas con N fijo de segmentos** — eso cuadriculaba los imports al escalarlos.

### Fuentes (Design Studio)

- **La app NO tiene carpeta propia de tipografías**: lee las instaladas en el sistema
  (`_font_dirs()` en `text_vector.py`). Agregar una fuente = instalarla en el SO. El caché
  (`fonts_cache.json`) se invalida solo con una firma de esas carpetas (`_dirs_sig`), pero **esa
  firma solo mira el PRIMER NIVEL**: fuentes metidas dentro de una subcarpeta que ya existía
  pueden no detectarse — instalarlas sueltas, o borrar el caché.

## App tkinter vieja (`PlotterApp`, `DesignCanvas`) — solo si te piden tocarla

- **Escalado de grupo (modos "Grupo" y "Todos"): el ancla es la esquina INFERIOR-IZQUIERDA** del bbox
  (`ax=min_x`, `ay=min_y`), **no el centro**. Usar el centro rompe las posiciones relativas entre
  trazados del grupo.
- **`_push_undo()` va en los métodos `_apply_*`, nunca en los `_nudge_*`** (los nudge delegan en
  apply, que ya empuja; hacerlo en ambos duplica el historial). **`open_file()` limpia ambos stacks**
  (`_undo_stack` y `_redo_stack`).
- **Refrescos de posición/escala/rotación: usar `_refresh_preview()`**, que NO resetea el zoom. **No
  llamar `set_paths()` ni `_auto_fit()`** para eso — perderías el zoom del usuario.
- **`set_paths()` y `_generate_hpgl()` siempre con `_effective_styled()`**, nunca con
  `current_styled` crudo. `_effective_styled()` aplica scale+rotación (sobre el centro del bbox
  original) y luego el offset, devolviendo dicts nuevos sin mutar el original.
- **Los `create_line` usan `smooth=False`** (con `joinstyle=MITER`, `capstyle=BUTT`). ⚠️ **No poner
  `smooth=True`**: fue eliminado a propósito para arreglar la fidelidad visual del corte (la suavidad
  viene del aplanado adaptativo del motor, arriba).
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

### Aspecto visual de la app tkinter (tokens)

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

### Dependencias opcionales (solo escritorio)

La app de escritorio **arranca sin ninguna dependencia** y solo deshabilita la función que falte
(en el servidor, en cambio, todas son obligatorias):

| Flag | Librería | Habilita |
|---|---|---|
| `HAS_SERIAL` | pyserial | Conexión al plotter y envío HPGL |
| `HAS_DXF` | ezdxf | Abrir `.dxf` |
| `HAS_MUPDF` | pymupdf (fitz) | Abrir `.ai` |
| `HAS_SVG` | svgpathtools | Solo `_parse_with_lib()`, que **no se usa** (el SVG primario va con stdlib) |

### Otros detalles de escritorio

- `version.txt` se lee con **`utf-8-sig`**: se come el BOM de PowerShell 5.1 (era del actualizador).
- **En macOS: usar un Python con Tk 8.6+ (no el del sistema).** El Tk 8.5.9 de `/usr/bin/python3`
  se rompe con el Modo Oscuro y pinta todos los fondos en negro. Detalles en [[estado]].
- **No quitar el bloque `if sys.platform == 'darwin':`** del inicio de `PlotterApp.__init__` (fuerza
  tema `clam` + paleta clara). Solo aplica en Mac a propósito: en Windows/Linux el tema nativo se ve
  bien y no debe alterarse.
