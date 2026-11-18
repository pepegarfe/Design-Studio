# CLAUDE.md — Design Studio (antes Plotter Antike)

Leer **antes** de tocar el código: solo **invariantes y trampas** que no se deducen leyéndolo. La
arquitectura se descubre en el código — no se documenta aquí para que no se pudra.

**Historia, decisiones y estado del trabajo → [[MEMORY]]** (`.claude/memoria/`, empezar por `estado.md`).

> Verificado contra el código el 18-nov-2026. Si ves algo que el código contradice, **corrígelo aquí**.

**Las reglas de cada zona viven en `.claude/rules/` y se cargan solas al tocar sus archivos:**
`cnc.md` (generador de G-code y su interfaz) · `interfaz-web.md` (`studio_ui.html`) ·
`pwa-y-despliegue.md` (servidor, PWA, Docker) · `servidor-web.md` (varias cuentas a la vez) ·
`motor-y-escritorio-legado.md` (`plotter_control.py`: parsers y la app tkinter vieja).

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
  **matriz afín** (`_root_mtx` mete el factor `PX_TO_MM`). ⚠️ **Nunca agregar `* PX_TO_MM`** en
  `_parse_d`, `_parse_rect`, `_parse_circle`, `_parse_line`, `_parse_poly`: duplicarías la conversión.
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
  la lee; igual que la función `_pinch_corners()`, que nadie llama.)

---

## Invariantes que cruzan todo el código

- **Rutas de recursos y config: usar `_resource()` y `_config_path()`**, nunca hardcodear. Es lo que
  hace que cada cuenta de la web lea SU carpeta (ver `.claude/rules/servidor-web.md`).
- ⚠️ **TODO JSON con `encoding='utf-8'` EXPLÍCITO**: sin él Python usa el codepage del SO (**cp1252
  en Windows**) y un `″` —lo llevan los nombres de fresa de fábrica— hace que `write_text` **trunque
  el archivo a 0 BYTES** y la config se pierda EN SILENCIO. **En Mac nunca falla**, así que no
  aparece probando aquí.
- ⚠️ **Lo que el generador de corte corrige u omite, lo AVISA** (`_cnc_warnings()`). Si agregas otra
  corrección silenciosa, agrégale su aviso (detalle en `cnc.md`).
- **Regla de diagnóstico:** fallo **intermitente** = dos cosas compitiendo; fallo en **una sola
  máquina** = mide ahí, no deduzcas.
- ⚠️ **En la Mac todo tarda décimas; Railway es varias veces más lento.** Lo que aquí es 1 s allá se
  siente roto: mide el rendimiento pensando en Railway.

---

## Desplegar (operativo, no obvio)

- ⚠️ **Desplegar = `git push` a `master`**: Railway reconstruye el `Dockerfile` y reinicia (~1 min).
  **Cada push reinicia el sitio ~30 s, aunque solo cambien notas** (`.claude/`, `CLAUDE.md`; medido 11-nov-2026): no hay "Watch Paths"
  y **Jose decidió dejarlo así** (18-nov-2026): no volver a ofrecerlo. El sync de Obsidian también
  empuja a `master`.
- Detalle de PWA, íconos, rutas públicas y actualización automática → `.claude/rules/pwa-y-despliegue.md`.

---

## Ejecución y pruebas (desarrollo)

```bash
pip install -r requirements-servidor.txt
/opt/homebrew/bin/python3 studio_server.py     # el sitio, en http://127.0.0.1:8765
```

Pruebas: `python3 web/auditar_servidor.py` (sobre una copia), `python3 auditar_gcode.py`,
`node web/test_plotter_web.mjs`, `node web/test_estacion.mjs`, `node web/test_webusb.mjs`.
Cómo verificar la interfaz con navegador: [[como-verificar-la-interfaz]].
