---
name: cnc-richauto
description: "CNC router 122×244cm (Asia Robotics, controlador RichAuto DSP) — investigación del dialecto G-code y plan para integrarla a Design Studio estilo Vectric Aspire"
metadata: 
  node_type: memory
  type: project
  originSessionId: 661c489b-f53b-4842-91af-46e807877393
  modified: 2026-07-23T23:38:49.633Z
---

# CNC RichAuto — integración a Design Studio (planeada 22-jul-2026)

Jose tiene, además del plotter de corte, una **máquina CNC de 122×244 cm** (cama 1220×2440 mm)
comprada a **Asia Robotics**, con **controlador RichAuto (AutoNow) A11E** (confirmado por Jose
el 24-jul-2026 leyendo el handle; "AutoNow" es la marca que serigrafían junto a RichAuto). Antes
la trabajaba con **Vectric Aspire**; quiere que Design Studio genere los **archivos G-code** con
un flujo lo más parecido a Aspire.

## Investigación verificada (manual oficial RichAuto A1X, leído completo el 22-jul-2026)

**Cómo se trabaja:** el RichAuto es un controlador *offline* — NO se le manda el trabajo por cable
desde la compu. Se guarda el archivo G-code en una **USB (FAT16/32, recomiendan 2–8 GB)**, se
enchufa al handle y se procesa desde ahí. También se puede copiar al almacenamiento interno.
⚠️ El manual advierte: caracteres ilegales o G-code no estándar → error de lectura. Nombres de
archivo cortos y ASCII.

**Formatos que lee:** G-code (`.nc`, `.tap`, `.txt`, `.g`, `.u00`, `.mmg`), PLT, DXF, bitmap.
Usaremos **`.tap`** — lo pidió Jose explícitamente (22-jul-2026): es lo que su flujo con Aspire
producía (los posts de Vectric para RichAuto salen como `*.tap`). El contenido es G-code normal;
solo cambia la extensión.

**G-code soportado (lista oficial del manual, apéndice 9.4):** G00/G01/G02/G03, G04, G17-19,
G20/**G21**, G40-44/G49, **G54**-59, ciclos de taladrado G73/G81/G82/G83, **G90**/G91,
**M03/M04/M05**, M06, M08/M09, **M30**, y palabras T/S/F/H.

**⚠️ Trampas del controlador (menú "G Code Setup" del handle):**
- **`F Read` viene en "Ign F" de fábrica** → el controlador IGNORA las velocidades del archivo y
  usa su propia "Work Speed". Para que respete nuestras F hay que ponerlo en "Read F". Lo mismo
  con `S Read` (velocidad de husillo). **Documentar esto en la UI** — es la 1ª causa de "la
  máquina no hace caso a la velocidad que puse".
- `AbsCntr Off/On`: centros de arco (I,J) incrementales por defecto. **Nos da igual**: no vamos a
  emitir arcos (ver decisión abajo).
- En muchas máquinas chinas el husillo se controla con la **perilla del variador (VFD)**, no con
  la S del G-code — confirmar cómo está la de Jose.

**Decisión técnica clave — solo G00/G01, sin arcos:** el motor de Design Studio ya representa TODO
como polilíneas densamente muestreadas (styled paths = listas de puntos en mm). Emitir únicamente
movimientos lineales G01 es lo natural, elimina de raíz los problemas de arcos G02/G03 que
reportan los foros de Vectric con estos DSP, y el manual mismo usa ese estilo en sus ejemplos.

**Esqueleto de archivo seguro (calcado del ejemplo del manual):**
```
G90 G54          (absoluto, sistema de coordenadas 1)
G21              (milímetros)
M03 S18000       (husillo ON)
G00 Z<seguro>    (subir a altura segura)
G00 X.. Y..      (viajar)
G01 Z-<pasada> F<bajada>   (hundir)
G01 X.. Y.. F<corte>       (cortar)
...
G00 Z<seguro>
M05
M30
```

## Qué se imita de Aspire (el flujo que Jose ya conoce)
1. **Job Setup**: tamaño del material, **grosor**, cero de Z (cara superior o cama), datum XY.
2. **Biblioteca de herramientas**: fresa con diámetro, profundidad por pasada, stepover, RPM,
   avance de corte y de penetración (persistir en JSON junto a `plotter_config.json`).
3. **Trayectorias (toolpaths)**: Perfil (por fuera / por dentro / sobre la línea, con pasadas
   múltiples y puentes/tabs), Vaciado (pocket), Taladrado, y quizá V-carve (mucho más complejo).
4. **Preview de trayectorias + tiempo estimado**, lista de trayectorias, guardar `.nc`.

## Matemática nueva necesaria
- **Offset de polígonos** (perfil por fuera/dentro, vaciado por anillos): **`shapely` 2.1.2**
  (hay wheel cp314 arm64 para el Python de Homebrew — verificado con pip --dry-run el 22-jul).
- Z entra al juego por primera vez (el plotter era 2D): pasadas múltiples, altura segura, rampa.

