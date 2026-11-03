---
name: idea-web-online
description: Idea guardada — Design Studio como app web local multi-dispositivo (prototipo funcional, en pausa)
metadata:
  type: project
---

# Idea: Design Studio "online" (app web local) — EN PAUSA

Explorada el 21-jul-2026 y **pausada por decisión de Jose** para seguir con la plataforma real.
Se guarda porque el prototipo **funciona** y quizá se retome.

## Qué quería Jose
Abrir Design Studio **desde varios dispositivos** (laptop, tablet, teléfono) y **sin instalar nada**.

## La arquitectura que lo cumple
Un **servidor web local** que corre en la Mac conectada al plotter. Otros dispositivos en la
**misma red WiFi** abren el navegador en `http://<ip-de-la-mac>:8765` y usan la app sin instalar nada.
La cara (HTML/CSS/JS) es la misma que la de escritorio; solo cambia el transporte (pywebview → HTTP).

- **`studio_server.py`** — servidor con `bottle` (ya instalado). Sirve `studio_ui.html` y expone
  `GET /api/workarea` y `POST /api/parse` (sube un archivo → lo parsea con el motor → devuelve
  trazados en mm + bbox). **Probado y funcionando** (leyó `prueba-corte.svg`: 7 trazados, bbox ok).
- La versión de escritorio equivalente es **`design_studio.py`** (pywebview), misma `studio_ui.html`.
  ⚠️ Ojo: `studio_ui.html` quedó adaptado a **fetch/HTTP** (modo servidor). Para volver a pywebview
  hay que regresar la parte de "Abrir" al puente `window.pywebview.api` (o hacerlo dual).

## El candado (CORREGIDO 2-nov-2026)
⚠️ Esta nota decía que "un navegador **no puede** tocar el puerto serie". **Era falso**: la API
**Web Serial** (Chrome/Edge de escritorio, desde 2021) habla con dispositivos USB-serial con
permiso del usuario, y el plotter es un FTDI FT232R (ver [[plotter-puerto-usb]]). Límites reales:
- **Solo Chrome/Edge en computadora**: ni Safari, ni Firefox, ni iPad/teléfono.
- ⚠️ **XON/XOFF no existe en Web Serial** (`flowControl` solo `none`/`hardware`): habría que
  escuchar a mano 0x13/0x11 y pausar el envío. Sin eso, un diseño largo se corta mal SIN error.
  Es lo PRIMERO que hay que probar con el plotter real.
- Fuentes: la web no puede listar las del sistema → catálogo propio (Google Fonts).
- CNC no tiene candado: el `.tap` se descarga y va a la USB como hoy.

Dos caminos evaluados: (1) motor Python en servidor + UI en navegador (rápido, mensualidad);
(2) todo en el navegador con Pyodide (shapely/ezdxf/fontTools sí; pymupdf dudoso; mucho más
trabajo). Paso propuesto antes de decidir: prueba mínima Web Serial + XON/XOFF que corte un cuadrado.

## Paso 1 construido (2-nov-2026): `web/prueba_webserial.html`
Jose dijo "vamos adelante". Página mínima: conectar por Web Serial (8N1, 9600, `flowControl:'none'`),
cuadrado de prueba **byte a byte igual** a `HPGLConverter.test_square()`, y **"flujo en el aire"**
(miles de `PU` en 20 mm con la cuchilla arriba) que cuenta las pausas XOFF: el cuadrado (~100 bytes)
NUNCA llena la memoria del plotter, así que no prueba el control de flujo — la de flujo sí.
`node web/test_webserial.mjs web/prueba_webserial.html` → 11 OK contra un plotter simulado, con caso
de CONTROL (ignorando XOFF sí desborda). ⚠️ Trampa del simulador: si el envío falso es instantáneo,
los avisos XOFF nunca llegan a tiempo y todo "falla" — el cable real tarda ~1 ms/byte.
⏳ **Falta lo único que decide: correrla con el plotter real** (Chrome, `python3 -m http.server`
en `web/`). Si "Pausas del plotter" = 0, subir movimientos; el XOFF real nunca se ha visto.

