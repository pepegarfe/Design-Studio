---
name: idea-web-online
description: "Design Studio en el navegador — EN MARCHA: en línea en studio.builtbyjose.tech (Mac + túnel), estación compartida, plan de mudanza a Railway"
metadata:
  node_type: memory
  type: project
  originSessionId: 44e6b81a-bc3a-4b91-b006-6f53d30048f9
  modified: 2026-11-11T19:09:58.207Z
---

# Design Studio "online" — EN MARCHA desde el 2-nov-2026

Explorada el 21-jul-2026 y pausada; retomada el 2-nov-2026 con el plan de abajo. Estado actual: al final.

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
- **Web Serial por cable: solo Chrome/Edge en computadora**: ni Safari, ni Firefox, ni iPhone/iPad.
  ⚠️ **ANDROID SÍ tiene camino (corregido 5-nov-2026)**: ver "WebUSB en Android" abajo.
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
- **413 al Enviar** (2-nov, primera prueba real en Chrome): bottle rechaza pedidos >100 KB
  (`MEMFILE_MAX`) y afectaba a TODA ruta con diseño grande. Subido a 200 MB en `studio_server.py`.
  Se escondió porque las rutas atrapan el error y responden **200 con el error adentro**: una
  prueba que solo mira el código HTTP no lo ve — mirar `ok` del cuerpo. La auditoría ahora prueba
  un diseño de ~2 MB y usa un puerto PROPIO (`DS_PORT`): con el 8765 le pegaba al servidor de Jose.
- ✅ **PROBADO CON EL PLOTTER REAL (2-nov-2026)**: la interfaz completa en Chrome (servidor local)
  conectó y CORTÓ un diseño de Jose por Web Serial (tras arreglar el 413).
  Sin Web Serial (Safari/Firefox) cae al plotter del servidor y el aviso dice "pyserial…": fase 3.

## Fase 3 HECHA (2-nov-2026): seguridad — ✅ Jose creó su cuenta, entró y cortó con la sesión puesta
- **Entrar con contraseña** (`web_auth.py`): cuentas en `datos_web/usuarios.json` (gitignored; `DS_DATOS`
  la mueve), solo la huella PBKDF2 (600k vueltas); cookie `ds_sesion` firmada HMAC (llave en
  `datos_web/secreto.key` o `DS_SECRETO`), HttpOnly + SameSite=Lax (+ Secure en https), 30 días.
  La **1.ª cuenta solo desde localhost** y sin `X-Forwarded-For`; después `/crear` queda cerrado
  (más cuentas = fase 4). 8 fallos → 15 min de bloqueo por dirección (`DS_PROXY=1` para creerle
  a X-Forwarded-For detrás de Railway). Mismo mensaje si el usuario no existe.
- La guardia va **por fuera de bottle** (`_guardia`, WSGI): ninguna ruta nueva queda abierta por
  olvido. También corta pedidos >64 MB y agrega cabeceras (nosniff, X-Frame-Options DENY).
  ⚠️ Solo la aplica `main()`: importar `app` en otro lado la salta.
- Huecos cerrados: `/api/text` aceptaba CUALQUIER archivo como fuente (ahora solo los de la lista);
  `update_start` descargaba CUALQUIER URL y `update_apply` (ahora la web no se actualiza:
  "siempre la más reciente"); plotter en el servidor APAGADO (`DS_PLOTTER_SERVIDOR=1` lo prende),
  con aviso "usa Chrome o Edge" en vez de "pyserial…"; nombre de exportación saneado.
- UI: fetch con 401 → `/entrar`; "Cerrar sesión" en el diálogo de versión (web).
- `web/auditar_servidor.py` → **59/59** (32 de seguridad nuevas). Sin salir: la cookie robada vale
  hasta que vence (no hay lista de sesiones; cambiar `v` del usuario las mata todas).
- Pendiente para publicar: HTTPS (fase 5), servidor de varios a la vez, datos por usuario (fase 4).

## Fase 4 EN CÓDIGO (4-nov-2026) — ⏳ falta que Jose la pruebe y la decisión de fuentes
- **Datos por cuenta**: `datos_web/usuarios/<usuario>/` (fresas, tarifas, área, autoguardado). El calco
  y los acomodos también son por cuenta. Reglas para tocar esto: `.claude/rules/servidor-web.md`.
