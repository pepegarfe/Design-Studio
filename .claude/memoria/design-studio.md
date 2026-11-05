---
name: design-studio
description: Design Studio — la interfaz nueva (web/pywebview) que reconstruye Plotter Antike; estado y cómo correrla/compilarla
metadata: 
  node_type: memory
  type: project
  originSessionId: 661c489b-f53b-4842-91af-46e807877393
  modified: 2026-11-05T19:04:33.300Z
---

# Design Studio — la interfaz nueva (rebuild)

Construida el 21-jul-2026. Es un **programa nuevo** que reconstruye la cara de Plotter Antike con
aspecto pro, **reutilizando el motor** (`plotter_control.py`: parsers SVG/DXF/AI, `HPGLConverter`,
`PlotterController`). El original tkinter **sigue intacto** (Plotter Antike no se tocó).

> **Es la cara NUEVA del mismo plotter.** La cara vieja (app tkinter) está en [[estado]]. Ambas
> comparten `plotter_control.py` y por eso viven en **un solo repo**: Design Studio lo importa;
> separarlos obligaría a duplicar el motor y arreglar cada bug dos veces.

## Por qué existe
El aspecto de la app tkinter tiene techo (no compite con Illustrator). Jose pidió reconstruir para un
look profesional. Se eligió **web + backend Python** (pywebview) porque la maqueta aprobada es HTML/CSS
y así se convierte directo en la app; el motor Python se reusa por debajo.

## Arquitectura y archivos (todos en `~/Design-Studio/`)
- **`design_studio.py`** — entrada de ESCRITORIO (ventana nativa pywebview). Clase `Api` = puente
  JS↔Python. Carga `studio_ui.html`.
- **`studio_server.py`** — modo SERVIDOR web (bottle, puerto 8765): sirve `studio_ui.html` y expone la
  misma API por HTTP. Es el modo con el que se DEPURA en Chrome. (La idea de usarlo multi-dispositivo
  está en pausa → [[idea-web-online]].)
- **`studio_ui.html`** — TODA la interfaz (HTML/CSS/JS). El motor de edición (transformaciones,
  selección, capas, historial) vive en **JavaScript**; solo parseo/HPGL/serial van a Python.
  ⚠️ Tiene un `window.__DS` de depuración (inofensivo).
- **`studio_backend.py`** — `PlotterService` (SERVICE) compartido: conexión serial, control manual,
  envío en hilo con progreso, cancelar; y `set_workarea`, `build_hpgl`.

## Estado (21-jul-2026)
- **Fase 1 (editar): ✅ verificada en vivo** — abrir, selección (individual/grupo/todos, por capas y
  clic), mover, escalar (W/H y %), rotar, espejo, centrar, restablecer, capas con miniaturas,
  deshacer/rehacer, copiar/pegar/borrar. Motor de transform en JS (offset+escala+rotación por trazado).
- **Fase 2 (salida): ✅ verificada** — generar HPGL (idéntico al motor original), guardar, overlay de
  corte, parámetros, estimación de tiempo.
- **Fase 3 (plotter): ⚑ construida, cableado verificado, SERIAL SIN PROBAR** — panel de conexión,
  control manual, enviar con progreso, cancelar, test. Falta enchufar el plotter para verificar de verdad.
- **Fase 4: ✅ config verificada + app de Mac compilada** — editar/guardar área de trabajo (persiste en
  `plotter_config.json`, compatible con el original). **`dist/DesignStudio.app` compila y arranca** (97 MB).
  Falta: empaquetar Windows y probar visualmente la ventana compilada.

## 22-jul-2026: Design Studio ahora también es el CAM de la CNC
Toda la épica CNC (fases A–H: pestañas Diseño|CNC, trayectorias estilo Aspire, fresas por
material, G-code .tap) vive en [[cnc-richauto]] — leer ESA nota antes de tocar nada del CNC.
Cambios de UI GENERAL que vinieron con ella (aplican a toda la app): **tema claro por default
y persistente** (clave `theme` en cnc_config.json), toggle de tema al final del riel izquierdo,
botón de área de trabajo junto al zoom (píldora propia, contenedor flex), iconos 100% SVG
(cero emojis/glifos), atajos Cmd+G/Cmd+Shift+G por `e.code`.

## 22-jul-2026: fidelidad de CURVAS arreglada en el MOTOR (plotter_control.py — ambas apps)
Jose reportó curvas "cuadriculadas" en imports. Causa: los 4 muestreadores (Béziers SVG C/S/Q/T,
arco A, círculo/elipse a 72 lados FIJOS, Béziers del AI) troceaban con densidad FIJA por unidad
interna del archivo — un viewBox chico escalado quedaba facetado. **Solución (la de los
programas pro): aplanado ADAPTATIVO por tolerancia** — `_flat_cubic`/`_flat_quad` (De Casteljau
recursivo) y `_arc_steps` (sagita), con tolerancia **RELATIVA** (~0.015% del tamaño de la curva
→ a prueba de escalados posteriores) + **piso absoluto 0.01 mm** (vía escala de la matriz raíz)
+ **pasada final `_simplify_mm`** (Douglas-Peucker a 0.01 mm, en mm, a la salida de SVG/AI/DXF).
Números verificados: círculo Ø90 → desviación 0.0099 mm (antes 0.048); Bézier de logo viewBox-24
a 200 mm → 0.0075 mm; escalar ×5 conserva 0.02% del radio; rectas intactas.
**Gotchas que costaron**: (1) tolerancia relativa POR TRAMO explota en trazos de cientos de
mini-curvas (potrace: 25k puntos en un círculo) → por eso el piso + la simplificación en mm;
(2) potrace mete un `<g transform="scale(0.1)">` que el piso calculado solo con la matriz raíz
no ve → por eso la limpieza final se hace en MM REALES post-matriz, que atrapa todo.
⚠️ No volver a muestrear curvas con N fijo (ver CLAUDE.md).
**Ronda 2 (commit 0f53cd2)**: el DXF seguía cuadriculado — su tolerancia era fija en UNIDADES
DEL DIBUJO y la escala $INSUNITS→mm se aplica DESPUÉS: un DXF declarado en metros (×1000) o
pulgadas (×25.4) quedaba con desviación real de hasta 1mm. Fix: `parse()` calcula la escala
primero y fija `self._tol = 0.01mm/escala`. Verificado idéntico (0.0099mm) en m/in/mm.
**Si un DXF sigue facetado tras esto**: el ARCHIVO trae las curvas ya trozadas en polilíneas
por el programa que lo exportó (Illustrator suele hacerlo) — eso ya no lo arregla ninguna
tolerancia; la solución sería re-ajuste de arcos/Béziers sobre polilíneas (el "curve fitting"
de Vectric), no construido.
**Ronda 3 — calibración contra caso REAL (commits be75891 + e06f2f7, cierre del 22-jul)**:
Jose seguía viendo "exactamente lo mismo" tras relanzar. Diagnóstico con SU archivo
(`vaquero salchichon.dxf`, Drive Cantarito/CORTE METAL: 17 SPLINEs reales, $INSUNITS=5=cm):
(a) para archivos en CM el fix de escala no cambiaba nada (0.001 unidades-cm ya eran 0.01mm) —
por eso viejo≈nuevo; (b) el flujo real de Jose es importar 81×205mm → **escalar ×10 en la
app** → inspeccionar a **5924% de zoom**, y la tolerancia relativa de 0.015% daba ~0.3mm
post-escala = 17px de quiebre a ese zoom. **Calibración final medida contra la spline exacta:
relativa 0.001% (1e-5) + pisos 0.001mm reales + _simplify_mm 0.001** → 0.0019mm al importar,
0.019mm tras ×10 = **1.1px a 5924%** (invisible), 3186 pts en todo el archivo.
**Lecciones**: (1) calibrar tolerancias contra el CASO DE USO real (escala máxima × zoom de
inspección), no contra "se ve bien al 100%"; (2) "sigue exactamente igual" tras un fix = o el
proceso corre código viejo, o el fix no toca ese camino — DIAGNOSTICAR CON EL ARCHIVO DEL
USUARIO (mdfind lo encontró en su Drive) antes de otra vuelta de tuerca a ciegas; (3) re-abrir
la app no basta: un diseño YA CARGADO (o un .dstudio) conserva los puntos horneados — hay que
RE-IMPORTAR el archivo fuente.

## Novedades sesión 21–22 jul 2026 (LEER al retomar)
Todo verificado en vivo (Chrome, modo web) y relanzado en escritorio. **Commit `f02e918` (pusheado)**:
- **Calco de imagen** (B/N + color) — ver sección "Calco de imagen" abajo.
- **"Abrir" acepta imágenes** (PNG/JPG/…): las manda directo al calco (además de SVG/DXF/AI y .dstudio).
  Arreglado el filtro de pywebview: **su validador NO admite comas** en la descripción del `file_type`.
- **Arreglo del eje Y** — ver sección "Eje Y" abajo. ⚠️ Falta verificar el corte en hardware.
- **Capas estilo Illustrator**: grupos como nodos plegables con hijos anidados (`buildLayers`/`layerRow`/
  `groupHeader` en studio_ui.html; estado de plegado en `layerCollapsed`).
- **Selección múltiple**: Shift / Cmd / Ctrl + clic suma/quita; Shift+arrastre = marco aditivo
  (`mousedown`/`mouseup` del lienzo; respeta grupos como unidad).

**Commit `73229b8`** (ya pusheado):
- **Alinear-a**: el `<select>` de texto "Selección/Área de trabajo" ahora es un **segmentado con iconos**
  (id `alignTo`, dos `<button data-to>`; estilo `.seg`). De regalo mejoró el resaltado del modo B/N/Color.