## Plan por fases
- **A. Cimientos — ✅ CONSTRUIDA 22-jul-2026** (backend y API verificados con pruebas; falta el
  vistazo visual de Jose). Qué se hizo:
  - **`cnc_config.json`** (junto a `plotter_config.json`, vía `_cnc_path()` en `studio_backend.py`).
    ⚠️ **Archivo APARTE a propósito**: `_save_config()` de la app tkinter sobrescribe
    `plotter_config.json` con solo sus 6 llaves y habría borrado lo del CNC en silencio.
  - `cnc_get()`/`cnc_set()` en `studio_backend.py` (defaults + merge parcial + validación),
    expuestos en `design_studio.py` (Api) y `studio_server.py` (`GET/POST /api/cnc`).
  - **UI** (`studio_ui.html`): segmentado **Plotter | CNC** en la barra superior (persiste la
    elección); en modo CNC se ocultan "Exportar HPGL", "Enviar al plotter" y la píldora de
    conexión (la CNC es offline); aparece sección **Material** (grosor + cero de Z arriba/cama +
    Ø de la fresa activa) y **Herramienta** (selector + resumen + modal "Gestionar fresas…" con
    alta/baja/edición). El área de trabajo del modal de Configuración edita la máquina activa.
    Tiempo estimado en modo CNC usa el avance de la fresa (mm/min), no la velocidad del plotter.
  - 5 fresas preset (MDF, acrílico, PVC espumado, madera, 1/8" detalle) como punto de partida.
  - **Gotcha de la sesión:** un `studio_server.py` viejo seguía corriendo de la sesión anterior
    (puerto 8765 ocupado) — servía el HTML nuevo pero sin las rutas nuevas (404). **Señal:** el
    HTML trae los cambios pero la API no existe → proceso viejo; `lsof -iTCP:8765` y matarlo.
- **B. Perfil + G-code — ✅ CONSTRUIDA 22-jul-2026** (motor verificado con 6 pruebas unitarias +
  punta a punta por el servidor; falta vistazo visual de Jose y el corte real). Qué se hizo:
  - **`cnc_gcode.py`** (módulo nuevo): `make_toolpaths()` compensa la fresa con **shapely**
    (instalada 2.1.2). **Anidado par-impar** con `symmetric_difference` + `buffer(±r)`: la letra
    "O" por fuera expande el contorno Y contrae el hueco, como Aspire (verificado). Trazos
    abiertos: solo "Sobre la línea"; en fuera/dentro se saltan y se avisa cuántos.
    `build_gcode()` emite solo G00/G01, pasadas múltiples (techo de prof/pasada, la última exacta),
    cero de Z 'top' o 'bed' (verificadas ambas escalas de Z), altura segura +5mm, `M03 S`,
    `M05 / G00 X0 Y0 / M30`. **Comentarios normalizados a ASCII** (el manual advierte que
    caracteres raros rompen la lectura del controlador).
  - Backend: `cnc_toolpaths_preview()` / `cnc_build_tap()` en studio_backend; Api de escritorio
    `cnc_toolpath`/`save_tap` (diálogo nativo, escribe con `newline='\n'`); servidor
    `POST /api/cnc_toolpath` y `/api/tap` (descarga como blob).
  - UI: **pestaña "CNC" propia en el sidebar** (Propiedades/Capas/CNC — pedida por Jose; el tab
    solo aparece en modo CNC, se auto-enfoca al entrar y te saca de él al salir). Contiene
    Material, Herramienta y "Corte · Perfil" (segmentado Fuera/Dentro/Línea, Prof. que
    **sigue sola al grosor del material** mientras no la edites, contador de pasadas), botón
    "◉ Ver trayectorias" (dibuja en azul el recorrido del CENTRO de la fresa; se invalida solo
    al cambiar geometría/fresa/lado vía `killPrev()` en pushUndo/restore/loaders), y "Exportar
    HPGL" se convierte en **"Exportar G-code"** en modo CNC (mismo botón, `btnSaveLbl`).
- **C. Cajeado, taladro, puentes — ✅ CONSTRUIDA 22-jul-2026** (verificada con pruebas unitarias +
  punta a punta; falta vistazo de Jose). **La rampa de entrada quedó FUERA a propósito** (la
  bajada lenta de la fresa la suple en MDF/PVC; retomarla si el acrílico da guerra). Qué se hizo:
  - `cnc_gcode.py`: **`make_pocket()`** — anillos concéntricos hacia adentro por zona conexa
    (paso = `stepover_pct` de la fresa, % del Ø, default 40), del centro a la pared (pared al
    final = acabado limpio); respeta huecos anidados (holgura euclidiana exacta = radio).
    **`drill_points()`** — centro del bbox de cada contorno cerrado. **`build_drill()`** —
    picoteo: entre pasadas sube a +2mm a despejar viruta. **Puentes** en `build_gcode()`:
    `_split_ring()` parte el anillo por longitud de arco (n puentes de ancho w centrados lejos
    del arranque); solo actúan en pasadas más profundas que (prof − alto): la fresa sube al techo
    del puente con G01 y sigue. Anillos abiertos o pocket: sin puentes.
  - Backend: `_cnc_make()` despacha op profile/pocket/drill; preview devuelve también `drills`
    y `dia`. Fresas ganan `stepover_pct` (validado 10–90; las guardadas viejas caen a 40).
  - UI: segmentado **Operación (Perfil/Cajeado/Taladro)** en la pestaña CNC — **con ICONOS svg y
    tooltip, no texto** (pedido de Jose 22-jul; y el pocket se llama **"cajeado"**, el término de
    Aspire en español — no volver a "vaciado" en textos de cara al usuario). Perfil muestra
    Fuera/Dentro/Línea + campos Puentes/Ancho/Alto (default 3×8×3, 0 = sin puentes); Cajeado y
    Taladro muestran nota explicativa. Taladros se previsualizan como círculo (Ø de la fresa) con
    cruz. Campo "Paso %Ø" en el modal de fresas.
  - **Ojo en pruebas de offsets:** medir holguras con distancia EUCLIDIANA al polígono (las
    esquinas se redondean con radio exacto); medir por ejes da falsos fallos en esquinas.
- **D. Orden de corte y puentes pro — ✅ CONSTRUIDA 22-jul-2026** (verificada con pruebas
  unitarias + orden comprobado en un .tap real por la API; falta vistazo de Jose). Qué se hizo:
  - **Huecos ANTES que el contorno exterior** de cada pieza (`_units_from`: interiores → exterior).
    En "Sobre la línea" el anidado se calcula por contención (más profundo primero).
  - **Vecino más próximo** entre piezas desde el origen (`_order_units`, greedy con muestreo) y
    **cada anillo cerrado re-arranca en su vértice más cercano** a la posición actual
    (`_rot_to_nearest`) → viajes mínimos en la cama de 2.4 m. Cajeado: NN entre zonas
    (centro→pared intacto por zona). Taladro: NN entre puntos.
  - **Puentes por distancia**: segmentado Nº/mm en la UI ("uno cada X mm", default 250; mínimo 2
    por anillo); payload nuevo `tabs:{mode,v,w,h}` (el backend acepta el viejo `{n,...}`).
  - **Puentes RAMPEADOS** (pendiente 2:1, `_RAMP_SLOPE`): la fresa sube/baja interpolando XYZ en
    el mismo G01 (sin escalones verticales); en rectas la rampa es un solo segmento 3D, en curvas
    se insertan los quiebres (`_ring_with_tabs`/`_z_on_ring`; los puentes pueden cruzar el
    empalme del anillo — se maneja con corrimientos ±perímetro).
  - ⚠️ **Lección de prueba:** en tramos RECTOS una rampa correcta NO tiene puntos intermedios
    (un G01 interpola XYZ solo); lo que hay que asertar es "ningún cambio de Z sin avance XY".
- **E. Flujo de trayectorias estilo Aspire — ✅ CONSTRUIDA 22-jul-2026** (pedida por Jose:
  "elegir trayectorias, orden, render, rampas, puentes opcionales"; verificada con pruebas +
  e2e; falta vistazo de Jose; se commitea JUNTO con la D). Qué se hizo:
  - **Lista de trayectorias** en la pestaña CNC: "＋ Nueva de la selección" (sin selección =
    todo el diseño) crea una trayectoria con los parámetros del editor; cada fila tiene ojito
    (incluir/excluir), ↑↓ (orden de corte), ✕. La fila seleccionada carga sus parámetros al
    editor y TODO cambio del editor escribe en ella (`commitEditor`). Sin lista, el flujo viejo
    de "una operación → todo" sigue funcionando (fallback).
  - **uid estable por trazado** (`doc.uid`, `uidSeq`): las trayectorias referencian objetos por
    uid y sobreviven a borrar/pegar/deshacer; el `.dstudio` v2 guarda uids + `cncTps`.
  - **Puentes con checkbox** (on/off explícito) y **entrada en rampa** (checkbox, perfil y
    cajeado): cada pasada desciende avanzando por el contorno (pendiente 1:5, `_ENTRY_SLOPE`),
    repasa el tramo de rampa a fondo y la siguiente pasada arranca donde terminó
    (`_ring_pass` unifica rampa + puentes con `z = max(rampa, techo_puente)`). Verificado:
    CERO hundimientos verticales en material con rampa activa.
  - **Render**: botón "▣ Render" pinta las trayectorias al ANCHO REAL de la fresa (lineCap
    round), color madera más oscuro cuanto más profundo; taladros como círculos llenos.
  - **Export multi-trabajo**: las trayectorias activas salen EN ORDEN en un solo `.tap`
    (`build_jobs`, marcas `( -- nombre -- )`, un solo M03/M30). **Fresas distintas → rechazo
    con mensaje** (el RichAuto no tiene ATC; se exporta un archivo por fresa apagando las
    otras). Backend acepta payload viejo (plano) y nuevo (`jobs`).
  - **Gotcha emisión**: al encadenar pasadas, no re-emitir `G01 Z` a la altura donde ya está
    la fresa (movimiento nulo que ensucia el archivo) — se rastrea `z_now`.

- **F. Formulario estilo Aspire — ✅ CONSTRUIDA 22-jul-2026** (Jose comparó contra Aspire y el
  flujo estaba AL REVÉS; se rehizo tras cotejar el formulario "2D Profile Toolpath" de la doc
  oficial V12 de Vectric). **El flujo correcto y actual**:
  1. seleccionar vectores → 2. clic en la operación → 3. llenar el FORMULARIO →
  4. **"⚙ Calcular trayectoria"** crea (o recalcula la seleccionada) + **auto-preview**.
  ⚠️ **El formulario NO escribe en vivo** — sin Calcular no hay cambios (antes goteaba cada
  keystroke a la trayectoria: eso era lo "incorrecto"). Cambiar de operación con una
  trayectoria seleccionada = empezar una NUEVA (en Aspire no se cambia el tipo).
  - **Campos nuevos**: Nombre; **P. inicial** (start depth — corta de start a start+prof);
    **Dirección Concordante/Convencional** (se implementa orientando los anillos:
    climb = material a la IZQUIERDA del avance con husillo horario → `orient()` de shapely,
    fuera=CCW/huecos CW; dentro y cajeado invertido; verificado por área firmada);
    **Holgura** (± mm sobre el offset; positiva deja material); en Material: **Z segura**
    (clearance) y **checkbox "volver a 0,0"** (home_end) — van en `cnc_config.json` y
    `cnc_get()` migra configs viejas completando llaves faltantes del material.
  - Diferido consciente (existe en Aspire, es pulido): leads, editor de tabs con clic,
    preview 3D.
  - **Rampas COMPLETAS estilo Aspire (22-jul noche)**: tipos Suave/Zigzag/Espiral + definir
    por Ángulo o Distancia (`ramp={'type','mode','v'}`; bool legado sigue valiendo).
    Espiral = bajada repartida en toda la vuelta (overlap=False en `_ring_pass`) + vuelta
    plana final; Zigzag = `_zigzag_pass` (vaivén con reversa) + vuelta a fondo. Verificadas
    pendientes exactas por ángulo y distancia, reversa del zigzag, espiral+puentes.
    ⚠️ **Gotcha**: `build_jobs` hacía `bool(j.get('ramp'))` (legado) y colapsaba el dict de
    configuración a True — la señal fue "pendiente clavada en la constante vieja pese a pedir
    5°". Al extender un parámetro de bool a dict, cazar TODOS los casts intermedios.
  - **Husillo antihorario (M04)**: NO se expone — Aspire tampoco lo tiene (verificado en foros
    Vectric: lo resuelven editando el archivo). Las fresas estándar son de mano derecha (M03);
    la decisión real giro-vs-avance es Concordante/Convencional, que ya existe. RichAuto sí
    soporta M04 si algún día hay fresa zurda.

- **H. Flujo de dos pasos + pulido de interacción — ✅ COMMIT dba4178 (22-jul noche)**:
  - **Toggle primario Diseño|CNC** en el sidebar (solo visible con la CNC activa): Diseño =
    Propiedades/Capas; CNC = **Configuración/Corte**. Entrar al paso CNC aterriza SIEMPRE en
    **Configuración** (material+fresa, como el Job Setup de Aspire) y "Continuar a Corte →"
    avanza; volver = la pestaña (Jose pidió quitar el botón de regreso). `setSideMode()`,
    panes `paneCncCfg`/`paneCncCut`; `applyMachine` muestra/oculta `modeBar`.
  - **Candado del diseño en el paso CNC** (`cncStep()`/`cncLock()`): no arrastrar/mover/borrar/
    pegar/duplicar/agrupar (aviso claro); la SELECCIÓN sigue viva y es **INDIVIDUAL dentro de
    grupos sin desagrupar** (clic/Shift/marco por trazado — en Diseño el clic sigue tomando el
    grupo entero).
  - **Dirección re-etiquetada "A favor / Contra"** (concordante/climb vs convencional en los
    tooltips) — pedido de Jose al no entender "Concord./Convenc.".
  - **Flechas de SENTIDO de corte** en la vista previa (cada ~90px de pantalla, ocultas en
    Render): verificar A favor/Contra de un vistazo.
  - **Fallback fantasma ELIMINADO**: sin trayectorias calculadas, Vista previa/Render/Exportar
    avisan ("configura y pulsa Calcular") en vez de inventar una trayectoria con el formulario
    sobre todo el diseño — eso hacía creer a Jose que "el diseño cambiaba".
  - **Ojo con retroalimentación real**: toast al incluir/excluir, fila tachada+punteada, y la
    vista previa se ACTUALIZA en vivo (`refreshPrev`). ⚠️ **Fix del "no vuelve"**: decidir el
    re-preview por la INTENCIÓN del usuario (`prevOn`) y no por `!!cncPrev` — al excluir la
    única trayectoria la vista moría y `!!cncPrev` mentía. Lección: estado momentáneo ≠
    intención; los toggles que otros eventos pueden vaciar necesitan bandera propia.
  - **Renombrar trayectorias con doble clic** en la fila (Enter/Escape/blur; sincroniza el
    campo Nombre del formulario). Panel de Corte reordenado: formulario → Calcular →
    Trayectorias → Vista previa/Render AL FINAL.
  - **Semántica ojo vs Vista previa** (explicada a Jose): el OJO decide qué entra al CORTE
    (afecta el .tap); VISTA PREVIA solo enciende/apaga la capa visual (no afecta el export).
    (24-nov-2026: el ojo confundía a un probador y se cambió por una CASILLA; ver
    `.claude/rules/interfaz-web.md`.)

- **I. Seguridad y flujo fino del panel de Corte — ✅ COMMIT caa5092 (22-jul, cierre)**:
  - **Alerta de TRASPASO**: si `start+depth > grosor`, modal de confirmación antes de Calcular
    con los mm de exceso y aviso de cama de sacrificio (atravesar 0.2–0.5 es práctica normal —
    el diálogo confirma, no bloquea). Modal propio `askConfirm()`: **`confirm()` nativo no es
    fiable dentro de pywebview**.
  - **Calcular guarda y CIERRA** (como Aspire): crear NO deja la trayectoria seleccionada; el
    formulario queda limpio para encadenar. "Recalcular" solo al abrir una fila (esa sí
    permanece seleccionada). Jose tropezó con el comportamiento anterior.
  - **Fix nombres duplicados "Perfil 1"**: el campo Nombre ESPEJA la selección y se limpia al
    deseleccionar/cambiar de op (antes heredaba el texto viejo a las nuevas).
  - **Fix renombrar muerto**: clic de fila con retardo 230ms que el dblclick cancela — cada
    clic reconstruía la lista y el dblclick aterrizaba en un nodo DESECHADO (editor fantasma).
    Lección: clic-que-re-renderiza + doble-clic = conflicto; retardo cancelable o no rebuildear.
  - **"Guardar G-code (.tap)" como paso final del panel** (equivale al Save Toolpaths de
    Aspire; el botón de la barra superior sigue). Vista previa/Render movidos al final;
    orden del panel: formulario → Calcular → Trayectorias → vista → guardar.
  - **Trayectorias y flechas en MAGENTA de marca** (cvar --accent, tema-aware; Render conserva
    tonos madera). Brecha restante vs Save Toolpaths de Aspire: export automático POR FRESA
    cuando hay mezcladas (hoy: aviso + apagar ojos a mano) — ofrecido, sin construir.
  - **Preguntas de Jose respondidas** (dejar explicado, volverá a salir): clic en fila =
    abrir para editar (2º clic cierra); ojo = qué entra al CORTE vs Vista previa = solo
    pantalla; la INVERSIÓN de sentido fuera/dentro es física (climb = material a la
    izquierda del avance → geometría espejeada, sentido espejeado; Aspire igual).

- **UI general de Design Studio (commit 4035c5e, misma noche)**: tema **CLARO por default y
  RECORDADO entre sesiones** (clave `theme` en cnc_config.json — localStorage no es fiable en
  pywebview); toggle de tema al FINAL del riel izquierdo; botón de tamaño de hoja movido junto
  al zoom en **píldora propia** con icono de hoja con línea de cota, ambas dentro de un
  **contenedor flex** (lección: dos elementos que deben ir juntos se agrupan en un contenedor,
  no se posicionan por separado con coordenadas a ojo — así se desalinearon dos veces).
  - **Añadidos 22-jul tarde (pedidos de Jose tras comparar con Aspire)**:
    · **Pasadas EDITABLES** (como "Edit Passes"): el campo se auto-calcula pero al escribir N
      se reparte la profundidad en N pasadas parejas (`effPassDepth` ajusta el pass_depth del
      snapshot; `passAuto` distingue auto vs forzado).
    · **Última pasada separada** ("Do Separate Last Pass"): checkbox en Perfil con "Deja" (mm
      de cáscara) e "Invertir dir.". En el motor: `make_toolpaths(last_pass, last_rev)` genera
      por pieza anillos de DESBASTE (offset + cáscara, todas las pasadas) y de ACABADO (medida
      exacta, UNA pasada a fondo, opcionalmente en dirección contraria). Anillos como tuplas
      `(pts, es_acabado)` — `_rpts`/`_rfin`; el preview los aplana. El acabado también respeta
      puentes. Verificado: offsets 103.5/103, orientación opuesta, 4+1 pasadas, banderas por
      pieza en la "O".
    · Puentes DESMARCADOS por default (como Aspire); Trayectorias al FINAL del panel con
      **drag & drop** para el orden de corte (se quitaron ↑↓); **cero emojis/símbolos: todo
      icono es SVG** (ojo/basura/engrane/pluma/flechas del jog/cierres de modal…).

- **G. Fresas por material (Tool Database estilo Aspire) — ✅ CONSTRUIDA 22-jul-2026** (Jose pidió
  el careo contra la Tool Database de Aspire V12; el defecto era que el material iba PEGADO EN EL
  NOMBRE de la fresa — tu fresa de 6 mm existía 4 veces). Esquema v2 de `cnc_config.json`:
  - **Fresa = GEOMETRÍA** (nombre, Ø, notas) **+ `cut{}` = datos de corte POR MATERIAL**
    (pasada/avance/bajada/RPM/paso). **`materials[]`** gestionable (modal ⚙ junto al selector)
    y **`material.type`** = material ACTIVO, elegido en el panel Material: las fresas usan su
    juego de datos automáticamente. `flatTool()` en la UI aplana geometría+datos del material
    activo — el motor de G-code sigue recibiendo el dict plano de siempre (no se tocó).
  - **Migración v1→v2 automática** en `cnc_get()` (agrupa por nombre-base sin sufijo de material
    + Ø; palabra clave del nombre → material; sin palabra clave → sus datos van a TODOS).
    Verificada sobre la config real de Jose: 5 fresas → 2. El archivo se reescribe migrado.
  - **Snapshot al Calcular**: la trayectoria congela la fresa aplanada (`t.tool`); editar la
    biblioteca o cambiar material activo NO altera trayectorias ya calculadas (como Aspire).
  - **Exportar/Importar biblioteca** (materiales+fresas, JSON `antike-tools`): botones en el
    modal de fresas; Api `tools_export/tools_import` + rutas `/api/tools_export|tools_import`.
    Importar REEMPLAZA. "→ todos" copia los datos de corte del material activo a los demás.
  - Al borrar un material se PODAN los datos de corte huérfanos de todas las fresas.
  - No construido a propósito: tipos de herramienta (V-bit/ball nose — hasta V-carve), número
    de herramienta (RichAuto sin ATC), chip load, grupos en árbol (<15 fresas).
  - **Biblioteca default investigada (22-jul)**: 5 fresas comunes × 4 materiales, con números de
    ARRANQUE basados en tablas de chip load (feed = RPM × filos × chip load) y práctica publicada
    — 6mm 1 filo O-flute (acrílico/PVC: 1 filo expulsa la viruta caliente y no derrite), 6mm
    2 filos espiral (MDF/maderas), 6mm compresión (triplay/melamina, borde limpio ambas caras;
    1ª pasada > ~1×Ø), 3.175mm 1F y 2F (detalle). PVC espumado: rápido y con menos RPM (14-15k)
    para no derretir (publicado 3.5–6.5 m/min; defaults conservadores). Reglas de sanidad
    verificadas (acr 1F > 2F en avance). Fuentes: toolstoday.com/learn/understanding-cnc-feeds-
    and-speeds, workshopcalc.com/reference/cnc-feeds-speeds-chart, woodweb.com (PVC foam),
    cncrouterstore.ca chip load chart. ⚠️ Son puntos de partida — se afinan cortando.
  - **Re-validada contra tablas publicadas el 24-jul** (workshopcalc, toolgrit, shopbot):
    todos los presets caen dentro/centro de los rangos. Dos ajustes aplicados (código Y
    config): 6mm-2F/mdf avance 3600→4000 (más mordida, contra la rebaba por frotado) y
    3.175-2F/madera 1800→1600 (entrar al rango; las 1/8" son frágiles). ⚠️ Las tablas
    difieren entre sí hasta 50% — el árbitro es el borde cortado.

- **R. Vista 3D estilo Aspire — ✅ COMMITS 853cb8f (R1+R2) y 9506659 (R3+R4), 23-jul-2026**
  (Jose validó R1/R2 en pantalla; R3/R4 verificadas en node con el .tap real de chalecos).
  Botón "3D" junto a Vista previa/Render en el paso CNC. **Decisión clave: la simulación NO
  reimplementa la lógica de corte — parsea el MISMO .tap que se exporta** (un .tap por
  trayectoria vía Api `cnc_tap_text`, así cada una usa su fresa; solo hay G00/G01, límite
  RichAuto), sobre un **mapa de alturas** (rejilla adaptativa, tope ~1.4M celdas): pasadas,
  rampas y puentes salen solos del G-code. Three.js r128 **local** (`three.bundle.js`, UMD,
  en el .spec y con ruta propia en studio_server). La textura va **horneada en color por
  vértice** (la rejilla es más fina que un pixel — sin archivos de imagen): MDF/madera/
  acrílico/PVC/liso + modos Material/Relleno/Por trayectoria (el mapa guarda el "dueño" de
  cada celda), pasante = cama gris, **bajo la cama = rojo**. "Guardar imagen…" (Api
  `save_png`). Animación con fresa a escala, pausa y 4 velocidades; normales por gradiente
  del mapa (NO `computeVertexNormals`: por filas para `updateRange` parcial por frame; el
  frame final debe anular el rango y subir completo). **Gotchas de la sesión:** (1) la regla
  CSS `.simsheet` perdía contra `.sheet` por orden en el archivo → selector `.sheet.simsheet`;
  (2) probar las funciones de la UI extrayéndolas del HTML con node (`node --check` + eval
  por marcadores) — permitió verificar sim/malla/colores/anim sin abrir la app.

- **R2. Vista 3D — pulido tras el uso real de Jose (23-jul, commits d46dd35 + 5c89b7b + 94868b2)**:
  - **Materiales de verdad**: Triplay SEPARADO del MDF; las paredes casi verticales las pinta un
    **injerto de shader** (Lambert `onBeforeCompile`, uniforms por look) según la ALTURA real —
    chapas alternadas ~1.6mm en triplay, cosa imposible con colores por vértice (interpolan en
    degradado). Fondos por `matFloor()` a la chapa de su profundidad.
  - **La hoja = área de trabajo configurada** (se amplía solo si una trayectoria se sale).
  - **Doble clic quita el sobrante** (delete-waste de Aspire): inundación 4-vecinos, y la cámara
    se reenfoca a lo que queda. ⚠️ **Gotcha que cazó la prueba**: la inundación cruzaba POR
    ENCIMA de los puentes (3mm de material sí conectan) y se comía la pieza → la conexión solo
    cuenta a través de material de **más de medio grosor** (los puentes "se rompen", como en la
    vida). El pedazo quitado deja de tener GEOMETRÍA (índices reconstruibles `simTopIndex`/
    `simBotIndex`) — se ve la cuadrícula, no un bloque a nivel de cama.
  - **Pasante visible arriba y abajo**: el fondo del canal que atraviesa no se dibuja (cuadrícula
    a través) y la hoja tiene cara de abajo propia (rejilla paso 2, MeshBasic) con agujeros donde
    perforó. **Sobrecorte ≤0.5mm (SIM_OVER) = pasante normal de taller, SIN rojo**; el rojo es
    solo para mordidas mayores (la 1ª versión pintaba rojo el margen intencional y Jose preguntó
    por "la línea roja"). La animación arranca viendo la hoja sólida (0%) ~700ms.
- **S2. Integración con la máquina real — ✅ COMMIT db5f141 (24-jul, PROBADO en el A11E)**:
  Marchas opción B: `material.gears` = RPM reales de S1-S8; `gear_for()` elige la más cercana
  a las RPM del preset → `M03 S<marcha>`; la vista previa anuncia la marcha; editor en
  "Configuración avanzada" (junto con el cero de Z — Jose pidió sacar ambos de la vista
  diaria). Presets ajustados vs tablas publicadas (6mm-2F/mdf 4000 · 1/8-2F/mad 1600).
  Fix cnc_set (la lista blanca del material PERDÍA spinup/gears al guardar). El encabezado
  del .tap anota marcha y cero de Z. UI: Render eliminado (obsoleto por la Vista 3D),
  Exportar superior oculto en modo CNC, Importar junto a Abrir, gestionar-fresas como ícono.
  `auditar_gcode.py` en el repo (104 checks). Config del handle que quedó: **F Read=Read F,
  S Read=Read S (funciona porque el archivo ya manda marcha, no RPM), Spindle delay nativo
  10-12s** (el mecanismo bueno para la espera; el del archivo queda de respaldo — Jose lo
  pondrá en 0 para no duplicar).
- **S. Espera de arranque del husillo — construida 24-jul (hoy respaldo del delay nativo)**:
  Jose reportó que la máquina corta antes de que el husillo llegue a sus RPM. Campo **"Husillo"
  (segundos, default 5, 0=off)** en Material (id `matSpin`, llave `spinup` en material). Tras el
  M03 se emite **cinturón y tirantes**: `G04 P<seg>` **y** 4mm de viaje EN EL AIRE (sobre Z
  segura) a F calculada para durar exactamente la espera (240/seg) — porque la unidad del P de
  G04 **varía por controlador** (seg vs ms) y no hay doc del A11E; el respaldo aéreo funciona en
  cualquier control con "Read F". Al probar en máquina: si tras M03 espera ~10s, su G04 es de
  segundos (bajar el campo a 2-3s); si ~5s, el G04 fue inocuo y manda el respiro.

- **T. Perfil Izquierda/Derecha — ✅ COMMIT e3df84d (24-jul)**: para trazos ABIERTOS con lado
  definido (recortar un borde a medida exacta): `_offset_side()` con `offset_curve` de shapely
  (+izq/−der de la DIRECCIÓN DE DIBUJO — las flechas de la preview la enseñan; extremos sin
  extender; dirección conservada). El segmentado de lado se adapta a la selección (cerrados →
  Fuera/Dentro/Sobre · abiertos → Sobre/Izq/Der · mezcla → los 5; mismo criterio de cierre que
  el motor, ≤0.05mm). También: Alinear con etiqueta viva y 1 unidad → fuerza hoja de trabajo;
  botones renombrados (Ver/esconder trayectorias · Ver render); Material mínimo con Config
  avanzada (Z0, Z seg., husillo, 0,0, marchas) — commits afb5ced + e3df84d.

- **R3. Vista 3D — saga de la COSTURA y el sobrante físico (24-jul noche, commit a926588)**:
  render híbrido (rejilla fina solo en la zona de corte + placa para el resto de la hoja).
  **Lecciones duras, en orden**: (1) dos mallas con textura por vértice NUNCA casan (la piel
  depende de la densidad) → UNA CanvasTexture por look, espejo-repetible, mapeada por
  coordenadas de MUNDO, con interruptor `aCut` por vértice en el shader (intacto=textura,
  cortado=color plano); (2) costura entre mallas = unión en T (rendijas) → traslape coplanar;
  (3) ⚠️ **polygonOffset DESCARTADO DOS VECES**: factor explota con la pendiente (rasante) y
  units con la distancia (hoja de 2.4m) — ambas veces asomó el canto como "cinta perimetral".
  La solución final: traslape coplanar SIN sesgo con MATERIAL COMPARTIDO — el z-fight existe
  pero pinta pixeles idénticos = invisible; (4) la hoja DEFINE el material: celdas fuera de
  ella no se dibujan (trayectoria que se sale corta aire — se ve el canal morir en el borde);
  (5) quitar sobrante EN CASCADA (pedazos unidos vía placa se van juntos; la orilla real no
  conecta: piezas a sangre viven) + **barrido de material delgado huérfano** (el piso de un
  grabado profundo pertenece a su pieza; el umbral de medio-grosor solo no distingue puente
  de fondo de grabado — la distinción correcta es "¿a qué queda conectado?"). Bugs 1-5
  cazados POR JOSE probando en vivo, ronda por ronda. También: "Ver trayectorias" rápido
  (paralelo + JSON a dieta — el puente pywebview cobra POR VIAJE y por KB) y materiales
  Phong con paleta de referencias (madera: la veta simple ganó a los anillos "realistas").

## Auditoría pre-corte (`auditar_gcode.py`, en el repo — 24-jul-2026)
**Correrla antes de cualquier corte real si se tocó el motor**: `/opt/homebrew/bin/python3
auditar_gcode.py` (necesita shapely → el Python de Homebrew). **79 verificaciones, 0 fallas**:
gramática estricta línea por línea, física de seguridad (nada de G00 con fresa enterrada, F solo
feed/plunge bajo la Z segura, Z jamás más honda que lo pedido, pasadas ≤ pass_depth), geometría
exacta a ±0.01mm (compensación fuera/dentro/holgura, cajeado, taladro, anidado hueco-primero),
ambos ceros de Z, multi-trabajo, rechazo de fresas mezcladas, y el bloque de espera de husillo.
Además se midió sobre la simulación 3D (mismo .tap): pieza 100.09mm, kerf 5.96≈6, 3 puentes.
⚠️ El primer hallazgo de la batería fue un bug DEL PROPIO TEST (medía "el primer cuarto de
movimientos" y el hueco tiene 5 puntos vs 69 del exterior) — verificar el orden por ANILLOS.

## Configuración del handle A11E (rutas EXACTAS del manual oficial, leído 24-jul-2026)
- **Velocidades del archivo**: `MENU → AUTO PRO SETUP → G Code Setup` → **`F Read = Read F`**
  y **`S Read = Read S`** (fábrica: `Ign F`/`Ign S` — ignora TODAS las F/S del G-code y usa su
  "Work Speed"; así trabajó siempre con Aspire sin saberlo).
- **Espera de husillo NATIVA**: `MENU → MACHINE SETUP → Spindle Setup → Spindle delay`, en
  **MILISEGUNDOS** (incluye arranque y paro). Jose la necesita ~**10000** (su husillo tarda en
  llegar a RPM). Este es EL mecanismo correcto — el G04 del archivo resultó inocuo en su
  A11E y los movimientos lentos en aire dependen de Read F. **Historia**: la espera de 5→10s
  del archivo "no hacía ninguna diferencia" porque el handle ignoraba ambos mecanismos; los
  ~4s que sí esperaba eran el Spindle delay de fábrica (4000ms).
- **Marchas del A11E — LA FÍSICA CONTRADIJO AL MENÚ (24-jul, lección importante)**: el menú
  `MACHINE SETUP → Spindle Setup → Spindle speed` listaba "1..8 desde 18000 bajando 1000",
  pero al PROBAR girando el husillo: **S1 = PARADO** (combinación muerta del cableado
  Count 3) y **S2→S8 ASCENDENTE**. La tabla leída del menú habría mandado el MDF a S1 =
  fresa hundiéndose SIN GIRAR. **Tabla en la app (PROVISIONAL, pendiente de leer los Hz del
  variador por marcha): [100(S1 bloqueada), 12000, 13000, 14000, 15000, 16000, 17000, 18000]**
  → mdf S8, acr S6, pvc S4. Para calibrarla exacta: husillo a mano, recorrer S2..S8 leyendo
  el display del variador (RPM = Hz × 60) y capturar en "Marchas…". `SpdlCnt = 3` (no tocar).
  La app la trae capturada (material.gears) y elige marcha por CERCANÍA de RPM del preset:
  mdf 18000→S1, acr 16000→S3, pvc 14000→S5. ⚠️ **Tabla del handle y modal "Marchas…" de la
  app son PAREJA ESPEJO**: si alguien cambia una, actualizar la otra el mismo día (la app
  compara contra SU copia — desincronizadas mandan marcha equivocada sin aviso). Jose preguntó
  si convenía cambiar las velocidades del handle: NO — el rango 11k-18k cubre los presets;
  la afinación de cortes va por avance/pasada en "Fresas…", no por reprogramar marchas. El "Spindle state con flechas" es el mapa de
  señales por marcha — no tocar. Con la tabla en el archivo, `S Read = Read S` SÍ funciona
  (el problema anterior era mandar RPM como S; ver siguiente punto, que queda como HISTORIA).
- ⚠️ (HISTORIA — resuelto con la tabla de marchas) **`S Read` en `Ign S`** (verificado 24-jul en la
  máquina real): la máquina es **multi-speed por MARCHAS S1–S9** (se cambian desde el handle;
  encendido manual con ON/OFF funciona). Con `Read S`, el `S18000` del archivo (RPM) se
  interpreta como MARCHA — "marcha 18000" no existe → **el husillo nunca arranca**. Con
  `Ign S`, M03 enciende con la marcha puesta en el handle (el flujo de siempre de Jose).
  Combinación correcta del A11E: **`F Read = Read F` + `S Read = Ign S`** +
  `Spindle delay = 10000` ms. Opción futura si Jose la pide: emitir `S1`–`S9` (marcha por
  material/trayectoria) en vez de RPM — requiere conocer las RPM de cada marcha (variador).
- El manual completo quedó descargable: forsuncnc.com → DSP-A11-User's-Manual.pdf (86 págs;
  G Code Setup en pág 22 del PDF, Spindle Setup en pág 18).

## 🎉 PRIMER CORTE REAL — HECHO (24-jul-2026, reportado por Jose)
- **A MEDIDA** ✓ (la pieza midió lo que pedía el diseño — kerf compensado bien).
- **Orientación CORRECTA** ✓ — la duda del eje Y queda CERRADA para la CNC (la del plotter
  sigue abierta, es hardware aparte).
- **Husillo**: arrancó a las RPM esperadas (marchas OK) y esperó ~10 s antes de bajar —
  **eso es el Spindle delay del handle (10000 ms) que nosotros configuramos**, no un misterio:
  se ajusta en MACHINE SETUP → Spindle Setup. Recordar a Jose poner el campo "Husillo" de la
  app en 0 para no duplicar esperas.
- **MDF 3mm: la REBABA persiste en ambos lados** pese al preset de 4000 → sigue la prueba A/B
  pendiente: cambiar cortador (downcut), velocidades, etc.
- Puentes/rampas/profundidad: todo en orden; la Vista 3D anticipó bien.

**Protocolo del primer corte real (ya ejecutado; útil para máquinas nuevas):** archivo chico (cuadrado 100×100), primero
"corte en aire" (Z cero muy por encima del material) para verificar recorrido y orientación del
eje Y (misma duda pendiente que el plotter — [[design-studio]] "Eje Y"), luego corte real en
material de sacrificio. Revisar en el handle: G Code Setup → F Read = "Read F".

## Alcance acordado con Jose (22-jul-2026)
- **Trayectorias: Perfil + Vaciado (pocket) + Taladrado.** V-carve queda FUERA por ahora
  (Fase E opcional futura) → se quita la parte matemáticamente más dura del proyecto.
- **Husillo:** Jose no sabe cómo se controla (en Aspire ponía las RPM en la herramienta y ya).
  → Emitir `M03 S<rpm>` en el G-code y **verificar en la máquina** si obedece la S (recordar la
  trampa `S Read = Ign` del handle). Si no obedece, no rompe nada: el S se ignora y listo.
- **Materiales para presets de fresas:** MDF/triplay, acrílico, PVC espumado/coroplast y madera
  sólida. → La biblioteca de herramientas debe nacer con presets por material.

## Pregunta resuelta (24-jul-2026)
- ~~Modelo exacto del controlador~~ → **RichAuto (AutoNow) A11E**, confirmado por Jose en el
  handle. Toda la familia A1X comparte la lista de G-code del manual, así que nada de lo
  construido cambia; útil para buscar manuales/firmware específicos (p.ej. la unidad del P
  en G04, aún sin documentar).

Relacionado: [[design-studio]] (donde vivirá la función), [[estado]] (motor compartido).