- **Herencia**: la cuenta del dueño nace con una COPIA de `plotter_config.json`, `cnc_config.json` y
  `autosave.dstudio` de la carpeta del proyecto. ⇒ desde ahí, lo que Jose cambie en la web NO llega
  al escritorio ni al revés. La copia buena era la del proyecto (fresa 2 filos MDF a 1270); la de la
  app instalada (`~/Library/Application Support/Antike/PlotterController/`) sigue en 4000 de fábrica.
- **Cuentas**: dueño = la primera del archivo. `/cuentas` (solo él): alta con contraseña temporal,
  restablecer, desactivar (saca al instante, conserva los datos). `/clave`: cualquiera cambia la
  suya; con temporal nada funciona hasta cambiarla. Enlaces en el diálogo de versión de la interfaz.
  Las cuentas NO se borran desde la app.
- **Varios a la vez**: waitress si está instalado, si no el servidor con hilos de Python. waitress
  NO está en la Mac (Python de Homebrew protegido); se probó instalado aparte. Hay que meterlo en
  las dependencias al publicar.
- **Fuentes**: `DS_FUENTES=<carpeta>` hace que solo se ofrezca ese catálogo. Falta decidir cuál.
- **Auditoría con los dos servidores** (116/116 al cerrar esto; 143/143 con la prueba sin cuenta). Se quitó cada protección en una copia (10 casos) y
  la auditoría las detectó todas. Lo que delató el fallo de waitress fue correrla con los dos.
- ⚠️ `node web/test_plotter_web.mjs`: falla intermitente "plotter que pide pausas: 0 pausas"; también
  salió en el commit b0c3c8e, anterior a la fase 4. El plotter real no pide pausas.

## Prueba sin cuenta (4-nov-2026, pedido de Jose: "ingreso fácil... donde no se guarden parámetros")
- Botón "Probar sin cuenta" en `/entrar` (`POST /invitado`, sin contraseña). Cada visitante tiene su
  carpeta en `datos_web/invitados/`: los ajustes valen mientras dura la prueba y se borran al salir,
  a las 2 h o al reiniciar. Empieza siempre con valores de fábrica; autoguardado desactivado; el
  navegador no recuerda los baudios. Interpretación mía: Jose no pidió una cuenta compartida.
- Sin la carpeta la cookie deja de valer, así que salir la mata aunque alguien la haya copiado.
- Topes por ser público: 20 pruebas a la vez, 10 nuevas por dirección cada 15 min, 1 acomodo a la vez
  por visitante. `DS_INVITADOS=0` quita el botón.
- ⚠️ DECIDIR ANTES DE PUBLICAR: cualquiera de internet podrá usar el procesador sin contraseña.
- Falla "plotter que pide pausas" de `test_plotter_web.mjs`: INTERMITENTE. Salió 2 veces y luego
  pasó limpio 9 seguidas sin que se tocara esa parte; causa sin investigar.