## Épica en curso: reemplazar Illustrator (iniciada 24-jul-2026, pedida por Jose)
Jose quiere diseñar TODO dentro de Design Studio (hoy solo edita lo importado). Orden acordado:
1) formas básicas → 2) texto con fuentes → 3) soldar/booleanas + contorno-offset → 4) edición de
nodos (al final a propósito: los trazos viven aplanados en puntos; editar anclas estilo
Illustrator pedirá otra representación). V-carve sigue fuera.
- **1. Formas básicas — ✅ COMMIT 86765a0 (24-jul, Jose las probó y pidió el botón único).** 4 herramientas
  nuevas en el riel: Rectángulo (R), Elipse (E), Polígono/Estrella (P, con popover Lados/Estrella/
  Interior% arriba-izquierda del lienzo), Línea (L). Arrastre estilo Illustrator con
  previsualización punteada en acento; Shift = cuadrado/círculo/ángulos 45°/rotación a 15°;
  polígono se dibuja DESDE EL CENTRO y el ángulo del arrastre lo rota; Escape vuelve a Selección.
  Elipse con segmentos por sagita (~0.002 mm, 48–720) — sin N fijo burdo (lección del 22-jul).
  Se puede dibujar sobre la mesa VACÍA (el overlay tiene pointer-events:none; al crear la 1ª
  forma se asigna nombre 'nuevo-diseno' ASCII). Umbral anti-fantasma: arrastres <4 px de PANTALLA
  no crean nada (en mm engañaba: alejado, medio píxel ya era >1 mm). Bloqueado en paso CNC
  (cncLock). **Jose las probó y pidió el patrón Illustrator: UN solo botón de figuras**
  (`toolShape`, con triangulito de "hay más") que al clic activa la última usada Y despliega el
  flyout con las 4 (`shapeFly`/`flyRect…`); elegir una cambia el icono del botón; clic fuera o
  mousedown en el lienzo lo cierra; los atajos R/E/P/L siguen y marcan la opción. ⚠️ El clic de
  cada opción lleva stopPropagation (son HIJAS del botón: sin él, el clic rebota al padre y
  reabre el menú). Verificado con el arnés node de DOM falso (29 checks: bbox exacto,
  deshacer/rehacer, radios de estrella, snap 45°, uids únicos, flyout). Arnés en scratchpad de
  la sesión (`test_shapes.js`); al arnés le hicieron falta `lastChild`/`dataset` en los
  elementos falsos y disparar toolFit para que la vista esté lista antes de simular.

- **2. Texto con fuentes del sistema — ✅ COMMIT c5c34d4 (24-jul).**
  Módulo nuevo **`text_vector.py`** (fontTools 4.63, ya estaba instalada; dependencia OPCIONAL con
  `HAS_FONTS` como las demás): `list_fonts()` escanea las carpetas del sistema (413 en la Mac,
  4.7s la 1ª vez, caché después; filtra emoji/símbolos/ocultas exigiendo A-a en el cmap) y
  `text_paths()` vectoriza con `BasePen` (resuelve composites, off-curves implícitos y
  súper-Béziers solos) + De Casteljau adaptativo ~0.003mm + `core._simplify_mm`. **El tamaño es
  ALTURA DE MAYÚSCULAS en mm** (medida sobre la H real; como Aspire, no puntos tipográficos).
  Kerning de tabla `kern` (GPOS fuera a propósito); tracking en mm; multilínea con interlineado
  natural×factor y alineación izq/centro/der. Baseline en Y=0, Y-arriba (la convención de la UI —
  el texto NO pasa por el volteo de SVG). Api `fonts`/`text_make` + rutas `/api/fonts`/`/api/text`.
  UI: herramienta T en el riel (atajo T) → modal (frase multilínea, selector de fuente, alto mm,
  espaciado, interlineado %, alineación) → "Crear texto" lo pone AGRUPADO al centro de la vista;
  **doble clic encima lo reedita** (regenera conservando el CENTRO del bbox viejo). La receta vive
  en `textMeta[gid]` y viaja en snapshot/undo y en el **.dstudio v3**; reeditar tras escalar a
  mano regenera al tamaño de la receta (limitación consciente v1). Verificado: 14 checks Python
  (H de 20mm=20mm, hueco de la O, kerning AV<AA, .ttc, script), 23 checks de UI en node con
  backend fingido, y punta a punta por el servidor real. **Gotchas de la sesión:** (1) el atajo
  global de teclado solo ignoraba INPUT — un textarea nuevo habría disparado herramientas/Supr
  al escribir; ahora ignora INPUT|TEXTAREA|SELECT; (2) volvió a morder el **servidor viejo en
  8765** (los curl devolvían 404-HTML: matar el proceso, como ya documentaba esta nota).

- **3. Booleanas + contorno-offset — ✅ COMMIT c9d2434 (24-jul).**
  Módulo nuevo **`geo_ops.py`** (shapely opcional, mismas convenciones que cnc_gcode: unidad =
  anillos par-impar con symmetric_difference, la O conserva su hueco): `boolean_op`
  (union/difference/intersection entre unidades) y `offset_op` (unión de las unidades +
  `buffer` con quad_segs por sagita ~0.005mm). Api `geo_boolean`/`geo_offset` + rutas
  `/api/boolean`/`/api/offset`. UI: sección **Combinar** (Unir/Restar/Intersectar, habilitadas
  con 2+ unidades) y **Contorno** (Dist ± mm + Crear; Enter en el campo dispara) en Propiedades.
  Reglas: **Restar = la unidad con índice de dibujo MÁS BAJO menos las demás** (la de abajo,
  como Minus Front de Illustrator — geoUnits ordena por Math.min de índices); las booleanas
  REEMPLAZAN los anillos consumidos (los trazos abiertos de esas unidades sobreviven y se
  avisa cuántos quedaron fuera); el contorno se SUMA como grupo nuevo seleccionado sin tocar
  el original; un texto soldado pierde su receta textMeta (ya no es texto) SOLO si el grupo
  quedó sin trazos. Verificado: 14 checks Python (áreas exactas, par-impar, contorno envolvente
  de figuras separadas, offset negativo devorador = error claro, arco de esquina ±0.01mm) +
  16 checks de UI simulada + e2e por el servidor real. **Gotcha del arnés**: tras dibujar con
  una herramienta hay que Escape antes de hacer marco — si no, el "marco" dibuja otra figura
  (dos checks fallaron por eso; no era bug de la app).

- **4. Edición de nodos (anclas + manijas) — ✅ COMMIT e856837 (24-jul, Jose la probó). Con esto la ÉPICA v1 QUEDA COMPLETA (formas → texto → booleanas/contorno → nodos).** El reto: los trazos viven APLANADOS en puntitos. Solución pro (la de Vectric): módulo
  **`curve_fit.py`** (Schneider de Graphics Gems, puro Python, sin dependencias) **re-ajusta
  Béziers** sobre la polilínea al entrar — detección de esquinas >35°, tramos de 2 pts = rectas
  exactas con manijas CERO, re-parametrización de Newton; rect→4 anclas exactas, círculo de
  300 pts→12 anclas suaves fieles a 0.018mm, estrella conserva sus 10 picos. Api `fit_nodes` +
  ruta `/api/fit`. UI: herramienta **flecha hueca "Editar nodos" (A)** en el riel; clic en un
  trazado → anclas (cuadritos); arrastrar ancla/manija, Shift+clic multi-selección, **doble
  clic agrega nodo** (en recta sin manijas; en curva parte con De Casteljau), **Supr quita**
  (respeta mínimo 2/3), manijas de anclas SUAVES giran en espejo conservando el largo de la
  gemela (colinealidad <5° al cargar = suave). **Esc/Enter/V/clic-en-vacío HORNEA** de vuelta a
  puntitos (flatten adaptativo 0.005mm; transform reseteado patrón mirrorActive; `nedit.uid`
  referencia por uid por si el doc cambia). Sin cambios = sin tocar doc ni historial; el
  pushUndo va en el PRIMER arrastre real (Cmd+Z durante la edición = hornear y deshacer → el
  original). `__DS` ganó getter `nedit` para los arneses. Verificado: 13 checks Python del fit
  + 23 de UI simulada + e2e (14 anclas para círculo de 200 pts por el servidor real).
  ⚠️ Limitación consciente v1: no hay "sacar manijas" de una esquina recta (convertir recta en
  curva) — se suple insertando nodos en la curva vecina; retomar si Jose lo pide.

- **5. Rondas 1+2 de diseño (9 funciones) — ✅ COMMIT 7279562 (24-jul, Jose las probó).**
  Pedidas por Jose en bloque ("adelante con las dos rondas"). Qué entró:
  · **Texto en arco**: campo "Curva" (±grados) en el modal — cada glifo se coloca RÍGIDO sobre el
    círculo (rota, no se deforma; + = arco, − = valle; por línea, R = ancho/θ); viaja en la
    receta textMeta. ⚠️ El ancho total PUEDE crecer con el arco (las letras inclinadas
    sobresalen) — el invariante correcto es que la ALTURA crece.
  · **Pluma (P — le QUITÓ el atajo al polígono, que quedó solo en el flyout)**: clic=esquina,
    arrastre=ancla suave con manijas simétricas, clic en el 1º=cerrar, Esc/Enter=terminar,
    Cmd+Z quita el último punto; liga elástica curva al cursor; hornea con nodePts (la cocina
    del editor de nodos) vía `insertPath()` (helper nuevo que también usan formas y tijeras).
  · **Tijeras (C)**: clic sobre un trazado → abierto queda en DOS (mismo grupo, puntas
    coincidentes en el corte); cerrado se ABRE por ahí (arranca y termina en el corte).
    ⚠️ Limitación: el anillo abierto conserva puntas coincidentes → el criterio de cierre por
    distancia lo sigue viendo "cerrado"; un 2º corte re-abre en otro punto, no parte en dos.
  · **Imanes (snapping)**: al ARRASTRAR, bordes/centros de la selección se pegan (6 px) a
    bordes/centros de las demás unidades + hoja + guías; líneas de imán en acento; Alt lo
    apaga. El arrastre se REHIZO de incremental a delta-total (orig+delta) para que el imán no
    acumule deriva — moving ahora guarda A/orig/candidatos.
  · **Reglas y guías**: reglas en mm (22 px, paso adaptativo 1–1000 según zoom); arrastrar
    DESDE la regla crea guía (izq=vertical, arriba=horizontal), re-arrastrable, soltarla en la
    regla la borra, clic en la ESQUINA borra todas; van en el .dstudio (`guides`).
  · **Copias en círculo**: el modal Copias ganó segmentado Rejilla|Círculo (N, radio, ángulo);
    pivote a "radio" mm BAJO el centro de la selección, sentido horario, 360=n reparte /
    parcial=/(n−1) — coronas/relojes.
  · **Engrosar línea** (`expand_op`, LineString.buffer): abiertos → cápsula cerrada con grosor
    total; REEMPLAZA la línea. Botón en Contorno (activo solo con abiertos en la selección).
  · **Esquinas redondeadas** (`round_op`, apertura+cierre morfológicos −r/+2r/−r): redondea
    convexas Y cóncavas, por unidad (vecinas no se funden), figura devorada por el radio se
    devuelve INTACTA con aviso; REEMPLAZA. Botón en sección Esquinas.
  · **Imagen de referencia** (riel): foto tenue (40%) centrada a la hoja, bloqueada, debajo de
    todo; clic de nuevo la quita; solo de la SESIÓN (no viaja al .dstudio a propósito — base64
    inflaría el archivo). Escritorio: Api `ref_image` (data-URL); web: `refInput`+FileReader.
  Rutas nuevas `/api/expand` `/api/round` + Api geo_expand/geo_round/ref_image; `geoRemove()`
  (helper de borrado+poda de textMeta) y `GEO_API` (mapa de geoCall). __DS ganó pen/guides/
  refImg/snapGuides. ⚠️ Gotcha de arranque: las vars nuevas que draw() pinta (guides/RUL/
  refImg) deben declararse ANTES de draw() en el archivo — draw corre durante la carga.
  Verificado: 34 checks nuevos de UI + 18 de motores Python + regresión completa (125 checks
  UI en 5 arneses) + e2e real (expand/round/texto-arco). El arnés aprendió: E(id) crea el
  elemento falso al vuelo y `_segBtns` generaliza los segmentados.