## Prueba con el plotter REAL (2-nov-2026)
- ✅ **Conectó y cortó el cuadrado desde Chrome** (77 bytes, 0.1 s). El navegador SÍ maneja el plotter.
- **Flujo, 8000 movimientos (79 KB): la página terminó en 91.6 s (~860 B/s = el tope del cable a
  9600) con 0 XOFF, y el cabezal SIGUIÓ moviéndose** → el plotter guardó ≥ ~74 KB sin pedir pausa.
  Su memoria es grande; un diseño de vinil normal no la llena. Falta ver si terminó en el origen.
- ⚠️ **Error de diseño mío**: dije que con movimientos cortos la prueba sería breve. FALSO: la memoria
  solo se llena si el plotter consume MÁS LENTO que el cable (≤960 B/s), así que movimientos cortos
  NUNCA la llenan, y con memoria de ~1 MB llenarla tarda ≥18 min con cualquier diseño.
  Lo que se arrastra es el VACIADO: lo guardado se ejecuta después (8000 movs ≈ 25 min).
- Por eso se agregó **"Memoria del plotter"**: `ESC.L` (tamaño), `ESC.B` (libre) — HPGL los
  atiende al instante aunque esté ocupado — y **`ESC.K` = paro** (tirar lo guardado). ⏳ No
  probados en este plotter. 15 OK en simulador.
- ⚠️ **Hallazgo para la app de ESCRITORIO**: "Detener" solo frena lo que falta por ENVIAR; lo que
  el plotter ya guardó (minutos) sigue. `abort()` manda ESC + `IN;`, y ese `IN;` se forma DETRÁS
  de lo guardado. Si `ESC.K` funciona aquí, es el paro real que también le falta al escritorio.

## El plotter NO habla, y no hace falta (2-nov-2026)
- Plotter = **SMT Robotics Cutting Plotter 721**, clon de la familia "721" (Jinka JK-721 y otros).
- **Nunca manda un solo byte**: `OI;`, `OS;`, `ESC.B`, `ESC.L` → 0 bytes, en la página Y con
  pyserial (script crudo, sin xonxoff). ⇒ **el `xonxoff=True` del ESCRITORIO jamás ha hecho nada**,
  y no hay `ESC.K`: el único paro real es el **botón Reset del plotter**.
- CTS sale ENCENDIDA (en FT232R suelta se lee apagada) → quizá control por HARDWARE. No confirmado.
- Manual del Jinka JK-721: **memoria 1–4 MB**, HPGL/DMPL, serie + USB, sin dato de handshake.
  A 9600 baudios 1 MB tarda ≥18 min en llegar y el plotter corta mientras tanto: un diseño
  normal no la llena. Encaja con lo medido (≥74 KB sin pausa). ⇒ El control de flujo es
  **irrelevante en la práctica**; NO se gastó la prueba larga de CTS (20+ min) para confirmarlo.
- Si algún día se pierde un corte largo a medias: la sospecha es el desborde → probar
  `flowControl:'hardware'` (Web Serial) / `rtscts=True` (pyserial).

## PLAN aprobado (2-nov-2026) — "primero solo yo, luego clientes"
Decisión de Jose: arranca solo él/su taller, pero **los datos se construyen YA separados por usuario**
(fresas, tarifas, autoguardado, prefs) para no rehacerlo al abrir a clientes. Escritorio sigue vivo.
1. **Auditoría en local**: `studio_server.py` vs el puente de `design_studio.py`, función por función.
2. **Plotter → navegador** (Web Serial, reusando `web/prueba_webserial.html`).
3. **Seguridad**: hoy escucha en `0.0.0.0` SIN contraseña y expone `update_apply` (reemplaza el
   programa) y el puerto serie → quitar en modo web + acceso con contraseña.
4. **Datos por usuario** + catálogo de fuentes propio (el servidor no tiene las 981 de la Mac).
5. **Publicar** con HTTPS (Web Serial lo EXIGE), probablemente Railway. ~US$5–20/mes.

## Fase 1 HECHA (2-nov-2026): auditoría servidor vs escritorio
- **En código**: las 39 llamadas de la UI tienen camino web (`api() ? puente : fetch`); 26/29 rutas
  llaman a la MISMA función del motor que el escritorio; el resto son copias idénticas.