## WebUSB en Android (5-nov-2026) — ✅ PROBADO por Jose en su Galaxy (Android 16): conectó, movió en el aire y CORTÓ el cuadrado
✅ **En la app (5-nov)**: el conector Web Serial (`WSP`) no se tocó; se le cambió el cable
(`serieDelNavegador`: Android → WebUSB disfrazado de serial). `test_plotter_web.mjs` → 72 OK, con
los 11 comandos de Android byte a byte iguales al escritorio y 2 casos de control (driver roto,
Android usando Bluetooth) atrapados. ⏳ Falta: Jose con la APP en el Galaxy (necesita https o el
ajuste de chrome://flags hacia el servidor de la Mac) y ver si la interfaz se puede usar en un
teléfono (está hecha para computadora).
- Jose tiene **Samsung Galaxy con Android 16** y adaptador OTG. Primero le dije "hoy no" mirando solo
  Web Serial: en Android, `navigator.serial` solo lista **Bluetooth**; el cable llega con Android 17
  y solo en aparatos "configurados para exponer puertos serie" (Chromium, intent to ship, M148).
  Jose pidió investigar bien → el camino real es **WebUSB + driver FTDI propio**: Chrome Android lo
  tiene hace años y RadioFoundry (PR #312) lo usa con un **FT232R en Galaxy S22**. En Mac/Windows NO
  sirve (el driver del sistema tiene tomado el chip) — allá sigue Web Serial.
- `web/prueba_webusb.html`: conectar (filtro FTDI 0x0403), mover en el aire (PR, sin PD) y cuadrado.
  Driver = 5 mensajes de control (reset, DTR/RTS 0x0303, sin flujo, 8N1 0x0008, baud 9600 = 0x4138) y
  envío por paquetes de 64. Solo ENVÍA (el plotter es mudo). `node web/test_webusb.mjs` → 29 OK con
  chip simulado; cuadrado byte a byte = escritorio.
- **Publicada en https://prueba-plotter.builtbyjose.workers.dev** (Worker de Cloudflare solo con esa
  página; WebUSB exige https). Se publica desde una carpeta con `wrangler.jsonc` +
  `public/index.html`; ⚠️ **wrangler necesita Node 22**: `export PATH="/opt/homebrew/opt/node@22/bin:$PATH"`.
- Lección: ante un "no se puede", buscar a alguien que YA lo hizo con el mismo chip antes de razonar
  sobre especificaciones.

## "Estación de corte" con un Android viejo (5-nov-2026) — ✅ CONSTRUIDA, ⏳ falta la prueba de Jose
- **11-nov-2026, dicho por Jose (no lo vi yo)**: la **tablet Fire HD 8** (proyecto `~/servidor-tablet`)
  **acepta el plotter** por USB-C y su **Chrome sí hace WebUSB**. Esa tablet es también el servidor
  de `~/vigia-precios`. ⚠️ Desde el 10-nov tiene los **Servicios de Google Play apagados** (fallaban
  en bucle): Chrome avisa "habilitar servicios de Google Play" al abrir; se ignora. No se ha
  confirmado que WebUSB siga funcionando así: si falla, sospechar eso primero. Chrome NO se apaga
  (Firefox no tiene WebUSB). Para cortar y cargar a la vez hace falta un OTG con entrada de carga.
- Construida: `estacion.py` (fila por cuenta, 30 pendientes, 20 de historial, vista previa del
  HPGL), `/estacion` (pantalla para teléfono: avisa con vibración y pitido, espera "Cortar",
  Detener, "¿Se terminaron?" para los que quedaron a medias, "Cortar otra vez") y el botón
  "A la estación" en la app (solo web y cuentas reales). Auditoría 169/169 con los dos servidores
  (sección K); `node web/test_estacion.mjs` 27 OK, con 2 casos de control (corta sola; cable
  arrancado anotado como "detenido") atrapados.
- Decisiones de Jose: avisa y espera (no corta sola); servidor = su Mac + túnel; "Probar sin
  cuenta" se QUEDA; dominio `studio.builtbyjose.tech`.
- ⚠️ `builtbyjose.tech` está registrado en **Squarespace** con DNS de Squarespace, y su raíz y
  `www` son el **portafolio de Jose en Lovable** (185.158.133.1). Para el túnel con nombre fijo hay
  que mudar el DNS a Cloudflare (gratis): lo hace Jose en los paneles; yo comparo antes de cambiar
  nameservers. ⚠️ **Del dominio cuelgan OTROS proyectos** (panel de Squarespace, 11-nov-2026), TODOS
  a copiar en "DNS only" (gris): CNAME `leads`→gungry-scraper.netlify.app, CNAME
  `money`→my-money-buddy.netlify.app, y el **correo del briefing de Omniseller** vía Resend
  (`briefing@omniseller.builtbyjose.tech`, `~/omniseller/app/routers/briefing.py`): MX
  `send.omniseller` 10 feedback-smtp.us-east-1.amazonses.com, TXT `send.omniseller`
  `v=spf1 include:amazonses.com ~all`, TXT `resend._domainkey.omniseller` (DKIM; valor con `dig`).
  Sin estos, el briefing cae a spam SIN error. `_domainconnect` (Squarespace) no hace falta.
  Lección: yo había dicho "sin correo" mirando solo la raíz; los certificados (certspotter) delatan
  sitios, NO correo — la lista real es la del panel.
  ✅ **MUDADO (11-nov-2026)**: nameservers `peyton`/`zoe.ns.cloudflare.com` (antes de cambiarlos
  comparé cada registro preguntando directo a Google y a Cloudflare: idénticos; sin DNSSEC). Tras
  el cambio, portafolio/leads/money 200 y correo idéntico. ⏳ Confirmar que el briefing siguiente
  llega a bandeja.
- `cloudflared` instalado (brew, 2026.10.7). **Túnel con nombre `design-studio`** (id d37c7f4e…,
  config en `~/.cloudflared/config.yml` → http://localhost:8765) y CNAME `studio` creados el
  11-nov; https funcionando (Let's Encrypt, a los ~2 min de activar la zona). ⏳ Aún corre a
  mano: falta decidir con Jose dejarlo permanente (launchd + que la Mac no se duerma).
- 11-nov, a pedido de Jose: tras entrar se vuelve a la página pedida (`?siguiente=`, validado) y la
  **prueba sin cuenta también tiene estación** (fila chica, solo de ese navegador). Auditoría 182/182
  con los dos servidores; control: quitar la validación del regreso → 2 fallas.
- 11-nov: **estación COMPARTIDA** (Jose eligió "una sola fila, todos"): `datos_web/taller/`, cada
  trabajo dice quién lo mandó. Las 5 cortadas reales de Jose de esa mañana quedaron en la fila
  vieja de su cuenta (`usuarios/pepegarfe/estacion*`, todas "hecho"; nadie las lee ya).
  Cuentas al 11-nov: `pepegarfe` (dueño) y `angel`.
- **Plan Railway** (aprobado el plan, no la ejecución): A) Dockerfile (Python + potrace + PyMuPDF
  + shapely), puerto de Railway (hoy lee `DS_PORT`), datos en volumen `/data` (`DS_DATOS`),
  fuentes = **Google Fonts** (decisión de Jose; `DS_FUENTES`, licencia libre); B) Jose crea cuenta
  Hobby US$5/mes, yo conecto el repo (⚠️ requiere `git push`: pedir permiso; el repo es PÚBLICO,
  `datos_web/` está en .gitignore); C) dirección provisional `*.up.railway.app`, copiar datos con
  `secreto.key` (mantiene sesiones), **MEDIR cómo llega la IP del visitante** (trampa del bloqueo)
  y probar todo; D) congelar, copiar datos frescos, CNAME `studio` → Railway (regreso: volver al
  túnel en 1 min); E) apagar la Mac como servidor tras unos días. Jose YA tiene cuenta Railway
  (Omniseller, Gungry; CLI logueada en la Mac): no hay cuenta nueva, el costo se suma (~US$3–8/mes
  calculado, no medido). Sin Docker en la Mac: la receta solo se prueba en Railway.