- **6. Menú contextual (clic derecho) + limpieza de barras — ✅ COMMIT b005939 (24-jul, Jose lo probó).** Pedidos de Jose tras probar las rondas:
  · **Retoques y GRAN LIMPIEZA de barras** (la regla: lo que ya vive en el clic derecho sale de
    las barras): Ajustar vista salió del riel a una PÍLDORA PROPIA junto al zoom (id `toolFit`
    intacto — los arneses lo usan); ELIMINADOS del riel "Calcar imagen" (vive en Abrir→imagen y
    "Otra imagen" del modal), "Espejo horizontal" y "Ver vectores de corte" (toolCut + bandera
    showCut fuera: era un tinte magenta heredado de tkinter sin sentido aquí — todo YA es
    vector de corte); del panel Propiedades ELIMINADAS las secciones "Acciones rápidas"
    (Duplicar/Copias/Agrupar/Desagrupar → atajos y clic derecho) y la fila "Voltear" (→ SOLO
    clic derecho; sin atajo aún). **Al abrir la app siempre aterriza en el paso Diseño**
    (setSideMode('design') tras el applyMachine del arranque; el cambio manual de máquina
    conserva su flujo a Configuración). Riel final: flecha, nodos, mano, figuras, pluma, texto,
    tijeras, imagen de referencia, tema.
  · **Menú contextual** (`ctxMenu`, construido por contexto): sobre un trazado → Editar texto…
    (si es texto) / Editar nodos / **Cortar aquí** (tijeras en el punto del clic, sin cambiar de
    herramienta) / booleanas (solo con 2+ unidades) / contorno-engrosar-redondear (con los mm
    del panel; solo si aplican) / Copiar-Duplicar-Eliminar / Agrupar-Desagrupar / **Traer al
    frente / Enviar atrás**. En vacío → Pegar (des habilitado sin portapapeles), Deseleccionar,
    Ajustar vista. Cierra con Escape/clic fuera/rueda; sin menú en paso CNC o en medio de
    pluma/nodos/dibujo.
  · **Z-ORDER nuevo** (`reorderActive`): reordena los ARREGLOS del doc (paths/off/…/uid) — el
    índice de dibujo ES el orden de encimado y el de "la de abajo manda en Restar"; selección
    re-mapeada, undo normal, uids viajan con la figura (trayectorias CNC intactas).
  · ⚠️ **Gotcha cazado**: el mousedown del lienzo NO distinguía botón — el clic derecho
    arrancaba un arrastre (pushUndo+moving) antes del contextmenu. Guardia `e.button===2 →
    return` al inicio. Señal: menú contextual sobre canvas SIEMPRE necesita esa guardia.
  · **2ª tanda del menú (mismo día)**: sección Acomodo (Voltear H/V, Rotar 90°, Centrar en la
    hoja, Copias…, Zoom a esto) + **Restablecer transformación** (quita giro/escala SIN mover el
    centro: recoloca off para conservar el centro del bbox) + **Bloquear** (NUEVO: `lockedUids`
    Set por uid — invisible para hitPath/marquee/selectHit/activeIdx-"todos", se pinta en
    --faint, viaja en snapshot/undo y .dstudio `locked`; el grupo no arrastra a sus miembros
    bloqueados; se libera con "Desbloquear todo (N)" del menú de VACÍO — el clic derecho encima
    no lo ve, a propósito). El corte/export SÍ incluye bloqueados (es candado de EDICIÓN).
  Verificado: arnés `test_ctx_ui.js` (38 checks) + regresión total 163 checks en 6 arneses.

- **7. Fuentes: caché + selector visual — ✅ COMMIT f73dbb9 (24-jul, Jose lo probó; incluye quitar la etiqueta Todos/Objeto/Grupo del panel).**
  Jose reportó que las fuentes tardaban en cargar. (a) **Caché a DISCO** (`fonts_cache.json`
  junto a cnc_config, en .gitignore; v2 con firma barata de carpetas mtime+conteo): escaneo
  frío 2.9s → 0.001s al reabrir; hilo daemon en main() de design_studio y studio_server lo
  CALIENTA al arrancar. (b) `list_fonts` ahora devuelve `family`/`sub` por separado →
  (c) **selector VISUAL** (`fontPick`/`fpBtn`/`fpDD`/`fpList`): cada fuente dibujada con ella
  misma vía CSS (el navegador ya tiene las fuentes del sistema instaladas; `cssFontOf` mapea
  sub→font-weight/style: bold 700, black 800, italic…), con BUSCADOR, y el TEXTAREA del modal
  escribe con la fuente elegida en vivo. El `<select id=txFont>` viejo murió; doText usa
  `fontSel`. ⚠️ Lección del arnés: los elementos falsos necesitan que `innerHTML=''` vacíe
  `children`, o las listas reconstruidas acumulan filas fantasma. Verificado: 29 checks de
  texto (visual pick, buscador, payload con la fuente elegida) + regresión 169 total.
  **+ COMMIT c38d4e7**: flechas ↑/↓ recorren fuentes con vista previa EN VIVO (vuelta completa,
  respetan el filtro, Enter confirma, auto-scroll) y fix del desplegable DECAPITADO: el
  overflow:hidden de .sheet lo recortaba → clase .sheet.canspill (overflow visible) SOLO en el
  modal de texto. Señal: flotante que se corta en un borde = overflow:hidden en un padre.