- **En marcha**: `web/auditar_servidor.py` → **20/20 OK** (abrir SVG/DXF/AI idéntico al escritorio,
  HPGL idéntico, CNC, fuentes, texto, booleana, exportar 4 formatos, calco, autoguardado). Corre
  sobre una COPIA temporal: escribe config. NO probado en marcha: trayectorias CNC/.tap, nesting,
  offset/expand/round/divide/fit (misma función que el escritorio, solo verificado en código).
- **Lo que hay que arreglar para ONLINE** (no para la Mac):
  1. **Todo es UNO para todos**: calco (`img_trace._STATE`), plotter (`SERVICE`), config/fresas/
     autoguardado (un archivo) → dos usuarios se pisan. Fase 4.
  2. **bottle con `wsgiref` = atiende de a UNO**: un nesting largo congela a todos. Necesita
     servidor con hilos (waitress/gunicorn) antes de publicar.
  3. ~~El calco deja la imagen subida en el disco~~ → ARREGLADO en fase 2 (ver abajo).
  4. Fuentes = las del equipo donde corre (981 en la Mac; un servidor Linux tendría casi ninguna).
  5. Seguridad y plotter: fases 2 y 3.
  6. ~~Código triplicado~~ → ARREGLADO en fase 2: todo vive en `studio_backend`.
- Trampa de la prueba: `python -I` NO sirve para correr el servidor (le quita su propia carpeta y
  no encuentra `plotter_control`), y pywebview revienta al importarse si `sys.argv[0]` es relativo.

## Fase 2 HECHA en código (2-nov-2026): el plotter desde el navegador
- `studio_ui.html`: `<script id="motor-plotter">` (`PlotterMotor`) + conector `WSP` dentro del
  script principal. `P.*` decide **en cada llamada**: `api()` (escritorio) → `ws()` (Web Serial,
  si el navegador lo tiene) → `fetch('/api/...')` (plotter junto al servidor, p. ej. iPad en LAN).
  ⚠️ No decidir al cargar: `window.pywebview` aparece DESPUÉS de cargar la página.
- El servidor solo arma el HPGL (`/api/hpgl`, `/api/test_square`); el navegador lo manda.
- Unificado en `studio_backend`: `load_workarea`, `load_vector`, `build_hpgl`, `test_square_hpgl`
  (escritorio y servidor llaman a las MISMAS). Escritorio comparado antes/después: idéntico.
- Calco: la imagen anterior se borra al subir otra, y `img_trace.trace()` ya borra sus `.pbm/.svg/
  .png` de trabajo (fuga que también tenía el ESCRITORIO: 2 archivos por cada ajuste del calco).
- Pruebas: `node web/test_plotter_web.mjs` → navegador manda **byte a byte lo mismo** que el
  `PlotterService` del escritorio (`web/bytes_escritorio.py`, cable de mentira) en conectar, mover,
  pluma, origen, casa, enviar, test de corte y cancelar; más permisos, otra pestaña, desenchufar,
  doble envío, XON/XOFF. `web/auditar_servidor.py` → 24/24 (cuenta temporales con `TMPDIR` propio).
- Conectar AMIGABLE (pedido de Jose, 2-nov: "no es nada amigable"): en el navegador la píldora dice
  "Conectar plotter" y conecta de UN clic (`WSP.rapido`); ventanita de Chrome filtrada a chips de
  plotter (FTDI 0x0403, CH340 0x1a86, Prolific 0x067b, Silicon Labs 0x10c4; "Mostrar todos los
  cables" sin filtro); con permiso previo conecta solo al abrir la página o al enchufar (`WSP.auto`,
  evento `connect`); puerto/baudios bajo "Opciones avanzadas"; "Enviar" sin conexión conecta y sigue.
  La 1.ª ventanita de Chrome NO se puede quitar (seguridad del navegador). Escritorio sin cambios.
- ❌ FALTA: probarlo con la interfaz real en Chrome + el plotter (solo probado con cable simulado).
  Sin Web Serial (Safari/Firefox) cae al plotter del servidor y el aviso dice "pyserial…": fase 3.

## Estado
Prototipo web funcional en `studio_server.py` + `studio_ui.html`. Se retoma si Jose quiere el acceso
multi-dispositivo. Relacionado: [[estado]].