### Pendientes al 11-nov-2026 (fin de sesión)
- ✅ La estación YA cortó en real (5 trabajos "hecho" de Jose esa mañana, antes de compartirla).
- ✅ **Fase A de Railway HECHA (11-nov, sin commit ni push)**: `Dockerfile` (python 3.12-slim +
  potrace de apt; al construir comprueba tkinter/fitz/shapely/vtracer/potrace y FALLA si falta
  algo), `requirements-servidor.txt` (versiones de la Mac), `.dockerignore` (⚠️ excluye
  `datos_web/`) y `web/preparar_fuentes.py` + `web/fuentes_google.txt`: las **206 familias** de la
  Mac que existen en Google (las otras 137 son Apple/Microsoft, sin licencia para servidor) →
  572 .ttf, 97 MB, 17 s. ⚠️ El User-Agent de Firefox 24 YA recibe .woff (0/206): va el de
  Safari 5. Verificado sin Docker: fontTools lee las 572, "ANTIKE" en Bebas Neue = 7 contornos /
  20.00 mm (igual que ago), auditoría **182/182 con waitress** y esas fuentes, y arranque con el
  CMD del contenedor sobre una copia filtrada por `.dockerignore` y volumen vacío. NO probado: la
  imagen en sí (no hay Docker en la Mac; se prueba en Railway, Fase C).
  Notas para la Fase C: `fonts_cache.json` y la config común caen en `/app` (se pierden en cada
  despliegue: se rehacen solas, ~5 s); en volumen vacío NADIE puede crear la cuenta del dueño
  (viene de fuera) → copiar `datos_web` ANTES de abrirlo; si Cloudflare queda con nube naranja
  delante de Railway, el ÚLTIMO X-Forwarded-For podría ser Cloudflare y no el visitante → medir.
  ✅ Commit `6af9da8` y push (subió también 16 commits viejos sin subir; revisados: sin datos
  privados; la CI solo corre con tags `v*`). ✅ **Fase B HECHA (11-nov)**: proyecto Railway `design-studio`
  (id a09a33e2…), servicio `studio` conectado a GitHub `master` (⚠️ cada push a master DESPLIEGA
  ahí), volumen `/data`, dirección provisional **https://studio-production-34eb0f8a.up.railway.app**
  (región US West). Compila: 206/206 familias, `potrace: /usr/bin/potrace`, waitress. Abre en
  "Servidor sin cuentas" (desde fuera nadie crea la del dueño: correcto). ⚠️ 1ª compilación FALLÓ:
  la imagen `slim` trae el módulo tkinter pero NO `libtk8.6.so` → `libtk8.6` en el apt (`a785db5`,
  mandado con `railway up`, sin push). ✅ **Fase C casi completa (11-nov)**: `datos_web` (cuentas,
  `secreto.key`, `taller/`; sin `invitados/`) subido al volumen con `railway volume files
  --volume studio-volume upload` y **comparado byte a byte de vuelta: 17 archivos idénticos**.
  🚨 **IP del visitante MEDIDA y ROTA**: con `DS_PROXY=1` el bloqueo de 8 fallos NO funcionaba en
  Railway (9/9 sin bloqueo fingiendo IP). Un servicio de eco temporal (borrado) mostró que el
  último X-Forwarded-For es el borde de Railway (cambia cada pedido) y que `X-Real-IP` la
  sobrescribe Railway → nuevo `DS_IP_CABECERA=X-Real-IP` (`3941fd5`, regla en
  `servidor-web.md`). Auditoría **184/184 con los dos servidores**; en vivo: 9.º intento
  bloqueado y otra IP real (salida del contenedor, `railway ssh`) libre. Humo como invitado en
  Railway **13/13** (572 fuentes, texto, potrace, vtracer, HPGL idéntico, SVG/PDF/DXF, unión,
  acomodo, estación). Trampas: `railway volume files` exige `--volume` sin interactivo (y en zsh
  no meterlo en una variable: no se separa); `railway ssh -- python -c` destroza comillas →
  mandar el guion en base64. ✅ Jose entró con su cuenta en la dirección provisional y vio los
  trabajos de `angel` (11-nov); push hecho, despliegue desde GitHub `f51f36b` con
  `DS_IP_CABECERA=X-Real-IP` comprobado dentro del contenedor. **Fase C cerrada.** ✅ **Fase D HECHA (11-nov, 16:30)**: `https://studio.builtbyjose.tech` sirve desde Railway con certificado Let's Encrypt propio (vence feb-2027, Railway lo renueva). Historia: el primer dominio (id `02200809-…`) se quedó >2 h en `ISSUING / POLLING_AUTHORIZATIONS` con el sitio CAÍDO (`railway domain certificate retry` se niega mientras está en ISSUING). Arreglo: **borrar el dominio y volver a agregarlo** cuando el CNAME ya apuntaba a Railway → VALID en <1 min (id nuevo `efadcd0d-a5b6-4e81-96fb-10f83991f435`; el TXT no cambió). Lección: **mover el CNAME ANTES de agregar el dominio**; si se atora, borrar y re-agregar. CNAME `studio` → `hwdu091q.up.railway.app` (nube GRIS), cambiado por Jose y comprobado 11-nov. ⚠️ **Tras la caída, el Chrome de Jose seguía diciendo "no seguro"** aunque desde fuera el certificado estaba bien (las dos IP de Railway, .92 y .74, lo daban correcto): en incógnito salía seguro → era lo que Chrome guardó durante la caída. Remedio: ⌘Q y reabrir; si insiste, borrar los datos del sitio en `chrome://settings/content/all` (`chrome://net-internals/#sockets` ya no carga en su Chrome). Señal: **fuera bien + incógnito bien = caché del navegador, no el servidor**. Servidor de la Mac APAGADO; el volumen es la única fuente de datos. Regreso de emergencia al túnel: CNAME `studio` → `d37c7f4e-ab94-4f38-845d-d6d022cd318b.cfargotunnel.com` nube NARANJA + servidor de la Mac + `cloudflared tunnel run design-studio` (antes copiar el volumen a la Mac).