- **8. NESTING (acomodar piezas en la hoja) — ✅ COMMIT 423f65f (24-jul, Jose lo probó).**
  Investigación previa (pedida por Jose): el óptimo académico es NFP+algoritmo genético
  (SVGnest/Deepnest); libnest2d haría NFP exacto pero arrastra Boost/Clipper/NLopt (mal para
  PyInstaller). **Decisión: Bottom-Left-Fill (Burke et al.) sobre shapely** — grandes primero,
  rotaciones candidatas, barrido abajo-izquierda con PRE-FILTRO DE BBOXES (el grueso de las
  pruebas es aritmética pura; shapely solo cuando el bbox no descarta) + compactación por
  bisección (3 vueltas ↓←, 9 pasos). Módulo **`nest_ops.py`**: unidades par-impar + abiertos
  con cuerpo (buffer 0.15), gap por buffer/2, margen, **obstáculos** (= piezas BLOQUEADAS:
  se quedan y estorban — sinergia con el candado), skipped si no caben, util%. Api `geo_nest`
  + `/api/nest`. UI: sección "Acomodar en la hoja" (Sep./Margen/rotaciones 0-90-45 seg +
  botón con estado Acomodando…); aplica rot alrededor del PIVOTE (centro del bbox de unidad,
  el MISMO que usa el motor — viaja en el payload para que casen) + traslado; undo completo.
  Números: 30 piezas en cama 2440×1220 en 0.65s; 6/6 rects e2e util 42%; pieza larga elige
  sola girar 90°. Verificado: 14 checks Python + 12 UI + e2e (regresión total 187 en 7
  arneses). **Mejorado el mismo día (pregunta de Jose "¿más ángulos?")**: medido
  que MÁS ÁNGULOS SOLOS pueden EMPEORAR con greedy (hoja apretada: 90°=9/16 vs 45°=8/16 — el
  codicioso se auto-bloquea); la mejora correcta fue **MULTI-ARRANQUE** (6 órdenes: área/lado
  mayor/lado menor desc + 3 barajados con semilla fija 20260724 → se queda el mejor por
  (piezas, área)): apretada subió a 10/16 en todos los modos y los finos ganan +2% util; **y Jose remató con la pregunta correcta ("¿por qué elegir
  ángulo yo?")**: la perilla de ángulos SE ELIMINÓ — el motor ahora es AUTOMÁTICO por etapas
  (90°→45°→15° como rondas del torneo, presupuesto de 5s entre etapas, gana el mejor por
  (piezas, área)): apretada 10/16 util 64% en 3.8s; cama grande 30/30 en 5.6s. `rots` explícito
  sigue aceptado (compatibilidad/pruebas). ⚠️ El presupuesto hace el resultado dependiente de
  la VELOCIDAD de la máquina (una lenta puede saltarse etapas) — determinista en la misma
  máquina, no entre máquinas. **+ ANIMACIÓN de intentos (pedida por Jose; ✅ quedó dentro del COMMIT 90161c3 con el en-vivo)**:
  el motor devuelve `runs` (bitácora: stage/order/placed/util por intento) + `best`; la UI los
  REPRODUCE como fantasmas (acento; ganador en verde --good) con marcador (intento i/N, giros,
  orden, piezas, util%) a 380ms/cuadro + 3 cuadros de pausa en el ganador; clic o Esc saltan y
  aplican; el doc NO se toca hasta el final (cache de effPts previo). `finishNestAnim`/
  `applyNestPlacements`; __DS ganó `nestAnim`. Jose preguntó si era en vivo o repetición →
  se hizo **EN VIVO de verdad (✅ COMMIT 90161c3)**: `nest_start` (hilo daemon + `_JOBS`, poda a 4) / `nest_status`
  (runs desde `from`, al terminar placed/best/util/skipped; error del hilo se reporta) + Api
  geo_nest_start/status + rutas; la UI SONDEA cada 300ms y anima MIENTRAS el motor trabaja
  (HUD "Calculando…" sin intentos aún; el tick avanza hasta el último intento disponible);
  saltar ANTES de terminar deja `skip=true` y aplica solo al llegar el ganador. `nest_op`
  síncrono sigue para compatibilidad. Verificado: 16 checks nest-UI (parciales sin done, doc
  intacto, salto pendiente que aplica al terminar) + e2e real con lecturas parciales +
  regresión 204. **Jose señaló DESPERDICIO en plotter → MODO ROLLO (✅ COMMIT 90161c3, junto con el EN VIVO)**: la causa
  era llenar ABAJO-izquierda a lo LARGO del rollo de 3m (una fila = todo el rollo). Ahora
  `mode:'roll'` (la UI lo manda si machine=plotter; CNC sigue 'sheet'): BLF gira a
  IZQUIERDA-abajo (columnas: llenar el ANCHO, avanzar lo mínimo), slide compacta ← primero,
  puntaje = (piezas, −largo usado, área), y se reporta `used` (mm de material) en HUD/toast
  ("usarás X cm"). + **candidatos por ESQUINAS** de lo ya puesto antes de la rejilla (más
  apretado y más rápido; `_free_at` compartido). MEDIDO: 8 piezas 100×50 en rollo 3000×600:
  845mm→**120mm** de material (7×); 20 mixtas → 665mm, 5.6s. Motor hoja intacto (invariantes
  re-verificados); 17 checks nest-UI; regresión 205. Mejora futura consciente: capa genética (orden+rotación evolutivos)
  estilo SVGnest si el taller pide más aprovechamiento.

- **9. Rotación LIBRE con el mouse — ✅ COMMIT 423f65f (24-jul).**
  Manija estilo Illustrator: tallo+perilla arriba del centro de la caja de selección
  (ROTH=22px); arrastrarla gira la selección alrededor del CENTRO FIJO capturado al agarrar
  (no el bbox vivo — se recalcularía y derivaría), aplicando deltas incrementales a off/rot;
  **Shift = saltos de 15°**; el ángulo se pinta junto a la perilla. Clic sin mover no ensucia
  el historial (pop del pushUndo, patrón de moving); giro completo = UN undo; sin manija en
  modo "Todos"; bloqueada en paso CNC. ⚠️ Lección de arnés (2ª vez): DESHACER LIMPIA LA
  SELECCIÓN — todo guion que siga tras un undo debe re-seleccionar antes de usar manijas.
  Verificado: 13 checks (90° exacto con bbox intercambiado y centro quieto, snap 15°, undo,
  sin-basura, modo todos hace marco) — regresión total 200 checks en 8 arneses.

- **10. Escalar con el mouse + AUTOGUARDADO — ✅ COMMIT 446d9ce (24-jul).** (a) Las 4 esquinas de la caja de selección ya se ARRASTRAN: escala anclada en la
  esquina OPUESTA (clavada), factores desde el estado INICIAL del drag (orig cacheado — sin
  deriva), **Shift = proporcional por la diagonal** (convención Illustrator); clic sin mover
  no ensucia el historial; bloqueado en paso CNC; prioridad de manijas: esquinas → perilla de
  rotación → mover. (b) **Autoguardado**: `dirtySince` se enciende en pushUndo (toda mutación
  pasa ahí); cada 60s si hay cambios se respalda el proyecto completo a `autosave.dstudio`
  (junto a la config, en .gitignore) vía autosave_save/load/clear (studio_backend + Api +
  rutas); al ABRIR, `checkAutosave` (con candado de una-sola-vez que solo se fija cuando hay
  RESPUESTA — loadWork corre hasta 3 veces) ofrece recuperar con askConfirm (nombre + hora);
  decidir (sí o no) limpia el respaldo; guardar de verdad también. Verificado: 18 checks
  (recuperación única, dirty solo-con-cambios, factores exactos 1.6/1.3, ancla clavada,
  Shift proporcional) + backend real + regresión 223 en 9 arneses.

- **11. Suavizar importaciones facetadas — ✅ COMMIT 446d9ce (24-jul).**
  El "curve fitting de Vectric" que la nota vieja daba por no-construido: clic derecho →
  **"Suavizar (quitar facetas)"** (solo en trazos ≥8 pts) re-ajusta Béziers con el Schneider
  de curve_fit (`fit_nodes_many`, tol 0.1mm — más alta que la de edición: debe TRAGARSE las
  facetas) y hornea con nodePts; transform reseteado, uid conservado (CNC ok), undo normal.
  ⚠️ **Bug cazado por la prueba de calidad**: en cerrados SIN esquinas, la COSTURA de los dos
  cortes artificiales heredaba la tangente de la faceta local (un lado) → quiebre de ~15°
  sobrevivía. Fix: tangente CENTRAL en costuras artificiales (`seam_suave`/`bordes`) — 24-gon:
  quiebre 15°→2.6°, desviación 0.10mm, 6 anclas; de pilón el editor de nodos ya no tiene
  costura en círculos (12 anclas, rect sigue 4 esquinas exactas). Api `fit_many` +
  `/api/fit_many`. Verificado: calidad medida + 5 checks de menú + regresión 228 en 9 arneses.

- **12. Tanda de "reflejos Illustrator" (6 funciones) — ✅ COMMIT 1683124 (24-jul).** Pedida en bloque (#1,2,4,5,9,10 de la lista de faltantes):
  · **Cmd+A** selecciona todo (excluye bloqueados; 1 solo → individual).
  · **Alt+arrastre = jalar una COPIA** (copyWithGroups antes de armar moving; alt+clic sin
    mover se CANCELA restaurando el snapshot — no basta con pop del undo, la copia ya existía).
  · **Transformar de nuevo (⇧⌘D + menú)**: `lastXform` se graba en los mouseup de mover
    (con bandera dup si fue alt-copia → repetir ⇧⌘D = PATRÓN en cadena), rotar (deg) y
    escalar (fx/fy); repite sobre la selección actual.
  · **Pathfinder completo**: Exclusión (symmetric_difference en boolean_op, botón boolX) y
    **Dividir** (`divide_op`: polygonize de todas las fronteras + filtro de caras-material
    por representative_point; cada cara queda SUELTA — grupo solo si trae hueco; botón
    boolDiv + menú). Api geo_divide + /api/divide.
  · **Unidades mm|pulgadas** (`unitMode` + mmU/uMM; seg en el modal de Configuración,
    persistida en cnc_config `units`): convierte SOLO en los bordes — campos X/Y/W/H
    (mostrar y ESCRIBIR), barra inferior y etiquetas de reglas (pasos imperiales 1/8"…);
    el interno sigue 100% mm (CNC/HPGL intactos).
  · **Multi-hoja CNC** (`sheets` 1-8 en Configuración, persistida; plotter siempre 1):
    el lienzo dibuja N láminas lado a lado (pasillo 50mm, "Hoja n"), fitView abarca todas
    (`sheetSpanW`), y el NESTING reparte con la restricción de no cruzar pasillos
    (`_x_valid`, candidatos/rejilla por hoja, slide topado a SU hoja, hoja temprana gana,
    util×hojas); menú de vacío ofrece **"Traer la hoja N aquí"** (flujo: cortas la 1,
    apartas, traes la siguiente — el export sigue siendo por hoja física). .dstudio guarda
    sheets. Backend medido: 3 piezas 250 en 3 hojas de 300 → una por hoja (paso 350).
  Verificado: 18 checks nuevos + regresión 246 en 10 arneses.

- **13. COTIZADOR — ✅ COMMIT d6c6b77 (24-jul).** Botón "Cotizar" en la
  barra superior (visible en ambas máquinas; se apaga sin diseño). Cotiza la SELECCIÓN o
  todo: piezas (activeUnits), metros de corte, tiempo (misma fórmula del pie de página) y
  material (**plotter: cm de ROLLO** = extensión X del bbox × $/m lineal; **CNC: m² del
  bbox** × $/m²). Tarifas EDITABLES y PERSISTIDAS en cnc_config llave `quote`
  (mat_roll/mat_m2/rate_plotter/rate_cnc/setup/margin; cnc_set valida y mezcla parcial;
  el modal muestra la tarifa de la máquina ACTIVA y guarda en change). Desglose material+
  máquina+preparación → subtotal → margen % → TOTAL (y precio c/u con 2+ piezas).
  **"Copiar cotización"** arma texto listo para WhatsApp (clipboard con fallback a
  execCommand; sin portapapeles avisa, no truena). Verificado: 9 checks con matemática al
  centavo (total=mat+maq+prep exacto, margen ×1.3, persistencia del change, selección vs
  todo) + regresión 255 en 11 arneses.

- **14. ESQUINAS VIVAS (Live Corners de Illustrator) — ✅ COMMIT d6c6b77 (24-jul; la sección "Esquinas" del panel SE ELIMINÓ — el widget la reemplaza; también: medidas/tiempo del sidebar a la BARRA INFERIOR sin el texto Design Studio, y el NESTING del panel al RIEL con panel desplegable Sep/Margen/Acomodar).** En el editor de nodos (A), cada esquina RECTA (ancla sin manijas entre dos
  tramos rectos, ángulo <175°) muestra su **widget** (circulito con punto, 14px hacia adentro
  por la bisectriz). Arrastrarlo redondea EN VIVO: `liveCorner(k)` da la geometría
  (bisectriz, θ, maxR = tan(θ/2)·mín(lado)/2 — no comerse más de medio lado);
  `roundLiveCorners(base, infos, r)` reconstruye desde la BASE del drag (sin acumulación):
  cada esquina → dos anclas tangentes a d=r/tan(θ/2) con manijas h=(4/3)tan(Δ/4)·r (arco
  circular ≈ cúbica); el radio sigue al cursor con el mapeo r = avance·sin(θ/2)/(1−sin) —
  el ARCO pasa por donde va el mouse — y se muestra "r X mm" en vivo. **Con varias anclas
  seleccionadas, un widget redondea todas** (como AI). Clic sin mover no ensucia (dirty en
  el primer move del drag general). Tras soltar queda horneado en nodos (no re-ajustable —
  v1; deshacer sí). ⚠️ Verificación con matemática exacta: el punto más cercano del arco al
  vértice dista r·(√2−1) en 90° — el primer "fallo" del arnés era MI aritmética (esperaba
  r/2), no el código. 30 checks de nodos ahora; regresión 262 en 11 arneses.

## Novedades 23–24 jul 2026
- **`.ai` arreglado EN EL MOTOR (commit 492b1c8)**: los .ai perdían trazados enteros (18 de 39 en
  el logo de chalecos — todo path que empezara con curva se tragaba en silencio) y deformaban las
  curvas sobrevivientes. Causa: `AIParser._items_to_subpaths` asumía formato estilo SVG para los
  items de pymupdf; el formato REAL trae TODOS los puntos por segmento (`('c', inicio, c1, c2,
  fin)`) y NO existen items 'm'/'h'. **Señal para la próxima**: si la librería cruda ve más
  elementos que la app, el que pierde es nuestro código.
- **Vista 3D del corte** (fases R en [[cnc-richauto]]) y **auditoría del G-code** (ídem).
- **Botón "Importar" — ✅ COMMIT db5f141 (24-jul)**: suma otro archivo
  (SVG/DXF/AI/.dstudio) a la mesa SIN reemplazar. `addDoc`/`addProject` en studio_ui.html +
  `import_design`/`_load_vector` en design_studio.py (refactor: open_design usa el mismo helper).
  Reglas: lo existente intacto (uids viejos NO cambian → las trayectorias CNC calculadas
  sobreviven), lo nuevo entra como grupo propio a la derecha (+10mm, alineado abajo) y queda
  seleccionado; deshacible; mesa vacía → importar=abrir; de un .dstudio entran objetos con sus
  transformaciones pero **sus trayectorias NO** (uids ajenos, se avisa); grupos re-mapeados.
  Imágenes solo por Abrir (el calco reemplaza).
- **Técnica de prueba nueva que funcionó muy bien**: ejecutar el `<script>` COMPLETO de
  studio_ui.html en node con un **DOM falso mínimo** (Proxy con getElementById/addEventListener
  de mentira + getComputedStyle) y manejar la app por el gancho `window.__DS` (se le añadió
  `add`/`addProject`). Así se probó el flujo real de importar (9 checks) sin abrir la app.
  El extractor por marcadores (`node --check` + eval de funciones puras) sigue sirviendo para
  el módulo 3D.

## 27-jul-2026: CNC — seleccionar trayectorias por el lienzo y VERDE para la elegida — ✅ COMMITS 8dfc5ba + 477a802 + 26a8a52
Pedido de Jose: con varias trayectorias encimadas en la misma pieza no había forma de saber cuál
estabas editando.
- Cada grupo de la vista previa guarda **`tpi`** = a qué fila de la lista pertenece. ⚠️ Se calcula
  con `tpaths.indexOf(list[k])`, **no con `k`**: si una trayectoria falla no se apila en `groups` y
  los índices se correrían en silencio.
- La **seleccionada se pinta VERDE** (`--good`) y más gruesa; el resto sigue en magenta. Flechas de
  sentido y taladros heredan el color porque se pintan con el mismo `strokeStyle`.
  ⚠️ **Nació azul y se cambió a verde el mismo día**: Jose pidió el mapa de colores y al escribirlo
  salió la contradicción — en el lienzo **el azul ya significa "VARIAS figuras seleccionadas"**,
  justo lo contrario de "esta una trayectoria". **Regla del lienzo, respetarla al añadir colores:
  magenta (`--accent`/`--sel`) = UNA figura o acción en curso · azul (`--group`) = VARIAS ·
  verde (`--good`) = la trayectoria CNC activa · gris (`--faint`) = bloqueado.** El color no es
  adorno: en el diseño distingue selección individual (medidas ABSOLUTAS) de múltiple (RELATIVAS).
- **Pulsar una trayectoria en el lienzo** la selecciona en la lista, la carga en el formulario y
  lleva su fila a la vista. El impacto va **ANTES** que la selección de figuras (se dibujan encima)
  y solo actúa con `cncStep()` y vista previa encendida.
- **Pulsar CUALQUIER OTRA COSA la suelta** (COMMIT 477a802 — faltaba: solo estaba construida la
  mitad "seleccionar" y Jose preguntó por qué no se deseleccionaba). Vale en el vacío y sobre una
  figura; el clic **sigue su camino**, así que aún puede tomar la figura. En el paso Diseño no se
  toca (allí la lista ni se ve). ⚠️ **Soltar NO es solo quitar el verde**: el formulario vuelve a
  "trayectoria nueva" (el botón pasa de Recalcular a Calcular) — misma semántica que re-pulsar su
  fila, extraída a `deselectTp()` para que exista UNA vez. Efecto colateral asumido: lo tecleado
  en el formulario y aún no Calculado se pierde.
- El repintado se dispara **desde `paintTps()`**: por ahí pasa TODO cambio de `tpSel` (clic en fila,
  borrar, reordenar, calcular) → un único sitio del que acordarse.
- ⚠️ **Limitación del arnés descubierta aquí**: el DOM falso **no completa el arranque en modo CNC**
  (`applyMachine` no llega a aplicarse; comprobado contra la versión de ayer, así que es viejo, no
  una regresión). En las pruebas hay que poner `state.machine='cnc'` y `setSideMode('cnc')` a mano.

## 27-jul-2026: reacomodo de barras — ✅ COMMITS 7ccc539 + 28ce65b
- **Cotizar** se fue de la barra superior a la **BARRA INFERIOR, solo como icono**, junto al tiempo
  estimado (que es el dato del que sale el precio de máquina). Conserva su `id`, así que todo lo que
  lo enganchaba siguió igual; clase nueva `.statbtn` para iconos de la barra de estado.
- **"Exportar HPGL" ELIMINADO de la barra superior**: lo dejé puesto argumentando que era la acción
  diaria, Jose preguntó por qué, y mandó su regla del 24-jul (*lo que ya vive en otro sitio sale de
  las barras*). **Barra superior final: deshacer · rehacer · Abrir · Importar · Guardar ·
  Exportar… · conexión · Enviar al plotter.**
- Arnés nuevo `test_barras.js`: comprueba **dónde vive cada botón en el marcado**, no solo que
  funcione. Es lo que detecta que algo "se movió solo".

## 27-jul-2026: EXPORTAR COMO… (PNG/JPG/PDF/SVG/DXF) — ✅ COMMIT 0d8bed9
Pedido de Jose ("como lo tiene Illustrator"). Módulo nuevo **`export_ops.py`** + botón
"Exportar…" en la barra superior (visible con las DOS máquinas; el archivo de máquina
—HPGL/G-code— sigue por su camino aparte).
- **CERO dependencias nuevas**, que importaba porque el empaquetado acababa de cerrarse:
  PDF y rasterizado con **pymupdf** (ya estaba para leer `.ai`), DXF con **ezdxf** (ya estaba
  para leerlos). **PNG y JPG se obtienen rasterizando el MISMO PDF** → imagen y vector no
  pueden contradecirse, y hay un solo camino de dibujo que mantener.
- Regla **par-impar por unidad** (misma convención del lienzo y del corte): el hueco de la O
  sale hueco. Abiertos nunca se rellenan.
- Opciones: solo la selección (re-numera las unidades a la lista recortada) · encuadre
  "el diseño" con margen o "la hoja completa" · relleno (arranca como la vista del lienzo) ·
  resolución · **fondo Transparente o Blanco** (segmentado; Jose lo pidió explícito — nació como
  casilla escondida solo para PNG). El **blanco se pinta DENTRO del archivo** (rectángulo al fondo
  del PDF y del SVG), no solo en la imagen, para que viaje aunque abran el vector; el PNG blanco
  sale sin canal alfa. El diálogo **esconde lo que no aplica**: DXF sin aspecto, JPG sin elección
  de fondo (el formato no admite transparencia), PDF sin resolución.
- **Volteo de Y en UN solo sitio por formato**: PDF/SVG/raster son Y-abajo, DXF Y-arriba y no
  se toca (misma disciplina que salvó los imports en jul-2026).
- Guardas: DPI absurdo → baja solo (techo de píxeles) en vez de quedarse sin memoria; una
  recta (alto cero) no degenera la página; **el LWPOLYLINE cerrado NO repite el último punto**
  (repetirlo deja un segmento de largo cero que algunos CAM leen como pinchazo).
- **Verificado midiendo**: 33 checks del motor —100 mm miden 100 mm en los cinco formatos— y
  la prueba fuerte es la **IDA Y VUELTA**: exportar SVG y DXF y **reabrirlos con nuestros
  propios lectores**, que siguen midiendo 100×100. Más 31 de UI y e2e por el servidor real
  (los cinco con su MIME y reconocidos por `file`); el PNG se miró sobre fondo de color.
- **HPGL como un formato más** (27-jul, COMMIT 9290183): en modo plotter el diálogo ofrece
  PNG·JPG·PDF·SVG·DXF·**HPGL**; con la CNC no aparece (su G-code sale del panel de Corte, que
  tiene multi-trayectoria y una fresa por archivo). ⚠️ **No se reimplementa**: el diálogo DELEGA
  en `saveHpgl`/`hpglPayload` de siempre (ahora con parámetros opcionales: índices y aviso de
  terminado) y solo decide qué trazados entran → "solo lo seleccionado" también vale para el
  corte. El check que amarra esto compara que el envío del diálogo sea **idéntico** al del botón
  de la barra. **El botón "Exportar HPGL" de la barra superior SE ELIMINÓ** el mismo día: lo dejé
  puesto (argumento: es la acción diaria, un clic contra tres) y Jose preguntó por qué — su regla
  del 24-jul manda, *lo que ya vive en otro sitio sale de las barras*. Barra superior final:
  deshacer · rehacer · Abrir · Importar · Guardar · **Exportar…** · conexión · Enviar al plotter.
  El check de equivalencia se reapuntó y quedó MEJOR: ya no compara contra un botón, sino contra
  **lo que recibe "Enviar al plotter"** → lo que exportas es exactamente lo que corta la máquina.
- **Limitación consciente v1**: todo sale en NEGRO. Los parsers sí leen `fill`/`stroke` del
  archivo, pero `_load_vector` los descarta al entrar a la UI — para exportar con los colores
  originales habría que conservarlos en el documento y en el `.dstudio`.

## 27-jul-2026: VISTA RELLENA — ✅ COMMIT b37520c
Jose: "necesitamos ver los trazados rellenos para identificar la figura de manera correcta".
Botón en el **riel izquierdo**, en su propia sección tras "Imagen de referencia" (Jose lo pidió ahí;
nació en la píldora del lienzo) + **Cmd+Shift+Y**. No cambia la herramienta activa y `setTool()` no
lo apaga (togglea IDs concretos, no todo `.tool`) — igual que toolRef y toolNest.
- Cada **unidad** (un grupo, o un trazo suelto) se pinta con **regla PAR-IMPAR** (`fill('evenodd')`):
  un anillo dentro de otro abre hueco. Es la **misma convención del motor de corte**
  (geo_ops/cnc_gcode/nest_ops) → **lo relleno es lo que quedará de material**. Vista fiel, no
  adorno: si dos figuras del mismo grupo se traslapan, el traslape sale hueco *porque el cortador
  las corta las dos*.
- **Sólido y del MISMO color que su propio contorno** (`--stroke`, o `--sel`/`--group` si está
  seleccionada, `--faint` si está bloqueada) → figura y línea se funden en una silueta maciza.
  Nació translúcido al 26% y **Jose pidió opaco** ("que se vea como una sola figura"). Ojo: "negro"
  es relativo al tema — en tema oscuro el contorno es gris claro y el relleno también (si fuera
  negro literal sería invisible sobre el lienzo casi negro). Consecuencia asumida: dos unidades
  encimadas ya **se tapan** por orden de dibujo; para ver lo de abajo, Cmd+Y (contorno).
  Los trazos **abiertos no se rellenan**. Relleno y modo contorno (Cmd+Y) se apagan entre sí, pero
  el apagado por contorno **no pisa la preferencia guardada**.
- Persistencia: llave **`fillview`** en `cnc_config`. ⚠️ Hubo que añadirla en TRES sitios
  (`CNC_DEFAULTS`, la lista de llaves que lee `cnc_get`, y `cnc_set`) — el mismo patrón que hizo
  perder `spinup` en su día: **llave nueva que no se agrega a la lista blanca se pierde en silencio**.
- Refactor de paso: **una sola definición de "cerrado"** (`isClosedPts`, ≤0.05 mm) compartida por
  el criterio de los motores y el relleno; y **una sola llamada a `effPts` por trazo** (no tiene
  caché: pedirla dos veces —una para saber si cierra, otra para dibujar— encarecía cada cuadro).
- **Medido** en vez de supuesto: 0.25 ms extra por cuadro con 32 000 puntos (un cuadro dura 16.7 ms).
- Verificado: 18 checks (unidades, hueco de la O, abiertos sin rellenar, vistas opuestas,
  persistencia) + backend real + regresión de actualizaciones (28+24).
- **Lección del arnés (3ª vez que muerde)**: el manejador de teclado vive en **`window`**, no en
  `document` — disparar la tecla en el sitio equivocado da un falso fallo. Y los elementos falsos
  necesitan que `firstChild`/`lastChild` nunca sean `null` (el HTML real sí tiene esos nodos).

## 25-jul-2026: EMPAQUETADO para Windows y Mac + auto-actualización — ✅ COMMIT d77d07c
Jose eligió **distribuir SOLO Design Studio** (Plotter Antike se queda como motor/respaldo, ya no
se compila) y **sin cuenta de desarrollador de Apple** (app sin firmar → primera apertura con clic
derecho → Abrir). Lo construido, todo verificado:
- **`updater.py`** (módulo nuevo, compartido escritorio/servidor): `check` → `start`/`status`
  (descarga en hilo con % de avance) → `apply`. El `apply` escribe un **ayudante externo** (bash en
  Mac, PowerShell en Windows) y cierra la app: **un programa no puede sobrescribirse a sí mismo**
  (en Windows el .exe queda bloqueado; en Mac el .app está corriendo). Guardas: solo con
  `sys.frozen` (como script manda a `git pull`), el destino debe terminar en `.app` **y** tener
  `Contents/MacOS` antes de cualquier `rm -rf`.
- **BUG REAL encontrado y corregido en las DOS apps: las versiones se comparaban como TEXTO** →
  `'2026.7.10' > '2026.7.9'` es **falso** como texto, o sea que una versión nueva se veía más
  vieja y nunca se ofrecía. Ahora `vkey()` compara número a número y **la CI rechaza etiquetas con
  letras** (`v2026.07.25b`) porque al comparar se ignoran y dos releases empatarían.
- **Lección dura (costó un cuelgue): esperar a que un proceso muera con `kill -0` NO sirve** — un
  proceso **zombi** (terminado pero no recogido por su padre) sigue "existiendo" y el ayudante
  esperaba para siempre. Se mira el ESTADO real (`ps -o stat=`, `Z` = se fue). La señal fue que la
  prueba se colgó sin salida: el padre capturaba la salida del ayudante, que la heredó, y cada uno
  esperaba al otro.
- **⚠️ En Mac, `.app` SIEMPRE con `ditto`** (`-c -k --keepParent` para comprimir, `-x -k` para
  extraer), nunca el `zipfile` de Python: **pierde los enlaces simbólicos y el permiso de
  ejecución** y la app llega rota. La prueba de reemplazo lo verifica explícitamente.
- **potrace viaja DENTRO de la app** (`preparar_potrace.py` → `vendor/`): se copia con su
  `libpotrace.0.dylib`, se reapunta con `install_name_tool` a `@loader_path` y se **re-firma**
  (cambiar el binario invalida la firma ad-hoc y macOS lo mata). Sin esto el calco B/N solo
  funcionaba en esta Mac, que tiene Homebrew. `_potrace_bin()` busca primero dentro del paquete.
- **`DesignStudio --diagnostico`**: lista qué piezas trae y cuáles faltan. Nació de una duda real —
  la app puede **arrancar perfecta** y tener texto/nesting/CNC muertos porque una librería no quedó
  empaquetada. La CI lo corre tras compilar en las dos plataformas.
- **`DesignStudio.spec` estaba en `.gitignore`** (era el auto-generado): la CI habría fallado sin
  el archivo. Ahora es receta a mano y va a git. Iconos por `crear_icono_studio.py` (marca magenta;
  ⚠️ **ImageDraw no MEZCLA transparencias, las REEMPLAZA** — el "brillo" con alpha abrió un hueco
  blanco en el primer intento).
- **CI reescrita** (`.github/workflows/release.yml`): job `preparar` (valida etiqueta + crea el
  release) → `windows` y `mac` (macos-14 = **Apple Silicon**; un Mac Intel necesitaría un job
  aparte en macos-13). Instalador Windows propio: `instalar_studio.bat/.ps1` (copia la carpeta a
  `%LOCALAPPDATA%\Antike\DesignStudio` con `robocopy /MIR`, misma carpeta que reemplaza el update).
- **Verificación**: 24 checks del motor + 28 de la interfaz (arnés de DOM falso, ver abajo) + 8 del
  reemplazo real con apps de mentira (incluidas las guardas) + **descarga real de 82 MB** desde
  GitHub + app de Mac compilada (133 MB) que arranca y pasa el diagnóstico **también después de
  empaquetarla y desempaquetarla como hará la CI** + `auditar_gcode.py` 133/133.
- **PUBLICADO el 27-jul**: `v2026.07.27` (primer release) y `v2026.07.27.2` (con todo lo del 27).
  Windows 64 MB · Mac 57 MB, ambas verdes en la CI y con el diagnóstico completo dentro.
  ⚠️ **El primer intento FALLÓ en Windows**: la consola (cp1252) **no puede imprimir `✓ ✗ · →`** y
  el `print` mató el paso — el icono y potrace ya se habían creado bien. Arreglado en los tres
  scripts y en `--diagnostico` (comprueba la codificación y cae a texto pelado), porque **le
  pasaría igual a un usuario en CMD**. Regla: **la salida de terminal, en ASCII**.
  Ensayo real del ciclo de actualización preparado en `/tmp/ensayo-update` (copia con la versión
  bajada a mano) — falta que Jose pulse el botón.

## 28-jul-2026: la app NO ARRANCABA en Windows — la "marca de internet" — ✅ `v2026.07.28`

**Síntoma** (en la PC de un usuario, no la de Jose): cuadro *"Unhandled exception in script"* con
`Failed to resolve Python.Runtime.Loader.Initialize from ...\_internal\pythonnet\runtime\Python.Runtime.dll`.

**Causa**: al extraer un `.zip` bajado del navegador, Windows le pega a cada archivo el flujo
alterno **`Zone.Identifier`** ("vino de internet"). A un **ensamblado de .NET** eso lo mata: el CLR
se niega a cargarlo. Y pywebview en Windows **no puede vivir sin pythonnet** (`import clr`) — es el
puente Python↔.NET que dibuja la ventana. El instalador nunca quitaba esa marca.

- **Arreglo**: `instalar_studio.ps1` hace `Unblock-File` recursivo tras el `robocopy`.
  ⚠️ **Ese archivo se mantiene 100% ASCII a propósito**: PowerShell 5.1 lee UTF-8 sin BOM como ANSI
  y destroza los acentos. (Lo rompí al comentar con `⚠️` y hubo que revertirlo.)
- **No hay pescadilla**: el propio `.ps1` también sale marcado, pero `instalar_studio.bat` lo lanza
  con `-ExecutionPolicy Bypass`, que ignora la zona. Por eso el instalador sí corre.
- **La auto-actualización NUNCA estuvo afectada**: `updater.py` descarga con `urllib` y descomprime
  con `zipfile`, y **ninguno de los dos pone la marca** — solo la ponen los navegadores y el
  Explorador. Fallaba únicamente la instalación manual del zip.

### El hueco de fondo: `--diagnostico` no probaba LA VENTANA
Revisaba 8 piezas y **ninguna era el motor gráfico**, porque `webview.start()` lo carga de forma
**perezosa** — o sea *después* del chequeo. Resultado: la CI compilaba, imprimía "todo completo" y
publicaba una app que **moría al abrirse**. Ahora `--diagnostico` reproduce el `import clr` y, si
falla, imprime la causa y el comando de PowerShell que lo arregla.
**Lección general: un chequeo que corre antes de la carga perezosa no prueba nada de lo que viene
después.** Si la librería se carga tarde, el diagnóstico tiene que forzar esa carga.

**Cómo se confirmó**: en la Windows de la CI el mismo paquete da `Ventana (motor grafico) OK` — el
empaquetado estaba bien, lo único distinto en la máquina rota era el origen (zip del navegador).
**Señal de lectura**: el error decía *"Failed to **resolve**"* **con la ruta completa del archivo**,
no *"file not found"* → **el archivo estaba ahí**; era bloqueo/permisos, no empaquetado.

✅ **CONFIRMADO por el usuario**: con `Unblock-File` abrió sin problema. Diagnóstico a mano:
`Get-Item <ruta>\Python.Runtime.dll -Stream Zone.Identifier` (si existe → era esto).

## 28-jul-2026: y entonces se colgaba ~2 de cada 3 arranques — ✅ `v2026.07.28.2`

Ya abierta, la app entraba en **"No responde"** de forma **intermitente**. El síntoma que reportó
Jose fue "no puedo maximizar la ventana" — pero eso era **consecuencia**: Windows no redimensiona
una ventana que no bombea mensajes.

**Causa: una carrera.** `main()` lanzaba el calentado de fuentes **antes** de `create_window()`.
Python solo corre **un hilo a la vez** (GIL) y ese escaneo es Python puro y acaparador, justo
cuando la ventana necesita entrar a Python para armarse. Quién gana depende del reloj → **2 de 3**.
En Mac nunca se vio: 3.12 s de escaneo contra ~1 min en Windows (Defender inspecciona cada uno de
los ~400 archivos de fuente que abre una app **sin firmar**).

**Y se alimentaba solo**: el hilo era `daemon=True`, así que al cerrar la app a medias **no escribía
el caché** → el siguiente arranque re-escaneaba desde cero → la carrera se repetía siempre.

- `design_studio.py`: el calentado se engancha a **`win.events.loaded`** (+1.5 s de margen).
  pywebview lo despacha **en su propio hilo** (`Event(self)` sin lock, `event.py:44-47`; un
  manejador **sin parámetros** se llama tal cual). ⚠️ **Nunca volver a lanzar trabajo pesado de
  Python antes de `create_window()`.**
- `text_vector.py`: el escaneo hace `time.sleep(0)` cada 16 archivos para soltar el intérprete.
  Costo medido: **3.12 s vs 3.27 s = ninguno**.

### Cómo se descartó lo demás (el camino, que vale más que la respuesta)
1. **WebView2 faltante** → descartado: *"sí se ve la interfaz"*. Dato clave: WebView2 pinta en un
   **proceso aparte**, por eso se ve la interfaz completa y congelada mientras el anfitrión está
   muerto. Ver la UI **no** prueba que la app viva.
2. **Abrazo mortal Python↔ventana** → descartado leyendo el código: **cero** `evaluate_js`. Además
   pywebview corre cada llamada `js_api` **en un hilo aparte** a propósito (`util.py:247-250`), así
   que una función lenta de Python **no** congela la ventana.
3. **Costo de primera vez** → descartado por *"2 de cada 3"*. **Un fallo intermitente casi nunca es
   'algo roto': son dos cosas compitiendo.** Esa frase fue la que resolvió el caso.

⚠️ **NO reproducible en Mac** (necesita el Windows lento). Verificado aquí: contrato del evento
contra el despachador real de pywebview sin GUI + prueba de punta a punta abriendo la app 16 s con
el caché borrado → ventana viva y caché reescrito completo (60439 B) **después** de cargar, no
antes. ❌ **Este arreglo era un defecto real pero NO era la causa del cuelgue** — siguió pasando.

## 29-jul-2026: LA CAUSA RAÍZ del cuelgue en Windows — `api.window` → `api._window` — ✅ `v2026.07.29.2` (COMMIT 72e3ec4)

**Un abrazo mortal (deadlock), y era código nuestro.** `api.window = win` le colgaba la ventana al
objeto que se le pasa a `js_api`. pywebview **RECORRE** ese objeto para saber qué métodos exponerle
al JavaScript (`util.py` → `inject_pywebview` → `get_functions`) y, al ver un atributo que es un
objeto no-invocable con `__module__`, **se mete dentro**. Adentro de la `Window` toca la propiedad
**`width`**, cuyo getter (`window.py:215-219`) hace `events.shown.wait(15)` y luego
`gui.get_size(uid)`: **le pregunta el tamaño a la ventana nativa**… que en ese instante todavía se
está creando en **otro hilo**. Los dos se esperan. Para siempre.

**Arreglo**: renombrar a **`_window`** — pywebview **salta** los atributos que empiezan con guion
bajo (`util.py:193-194`). ⚠️ **Ese guion bajo NO es estilo, es el arreglo**; está comentado con
letras grandes en `Api.__init__` para que nadie lo "limpie". **Regla: nunca colgar del objeto
`js_api` un atributo público que sea un objeto** — pywebview lo recorrerá.

**Por qué ~2 de cada 3 y solo en Windows**: es una carrera. Si la ventana alcanza a mostrarse antes
de que el recorrido llegue a `width`, no pasa nada. En Mac esa carrera se gana siempre.

### Lo que DE VERDAD resolvió el caso: instrumentar (`v2026.07.29`)
Cinco hipótesis caídas razonando desde el Mac (marca de internet ✅ sí era, pero de OTRO fallo ·
escaneo de fuentes · WebView2 ausente · abrazo mortal por `evaluate_js` · procesos huérfanos).
La sexta salió a la primera **en cuanto la app contó qué le pasaba**:
- **`arranque.log`** junto a la config (`%APPDATA%\Antike\PlotterController\`), con marca por paso;
  se vuelca a disco en CADA línea (si la matan a la fuerza no se pierde nada). **Se acumula entre
  arranques** — los arranques sanos sirven de grupo de control contra el trabado.
- **Vigilante `faulthandler`**: pasados 25 s sin cargar, vuelca **la pila de todos los hilos**, y
  repite. Se desarma solo al cargar la página, así que un arranque sano no escribe nada.
- **Cómo se leyó**: los seis volcados eran **IDÉNTICOS** → no estaba lento, estaba **DETENIDO**. Y
  mostraban los tres hilos del abrazo (principal en `create_window`, el de la UI en `create`, y el
  puente de JS parado dentro de un `getattr`). ⚠️ **La app se distribuye sin consola: sin este
  registro un cuelgue al arrancar no deja NINGÚN rastro.** No quitarlo.

**Lección**: en cuanto un fallo solo ocurra en una máquina que no puedes tocar, **deja de deducir e
instrumenta**. Cada teoría costó un release y una reinstalación; el registro lo resolvió en un
intento. Y: **un fallo intermitente = dos cosas compitiendo**, casi nunca algo roto.

## 29-jul-2026: fabricante `BuiltByJose` + el paso CNC ya no se salta solo — ✅ `v2026.07.29.3`

**Renombre de carpetas** (convención `Fabricante\Aplicación`, como `Google\Chrome`). El fabricante
era `Antike` y la config vivía en `PlotterController`, heredado de la app vieja de tkinter y ya
engañoso: los ajustes de Design Studio bajo el nombre del programa anterior.

| Antes | Ahora |
|---|---|
| `%LOCALAPPDATA%\Antike\DesignStudio` | `%LOCALAPPDATA%\BuiltByJose\DesignStudio` |
| `%APPDATA%\Antike\PlotterController` | `%APPDATA%\BuiltByJose\DesignStudio` |
| `~/Library/Application Support/Antike/PlotterController` | `…/BuiltByJose/DesignStudio` |
| `com.antike.designstudio` | `com.builtbyjose.designstudio` |

- **`_migrar_config()` en `plotter_control.py`**: al arrancar, si la carpeta nueva no existe y la
  vieja sí, **COPIA** todo (fresas, materiales y presets del CNC, config del plotter, caché de
  fuentes, autoguardado). ⚠️ **Copia, NO mueve, a propósito** — ahí viven las fresas: si algo sale
  mal la vieja queda intacta. No pisa una carpeta nueva ya existente. ⚠️ **No borres
  `_FABRICANTE_VIEJO`/`_APP_VIEJA`**: los usa la migración.
- El **instalador borra la instalación vieja** tras copiar la nueva, con tres guardas (ruta
  exactamente la esperada · distinta de la recién instalada · contiene el `.exe` de esta app).
- ⚠️ **`--diagnostico` DEDUCE la ruta del `.exe`**, no la lleva a fuego: quien actualice con el
  botón de la app **se queda en la carpeta vieja** (`updater.py` reemplaza la carpeta actual, sea
  cual sea); solo reinstalar con el zip estrena la nueva. **La config migra igual**, porque eso lo
  hace la app al arrancar, no el instalador.
- ⚠️ **NO se tocó `format: 'antike-tools'`** de las fresas exportadas: es un **identificador de
  formato**, no un nombre — cambiarlo rompería los archivos ya exportados. Ni la app vieja de
  tkinter (`instalar.ps1`/`desinstalar.ps1`), que ya no se distribuye.

**Paso CNC**: elegir la máquina CNC en la barra de arriba **ya no salta** el panel lateral al paso
CNC (`applyMachine` ahora hace `setSideMode('design')` siempre). Primero se acomoda el diseño; al
paso CNC se pasa **a mano** con el toggle Diseño|CNC. Quedan cuatro sitios que tocan el paso
lateral y **ninguno lleva a 'cnc' automáticamente**: solo el clic del usuario.
Verificado 3/3 con el arnés de DOM falso. ⚠️ **El arnés NO crea los botones hijos de las barras
segmentadas** (`querySelectorAll('button')` → 0), así que el clic físico no se puede simular: hay
que llamar a la función y verificar la cadena leyendo el código. `__DS.cnc.setSideMode` (anidado,
no en la raíz de `__DS`).

⏳ Falta probarlo en la máquina.

---

✅ **CONFIRMADO EN LA MÁQUINA (29-jul)**: 5 arranques seguidos sin trabarse. Con la tasa anterior
(fallaba 2 de cada 3) eso sería 1 entre 243 por azar — el cuelgue está muerto.
⏳ Único fleco: **no se probaron uno por uno los 12 diálogos de archivo renombrados**
(Abrir / Guardar / Exportar). Si alguno truena al abrir su cuadro, es un `_window` mal puesto.

### Pendientes (act. 25-jul-2026 — tras la maratón de diseño del 24-jul)
1. **Rebaba en MDF 3mm**: sigue viva tras el primer corte real (salió en AMBOS lados pese al
   preset de 4000) → prueba A/B pendiente: pasada más agresiva / fresa nueva / **DOWNCUT**
   (al comprarla, alta en "Fresas…" con sus presets). Protocolo: cambiar UNA cosa a la vez.
2. **Verificar orientación del corte en el plotter** — el arreglo del eje Y cambió el HPGL
   ([[estado]] Fase 3). Necesita hardware. (La orientación CNC ya quedó ✓ con el corte real.)
3. **Calibrar marchas S2–S8** del A11E leyendo Hz del variador (tabla provisional en la app).
4. Diferidas de diseño que quedan: **texto en trayecto**, **recortar con figura (máscara de
   taller)**, **warp/envelope**, **voltear-como-copia**, **V-carve** (el proyecto grande).
   (Ya HECHAS del viejo listado: z-order ✓, texto ✓, contorno/offset ✓, snapping ✓,
   nesting ✓, y toda la épica Illustrator — ver notas 1-14 arriba.)
5. **Ruta comercial** ([[idea-comercial]]): en paso 1 (producción propia); siguiente hito =
   piloto con 2-3 talleres. **Empaquetado Win+Mac ya HECHO** (ver sección de arriba); falta
   decidir repo privado (el empaquetado y el primer release ya están hechos). Para vender a talleres convendría la
   cuenta de desarrollador de Apple (99 USD/año): hoy la app de Mac va sin firmar y asusta
   en la primera apertura.

## Lanzador de escritorio (Mac) — ícono "Design Studio.app"
Igual que Plotter Antike, hay un **ícono en el Escritorio** que lanza la app con doble clic. Es una
**mini-app de AppleScript** (`osacompile`) que por dentro solo corre:
`/opt/homebrew/bin/python3 /Users/josegf/Design-Studio/design_studio.py`. **NO es la app compilada de
97 MB** (`dist/DesignStudio.app`); es el atajo ligero de desarrollo — si mueves/borras la carpeta del
código, deja de funcionar. Ícono propio: cuadro magenta de la marca + cursor blanco de selección.
- ⚠️ **Gotcha que costó rato:** en macOS moderno (26.x) reemplazar `Contents/Resources/applet.icns`
  **NO cambia el ícono** si la app trae un **`Assets.car`** (catálogo compilado) referenciado por
  `CFBundleIconName` en el `Info.plist` — **ese catálogo manda sobre el .icns**. Arreglo: `plutil -remove
  CFBundleIconName`, borrar `Assets.car`, `xattr -cr` (quitar detritus de Finder) y **re-firmar**
  (`codesign --force --deep -s -`); luego reventar caché (borrar `com.apple.iconservices*` de
  `$(getconf DARWIN_USER_CACHE_DIR)` + `killall Finder Dock`). **Señal:** cambiaste el .icns y Finder no
  lo refleja → busca un `Assets.car`.

## Cómo correrla y compilarla (Mac, Python de Homebrew)
```bash
# Escritorio (ventana nativa):
/opt/homebrew/bin/python3 ~/Design-Studio/design_studio.py
# Modo web (para depurar en el navegador): abre http://localhost:8765
/opt/homebrew/bin/python3 ~/Design-Studio/studio_server.py
# Compilar app de Mac:
cd ~/Design-Studio && /opt/homebrew/bin/python3 -m PyInstaller --windowed --noconfirm \
  --name DesignStudio --add-data "studio_ui.html:." --add-data "version.txt:." \
  --collect-all webview design_studio.py    # → dist/DesignStudio.app
```

## Calco de imagen (Image Trace) — `img_trace.py`
Convierte fotos (PNG/JPG…) en trazos de corte. Dos modos:
- **B/N (silueta):** Pillow (gris + umbral) → **potrace** (CLI, `brew install potrace`) → SVG con curvas
  Bézier suaves → `core.SVGParser` → trazos. Máxima fidelidad de contorno (familia del calco de Illustrator).
- **Color:** **vtracer** separa por colores. ⚠️ **El binding Python de vtracer 0.6.15 CRASHEA (segfault)
  si se le pasa CUALQUIER parámetro** — solo funciona con defaults. Solución: controlar la cantidad de
  colores **reduciéndolos antes con `Image.quantize`** y llamar a vtracer sin argumentos.
- **Dependencias** (para el Python de Homebrew): `potrace` (Homebrew) + `Pillow` + `vtracer` (pip
  `--break-system-packages`; hay wheel cp314). El módulo se llama **`img_trace.py`** (NO `trace.py`,
  que choca con la stdlib).
- **UI:** herramienta en el riel (icono de foto) → sube imagen → modal con Umbral/Suavizado/Ignorar
  manchas/Invertir (B/N) o Colores (color) → "Calcar" carga el resultado como diseño (agrupado).
- **La fidelidad la limita la imagen de entrada:** nítida y de alto contraste = buen calco.

## Conectar el plotter: Mac vs Windows (para probar la Fase 3)
El motor usa `pyserial` → `serial.tools.list_ports.comports()`, que nombra el puerto distinto según el
sistema. Es el MISMO dispositivo, distinto nombre:
- **Windows:** `COM3`, `COM4`, … (el usuario elige el COM).
- **Mac:** un archivo `/dev/cu.*`. El plotter aparece como **`/dev/cu.usbserial-…`** o
  **`/dev/cu.usbmodem…`** (o con el nombre del chip: `SLAB_USBtoUART`, `wchusbserial`). Se usa `cu.`
  (callout), no `tty.`. El panel de Design Studio ya lista estos nombres automáticamente.

**Cómo identificar el puerto del plotter en Mac:** con el plotter desconectado solo salen puertos
internos (`/dev/cu.debug-console`, `Bluetooth`, `Buds3…` — ninguno es el plotter). Se enchufa el
plotter, se pulsa ↻, y **el nombre nuevo que aparece es el plotter**. Baud casi siempre **9600**.

**Dos causas de "no aparece":**
1. **Plotters viejos usan RS-232 (serial DB-9), no USB.** Necesitan un **adaptador USB-a-Serial**; ese
   adaptador es el que se ve como `/dev/cu.usbserial-*`. Sin él no hay conexión con una Mac moderna.
2. **Falta el driver del chip** (CH340 / CP210x / Prolific): si al enchufar y refrescar la lista NO
   cambia, es esto — hay que instalar el driver del chip del cable.

## Eje Y — historia en DOS actos (¡leer los dos!)
**Acto 1 (21-jul):** los calcos y SVG salían boca abajo → se puso un **volteo ciego de TODOS los
imports** en `loadDoc` (JS).
**Acto 2 (22-jul): ese volteo ciego era un BUG.** Jose reportó que los diseños se volteaban "cuando
antes no". Verificado con pruebas (triángulo asimétrico por formato): **cada parser entrega una
orientación DISTINTA** —
- **SVG** (`core.SVGParser`, `_root_mtx` sin Y negativa): entrega **Y-abajo** → SÍ hay que voltear.
- **AI** (`core.AIParser`): **ya invierte la Y** al parsear (`page_h` en plotter_control) → NO tocar.
- **DXF**: Y-arriba de nacimiento → NO tocar.
- **Calcos** (potrace/vtracer): producen SVG → SÍ voltear.

**Arreglo definitivo:** el volteo vive en el **backend, por formato** — `flip_paths_y()` en
`studio_backend.py`, aplicado solo a `.svg` en `design_studio.open_design` y `studio_server
/api/parse`, y siempre en `img_trace._svg_to_paths`. El JS **no voltea nada** (`loadDoc` tiene el
comentario). **Convención firme: todo lo que llega a la UI ya viene Y-arriba.** El volteo es sobre
el centro del conjunto → el bbox no cambia.
- ⚠️ Sigue **pendiente verificar la orientación del corte en hardware** (plotter y, cuando llegue
  la Fase B del CNC, también el .tap).
- **Lección:** "todos los imports salen mal" era en realidad "solo los SVG salen mal". Antes de
  corregir una orientación global, **probar CADA formato con una forma asimétrica** (un triángulo
  punta-arriba delata el volteo al instante).

## Bugs arreglados 22-jul-2026 (reportados por Jose tras la Fase A del CNC)
1. **Calco: "No such file or directory: potrace"** — se invocaba `potrace` a secas y las apps
   lanzadas desde Finder (ícono del Escritorio) o entornos recortados **no tienen /opt/homebrew/bin
   en el PATH**. Arreglo: `_potrace_bin()` en img_trace.py resuelve ruta absoluta (which + rutas
   Homebrew típicas). **Señal:** "funciona en terminal pero no desde el ícono" = problema de PATH.
2. **Eje Y** (ver arriba, Acto 2).
3. **En modo CNC, abrir un diseño pisaba el área con la del plotter** — `open_design`/`/api/parse`
   devuelven el área del plotter y `loadDoc` la aplicaba sin mirar la máquina activa. Arreglo:
   guardia `if(state.machine==='plotter')` en `loadDoc` y `loadProject`.

## Lecciones (señales)
- **Bug del lienzo que "no funcionaba":** un bucle de retroalimentación inflaba el `<canvas>` (medía
  su propio tamaño para fijarse el tamaño → crecía sin parar). Arreglo: `#cv{width:100%;height:100%}`.
  Señal: el contenedor medía 1076×701 pero el canvas reportaba 2400×1200.
- **En modo "Todos", clic en una figura debe seleccionarla individual** (no mover todo): `activeContains`
  debe devolver `false` cuando no hay selección explícita.
- Depurar el lienzo en Chrome (sirviendo con `studio_server.py`) es MUCHO más rápido que a ciegas.

Relacionado: [[estado]] (la app vieja), [[idea-web-online]] (multi-dispositivo, en pausa).
