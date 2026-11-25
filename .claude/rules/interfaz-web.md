---
paths:
  - studio_ui.html
  - three.bundle.js
  - geo_ops.py
  - web/test_*.mjs
  - estacion.html
---
# Interfaz web (`studio_ui.html`)

Verificado contra el código el 18-nov-2026 (movido del `CLAUDE.md`). Preferencias de Jose:
[[preferencias-interfaz-jose]]. Cómo probarla: [[como-verificar-la-interfaz]].

## Plotter en el navegador

- ⚠️ **Plotter en el navegador: en ANDROID no usar `navigator.serial`.** Existe, pero solo ve
  puertos **Bluetooth**: el plotter nunca aparecería, sin error. Allá el cable va por **WebUSB**
  con un driver FTDI propio (`serieUsb`/`abrirFtdi` en `<script id="motor-plotter">`) disfrazado
  de puerto Web Serial, y lo elige `serieDelNavegador()`. En computadora es al revés: WebUSB no
  sirve (el driver del sistema tiene tomado el chip). Solo FTDI; CH340/Prolific/CP210x no están.
  Probado en el Galaxy de Jose (Android 16). Prueba: `node web/test_plotter_web.mjs`.

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
- ⚠️ **Zoom: 100 % = TAMAÑO REAL** (`zoomPct()`, `setZoomPct()`). `view.scale` son píxeles por mm;
  el % es `view.scale / (96/25.4 × zCal)`. Antes era `view.scale×100`: "100 %" mostraba la pieza a
  ~¼ de su tamaño (lo reportó Jose, 24-nov-2026). `zCal` se mide con una regla (Archivo →
  Calibrar tamaño real, `calibrarZoom()`) y vive en `localStorage` (`ds_zcal`) porque es de la
  PANTALLA, no de la cuenta. Tocar el % abre una cajita (`#zoomInp`); mientras está abierta,
  `draw()` no pisa el texto (`zEdit`) — la misma trampa que el renombrado de cortes.
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
- **Corte de la CNC: TRES pasos en una barra — `1 Material`, `2 Cortes`, `3 Revisar`** (`#cncSteps`,
  `pintarPasos()`, `irPaso(k)`; aprobado por Jose, 12-nov-2026). La barra vive FUERA de los paneles
  (se ve también en Material), los tres son botones con su resumen, y cada pantalla tiene abajo
  su botón de regreso y el del siguiente paso (`.navrow`). Material es el panel `#paneCncCfg`;
  Cortes y Revisar son vistas de `#paneCncCut` (`pintarVista()`: LISTA `#cutList`, FORMULARIO
  `#cutForm`/`formOpen`, REVISAR `#cutRev`/`revOpen`). Al entrar a Corte se abre en Cortes.
  ⚠️ **`.stp` lleva `flex:none`**: `.inspect` es una columna flex con scroll y, sin eso, con
  contenido largo la barra se APLASTA y queda tapada (lo destapó la prueba de dos fresas).
  ⚠️ **`irPaso(0)` apaga `revOpen`**: si no, el botón magenta de arriba guardaría desde Material.
  **Pantalla de Material**: "Este trabajo" (material, grosor, cero de Z) y "Tu taller" (Fresas,
  Materiales, Máquina: los botones `#btnTools`, `#btnMats`, `#btnAdv`). `#toolPick` ("fresa
  habitual") sigue en el HTML, **oculto**: guarda la última fresa usada y `#tpTool` es su espejo.
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
- **Los recorridos se encienden y apagan con «Recorridos», junto al zoom** (`#recPill`/`#btnRec`,
  opción A de Jose, 24-nov-2026): solo se ve en el paso Corte de la CNC (`syncRec()`, que corre tras
  cada redibujo y en `setSideMode`, porque pasar a Diseño no redibuja). Reemplazó al "Ver recorrido"
  de Revisar (`#revPrev`, ahora oculto: no repetir botones). "Ver en 3D" sigue SOLO en Revisar
  (`#revSim`). Los de antes (`#btnTpPrev`, `#btnSim3d`) siguen en el HTML, **ocultos**, porque tienen
  la lógica y los visibles los pulsan. ⚠️ **Calcular enciende los recorridos solo**, y al abrir un
  corte para editarlo también (hace falta para poner puentes a mano).
- **El clic en el lienzo del paso Corte toma FIGURAS, aunque tengan un recorrido encima**; un corte
  se abre SOLO desde su fila (opción C de Jose, 24-nov-2026). Antes el recorrido ganaba el clic y
  tocar un barreno abría la edición del cajeado. Ya no existen `hitToolpath`/`selectTpFromCanvas`.
- **Cada corte lleva una CASILLA "se corta"** (`.tpchk`, junto a la manija ⋮⋮, opción B de Jose,
  24-nov-2026) = `t.enabled`, si sale en el G-code. Apagada, la fila se tacha y dice "No se corta".
  Era un OJO y parecía "ocultar la vista" (lo reportó un probador). No volver a un ojo. **El botón dice lo que hace**: en Cortes "Revisar",
  en Revisar "Guardar G-code" — no "Revisar y guardar" para un paso que solo revisa.
- **Revisar es el único camino para guardar** (`abrirRev()` → `guardarRev()` → `bajarRev()`). Antes
  de bajar el archivo se ofrece **cambiarle el nombre** (uno por fresa si son varios; `nombreTap()`
  lo limpia de lo que un sistema de archivos no acepta, y vacío = el propuesto). Vuelve a pedir los
  avisos al entrar y **`revDatos` se anula al empezar cada revisión**: nunca se guarda con el
  resumen de una anterior. Hace dos cosas que antes no existían: **un archivo por fresa**
  (`gruposPorFresa()`; el RichAuto no cambia de herramienta solo) y el **aviso de orden**
  (`ordenMalo()`: un perfil que atraviesa la pieza antes que un cajeado, un taladro o un perfil
  por dentro de esa misma pieza) con "Ordenar" (`ordenarCortes()`). `saveTap()`/`tapResumen()`
  siguen en el archivo pero ya nada visible los llama.
- **La fresa se elige dentro del formulario** (`#tpTool`), que es un **espejo** de `#toolPick`
  (Configuración): al cambiarlo PULSA aquel. No dupliques la lógica de `tool_sel`/`resetPasses`.
- ⚠️ **`paintTps()` NO rehace la lista mientras se renombra una fila** (cajita `.tpnm-edit` con el
  foco): borrarla tiraba el foco al `<body>` y las letras siguientes caían al lienzo como ATAJOS
  (cambiaban la herramienta, el nombre quedaba cortado). Pasaba cuando la vista previa llegaba a
  media escritura — en Railway tarda segundos; en la Mac no se reproduce sin retrasar la respuesta
  (Playwright: `page.route` con 3 s). `done()` marca `_cerrada` y repinta. (24-nov-2026)
- **Doble clic en una figura de un grupo = entrar al grupo** (queda ella sola seleccionada); en un
  texto sigue abriendo su edición. Un SVG importado entra como UN grupo. (24-nov-2026)
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
  **deshacer/rehacer se mudan** de la barra a `#undoFloat` — salvo en el paso Corte de la CNC
  (`body.corteCnc`), donde ese lugar es de «Recorridos» y no se edita nada (bloque "barraMovil": los MISMOS
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

### Color, descarte, alivios y "Mis proyectos" (12-nov-2026)

- **Color por figura = un mapa `colores[uid]`** (`studio_ui.html`), como los candados. ⚠️ **No lo
  conviertas en un arreglo paralelo a `doc.paths`**: va por uid justamente para que mover, borrar
  o reordenar figuras no tenga que acordarse de él. Sin entrada = sin color. Viaja en el
  historial (`snapshot().cols`), en el proyecto (`objects[i].col`) y al copiar/pegar/duplicar; al
  abrir un archivo llega de `load_vector()` (`col`, vía `_color_hex()`: negro y casi-blanco cuentan
  como "sin color"). **El color NO cambia el corte**: solo decide qué se manda.
- **Corte por color (plotter)**: `colOff` = colores apagados; `idxCorte()` da los índices que sí
  se cortan y **`hpglPayload()` lo aplica solo cuando no le pasan índices**. Con todo apagado el
  botón de enviar avisa y no manda. Solo existe en modo Plotter.
- **Sin selección NO se pinta nada**: el color exige selección explícita (`mode()!=='all'`), para
  que un clic distraído no coloree el diseño entero.
- **Descarte** (`geo_ops.weed_op`): recuadro + tiras horizontales, como FIGURAS normales del
  diseño (un grupo). Las tiras se recortan contra todas las figuras con 0.6 mm de respiro. Sin
  selección rodea lo que se va a cortar y, si es de un solo color, nace de ese color.
- **Alivio de esquinas** (`geo_ops.dogbone_op`, sección "Ensamble", solo en CNC): círculo sobre la
  bisectriz a un radio del vértice; "hueco" alivia las esquinas salientes (lo agranda), "pieza" las
  entrantes (le quita). ⚠️ El radio es el de la fresa **+ 0.1 mm**: con el exacto, el recorrido de
  la fresa en esa esquina se reduce a un punto y desaparece. Solo esquinas de 30° a 150°.
- **"Mis proyectos"**: `.dstudio` en `<carpeta de la cuenta>/proyectos/` (`project_*` en
  `studio_backend.py`). ⚠️ **Se abre y se borra SOLO por el id que puso el servidor**
  (`p` + 12 hex, validado con `_PROY_ID`), nunca por nombre ni ruta. La prueba sin cuenta no
  guarda. `projId` = el abierto; Cmd/Ctrl+S guarda ahí (pide nombre la primera vez); la descarga
  del `.dstudio` sigue en Archivo.
  Cada proyecto lleva su **miniatura** (`thumb`): la dibuja el navegador al guardar (`miniatura()`,
  mismas cuentas que `effPts`) y el servidor SOLO acepta un PNG incrustado y chico (`_mini_ok`),
  porque va directo al `src` de una imagen. Los guardados sin ella se dibujan al vuelo en la lista.
- **PDF se abre con el lector de `.ai`** (`AIParser`, PyMuPDF). **EPS y CDR NO**: necesitan
  programas del sistema (Ghostscript, libcdr) que no se pudieron probar en la Mac, y de CDR no hay
  archivo de muestra. No los prometas sin probarlos en la imagen de Railway.

### Notas, capas, elegir por color y placa (24-nov-2026, reporte de prueba)

- **NOTA = figura que se VE y NUNCA se corta** (`notas[uid]`, punteada gris en el lienzo). Nacen de
  los `<text>` de un SVG (el servidor los dibuja con una fuente sencilla, `_fuente_nota()`) o del
  clic derecho «Convertir en nota». ⚠️ **Todo lo que corta se salta las notas**: `tpResolve` y
  `sinNotas()` (CNC), `hpglPayload` (plotter, y con él la estación). Si agregas otro camino que
  mande figuras a una máquina, fíltralas ahí también.
- **CAPA** (`capas[uid]`): nombre de la capa del archivo. `notas` y `capas` van por uid y viajan
  por los MISMOS sitios que `colores` (historial, copiar/pegar, duplicar, proyecto `objects[i].nota/
  .capa`, importar) con `metaCopia()`/`metaDesde()`.
- **Cortes desde capas** (`recetaCapa()`, caja `#capaBox` en Cortes): perfil/contorno/corte (+ fuera,
  dentro, sobre), cajeado/vaciado/pocket, taladro/barreno/drill; **un número = profundidad en mm**;
  sin número, el grosor. Se PROPONE con un botón (el nombre de una capa puede no ser una orden) y
  crea los cortes por el mismo camino del usuario (`nuevaTp` → `_calcApply`). «Ahora no» la oculta
  hasta abrir otro diseño (`capasOcultas`).
- **Elegir por color**: fichas `#colPick` en Cortes (solo con 2+ colores) y «Seleccionar todo este
  color» en el clic derecho (`selMismoColor()`). Un color del archivo que no es de la lista de
  viniles se NOMBRA por el vinil más parecido (`nombreCol()`): nunca enseñar «#ff0000».
- **Placa del trabajo** (`material.sheet` = [ancho, alto] o null = la mesa; campos `#matSW/#matSH`
  en Material, `placa()`): se dibuja desde el origen, la vista 3D solo pone material ahí, y el
  servidor avisa «Se sale de la placa». ⚠️ Con UN solo campo lleno no se guarda nada y `paintCnc`
  no pisa los campos mientras se escribe: al pasar de Ancho a Alto la respuesta borraba el ancho.

### Mosaico (24-nov-2026, opciones A+A de Jose: https://claude.ai/artifact/SAoBB7awvBJg2wecJagkUL)

- **Motor**: `geo_ops.mosaic_op` (ruta `/api/mosaic`, que además dibuja la etiqueta «fila-columna»
  de cada tramo con `_textos_a_notas`). Cuadrícula IGUAL con lo mínimo para caber en la placa
  (placa − 2·borde − 2·fondo de unión); uniones ALTERNADAS y solo ENTERAS dentro de la pieza;
  esquinas redondeadas a Ø/2 + 0.1 (⚠️ salvo en los cruces de costuras: ahí quedaba un agujero);
  `holgura` total entre piezas; tope 60 tramos. Medido: tramos sin encimarse, holgura exacta, y en
  el perfil por fuera el centro de la fresa va a 3.00 ± 0.01 mm de la pieza en TODO el recorrido.
- **Pantalla**: sección «Mosaico» dentro de `#ensWrap` (solo CNC, paso Diseño); usa la fresa de
  Ensamble (`#dbDia`). La vista previa (`mosPrev`, punteado de acento, `pintarMosaico()` en la
  envoltura de `draw`) SOLO se enciende al tocar la sección (`mosOn`) y se apaga al partir, al
  cambiar de paso y al abrir otro diseño; `mosFirma` evita pedirla si nada cambió.
- **Al partir**: entra lo CERRADO de la selección sin notas (nada = todo); cada tramo queda
  separado en su lugar (`col × sep`, `fila × sep`, sep = fondo + 40) como un grupo con su etiqueta
  como NOTA. Las notas y trazos abiertos de la pieza viajan con el tramo donde cae su centro
  (`enTramo`, par-impar), y la etiqueta los esquiva (`avoid`). Los cortes (tpaths) de la pieza
  vieja quedan sin figuras: hay que asignarlos de nuevo. Un solo deshacer regresa la pieza.
- ⚠️ **Cada figura de un tramo recuerda la fresa con que se partió** (`fresaMos[uid]`, viaja como
  `notas`/`capas`; en el proyecto `objects[i].mf`). `avisosMosaico()` avisa si un corte usa una fresa
  MÁS GRUESA: no entra en los rincones redondeados y las uniones no encajan. El servidor no lo puede
  saber: el aviso se une en la interfaz (`conAvisos()`, que COPIA la respuesta para no ensuciar la
  memoria de recorridos) en la vista previa y en Revisar.
- **Atajo**: el aviso «Se sale de la placa/mesa» trae «Partir en mosaico» (caja `#tpWarn` y fila de
  Revisar, `data-mos`) → `irAMosaico()`: paso Diseño, figuras de ESOS cortes (`cortesFuera`)
  elegidas, sección abierta y vista previa encendida. ⚠️ Al apagar Revisar hay que llamar
  `pintarVista()`, o el botón de arriba se queda diciendo «Guardar G-code» en Diseño.
- **Fuera a propósito**: el solape/media madera (exige voltear la placa).

### Fuentes en la web

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

### Estación de corte (`estacion.html`, opción A elegida por Jose, 23-nov-2026)

- Revisada en la tablet Fire acostada (960 × 600 puntos). Jose eligió el **retoque (A)**: una
  columna de 760, barra fija arriba (`.barra`) con el estado del plotter (`#plot`) separado de su
  botón Conectar (`#pill`, se oculta conectado), iconos en todos los botones (`ICO`/`ico()`),
  vistas de 96 y avance en %. Las otras propuestas (B dos columnas "Ahora/Fila", C lista ancha)
  no se eligieron; están en https://claude.ai/artifact/4V99EYNGpAe7MvEyuUr88H.
- ⚠️ **"Descartar" pide un segundo toque** (`porConfirmar`, 4 s): borra el trabajo sin regreso
  y está junto a "Cortar". No quitar la confirmación.
- ⚠️ **`.acciones` lleva `align-items:center`**: sin eso la etiqueta Enviado/Falló/Detenido se
  estira al alto del botón vecino y la palabra queda pegada arriba.
- La lógica (`#estacion-logica`) no cambió: `web/test_estacion.mjs` solo prueba esa parte. Lo
  visual se verificó en la tablet real con una copia local (`adb reverse tcp:8799 tcp:8799`).