- ⏳ **Cada push a `master` reinicia el servidor de Railway** aunque solo cambien notas (medido 11-nov: ~30 s sin respuesta al cambiar de contenedor; además se borran los bloqueos por contraseña, que viven en memoria). Ofrecido a Jose: configurar "Watch Paths" en Railway para que solo reconstruya cuando cambie código. Sin respuesta.
- ✅ **Cerrar sesión visible** (comprobado en el código el 12-nov-2026): el editor lo tiene en el
  menú de cuenta del riel (`armarCuenta`) y la estación en su pie. Esta nota lo daba por pendiente
  cuando ya estaba hecho. Ese día se **quitó el botón "v dev"** y su ventana "Actualizaciones"
  (resto del escritorio: `version.txt` dice `dev` desde que se borró la CI) y las rutas
  `update_start/status/apply`; el menú de cuenta muestra al pie la **huella `BUILD`** del
  despliegue, para saber si dos pantallas corren el mismo programa.
- ⏳ Que Jose pruebe: entrar por el túnel con su cuenta (vuelve a /estacion), y que `angel` mande
  a la estación compartida.
- ⏳ Servidor y túnel corren A MANO desde la sesión (se caen si la Mac duerme); con Railway ya no
  hace falta dejarlos permanentes. **11-nov tarde: cayó con error 1033** (túnel sin conexión;
  `cloudflared tunnel list` con CONNECTIONS vacío). 1033 = túnel caído; 502 = túnel vivo y
  servidor caído. Para encenderlo: servidor con `/opt/homebrew/bin/python3 studio_server.py` y
  `PYTHONPATH` apuntando a una carpeta con waitress, y túnel `cloudflared tunnel run design-studio`
  (el modo automático de Claude NO deja abrir el túnel: lo corre Jose en su Terminal).
  ⚠️ **waitress vive en `~/.local/ds-waitress`** (instalado el 11-nov con `pip install --target`):
  arrancar con `PYTHONPATH=~/.local/ds-waitress`. Antes estaba en un scratchpad de /private/tmp y
  **macOS lo vació** (quedó solo `__pycache__`): el servidor arrancaba sin error con "el simple de
  Python" y la auditoría también, creyendo usar waitress. Señal: la línea `(servidor: …)` del
  arranque. ✅ Reiniciado con waitress el 11-nov (la fila del taller estaba toda "hecho": 2 de `angel`, la
  estación compartida ya funcionó con otra cuenta).
- ⏳ Mañana 12-nov: confirmar que el briefing de Omniseller llegó a bandeja (primer envío tras la
  mudanza del DNS).

### Diseño original (antes de construir)
- Jose preguntó si el TELÉFONO podía ser el servidor → NO recomendado (Termux, librerías compiladas
  dudosas, Samsung mata procesos en segundo plano, datos en el teléfono). Lo que SÍ: el teléfono como
  ESTACIÓN fija en el taller: Chrome en una pantalla "Estación de corte" que pide trabajos a una fila
  del servidor y los manda por WebUSB. No corre el motor.
- ✅ **Android viejo de Jose probado (5-nov)** con la página de prueba: detectó el plotter y movió en el aire.
- Por resolver: cable OTG en "Y" (cargar y hablar con el plotter a la vez; no todo teléfono lo admite),
  pestaña al frente con pantalla encendida, el permiso USB de Android puede volver a pedirse al
  reconectar, y la fila solo de cuentas autorizadas. Propuesta: la estación AVISA y espera un toque de
  "Cortar" (que el plotter nunca arranque sin nadie mirando).
- Servidor recomendado para "solo yo": **su Mac + túnel gratis de Cloudflare** (US$0, sin cambiar
  código, datos donde están). ⚠️ Trampa: el túnel entra desde la propia Mac → todo visitante parece
  "esta computadora"; revisar `es_esta_computadora()` con `DS_PROXY=1` antes de prenderlo.
  Después: mini-PC en el taller, o Railway con volume cuando haya clientes.
- ⏳ **Interfaz "Diseño → Corte" (12-nov-2026, commit `62a14d8`, en línea)**: maqueta aprobada por
  Jose y programada (reglas en CLAUDE.md, sección "Diseño → Corte"). Probada con navegador
  invisible (Playwright en `/tmp/ds-maqueta`, no persiste) y `.tap` idéntico byte a byte al
  anterior. **Falta que Jose la pruebe con el plotter REAL conectado** (conectar, mover cabezal,
  prueba de corte: mismo código, otro sitio) y en un teléfono real. Sin decidir: guardar
  velocidad/presión **por material** en el plotter (Jose no contestó). `CLAUDE.md` va en 333
  líneas contra su regla de <200: ofrecido moverlo a `.claude/rules/`, sin respuesta.
- ✅ **Corte de CNC rehecho como Aspire (12-nov-2026)**, tras comparar función por función contra
  la documentación de Vectric: lista ↔ formulario separados, fresa en el formulario, tiempo por
  trayectoria, duplicar, plantillas y **puentes a mano** sobre el lienzo. Jose pidió "todos los
  cambios"; **dejé fuera dos a propósito** y se lo dije: pasada final delgada (choca con la regla
  de `_passes`) y *leads* (riesgo de morder la pieza vecina). ⏳ Falta el primer corte REAL con
  puentes a mano, y decidir esas dos. V-carve quedó anotado como proyecto aparte.
- ✅ **Corte de CNC, propuesta "D" (12-nov-2026)**: Jose no quedó conforme con el flujo tipo
  Aspire; le dibujé cuatro propuestas (página en claude.ai, no persiste aquí) y eligió la
  combinada: material como encabezado, pasos Cortes/Revisar, corte creado desde el dibujo con
  una barra junto a la selección, color y número por corte, formulario con dibujos y "Atravesar",
  un archivo por fresa y aviso de orden. Reglas en CLAUDE.md. ⏳ Sin probar en la máquina ni
  con Ángel; yo le propuse **ver a alguien nuevo preparar un corte** y ajustar con eso.
- ✅ **Paquete "nivel profesional", partes 1–3 (12-nov-2026)**, tras un análisis de lo que falta
  frente a Illustrator/Corel/Aspire para un taller de rotulación: color por figura y corte por
  color, descarte, abrir PDF (con sus colores), "Mis proyectos" en la cuenta y alivio de esquinas
  (dogbone). Reglas en CLAUDE.md. ⏳ **Quedó fuera y se lo dije:** EPS y CDR (faltan programas del
  sistema y un .cdr de muestra — pedírselo a Jose), texto de un solo trazo para grabar (falta la
  tabla de una fuente Hershey; el grabado de línea ya se hace con perfil "Sobre" poco profundo),
  mosaico, imprimir-y-cortar (depende de si su plotter tiene sensor), V-carve, órdenes de trabajo.

## Pendiente para publicar (fase 5)
- `datos_web/` debe vivir en un disco que SOBREVIVA a cada despliegue, con respaldos: ahí están las
  cuentas y el trabajo de los clientes. Fijar `DS_DATOS` y `DS_PROXY=1`.
- ⚠️ Sin comprobar: `plotter_control.py` importa `tkinter` al inicio; un servidor Linux podría no
  tenerlo y el programa no arrancaría.
- Sin tope de acomodos simultáneos por cuenta: uno podría acaparar el procesador.
- `/api/fonts` entrega rutas completas del servidor (con un catálogo propio ya no dicen nada de la Mac).

## Estado
Fases 1, 2 y 3 probadas por Jose. Fase 4 en código y auditada. Relacionado: [[estado]].
