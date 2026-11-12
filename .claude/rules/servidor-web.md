---
paths:
  - studio_server.py
  - web_auth.py
  - studio_backend.py
  - estacion.py
  - estacion.html
  - img_trace.py
  - nest_ops.py
  - export_ops.py
  - web/auditar_servidor.py
---
# Versión web: varias cuentas atendidas A LA VEZ

Verificado contra el código y con la auditoría el 4-nov-2026. Historia en `idea-web-online.md`.

- **Los datos de cada cuenta salen de `core._config_path()`**, que en la web apunta a
  `datos_web/usuarios/<usuario>/` (lo fija `_guardia` por pedido, con `_CARPETA_USUARIO`). Ninguna
  ruta pide su carpeta. ⚠️ Un archivo nuevo por cuenta debe colgar de `_config_path()`; lo que sea
  común (caché de fuentes) de `_config_compartida()`.
- ⚠️ **Un hilo nuevo NO hereda la cuenta del pedido**: dentro de él, `_config_path()` devuelve la
  config común. El hilo del acomodo no lee config; si otro hilo la necesita, hay que pasársela.
- ⚠️ **Nada de variables globales con datos de una cuenta**: el servidor ya no atiende de a uno. El
  calco se guarda en `_CALCO` y los acomodos llevan `dueno`. Una global se ve bien con un solo
  usuario y mezcla los datos de dos.
- ⚠️ **PyMuPDF no aguanta dos hilos**: PDF, PNG, JPG y abrir `.ai` van bajo `_PYMUPDF`.
- ⚠️ **Config: `_escribir()` y `@_en_fila`, nunca `write_text` directo.** Si `cnc_get()` lee un
  archivo a medio escribir cae a valores de fábrica, y el siguiente guardado BORRA las fresas.
- ⚠️ **waitress va con `clear_untrusted_proxy_headers=False`.** Por defecto borra X-Forwarded-For y
  `es_esta_computadora()` tomaría a un visitante de fuera por local: podría crear la cuenta del dueño.
- ⚠️ **Dirección del visitante (`direccion()`): MEDIDO con un túnel real de Cloudflare (5-nov-2026)**
  todo llega desde `127.0.0.1`, `CF-Connecting-IP` = la real (Cloudflare da **403** si alguien la
  inventa) y `X-Forwarded-For` = **lo que mande el visitante + la real al final**. ⇒ Nunca el PRIMER
  valor de X-Forwarded-For (lo escribe el atacante: esquivaba el bloqueo de 8 fallos); por túnel,
  `CF-Connecting-IP` solo si llega desde la propia Mac; detrás de otro proxy, el ÚLTIMO valor.
  `es_esta_computadora()` exige que no venga NINGUNA de las dos. Auditoría, sección "Y".
- ⚠️ **En RAILWAY el "último valor" FALLA** (MEDIDO con un servicio de eco, 11-nov-2026):
  X-Forwarded-For llega como `<real>, <borde de Railway>` y ese borde **cambia en cada pedido**
  → con `DS_PROXY=1` el bloqueo de 8 fallos no llegaba nunca (9/9 sin bloqueo en el servidor
  real). Railway SOBRESCRIBE `X-Real-IP` con la real → el Dockerfile usa
  **`DS_IP_CABECERA=X-Real-IP`**, no `DS_PROXY`. Comprobado en vivo: 9.º intento bloqueado aunque
  cada uno finja otra IP, y otra IP real (la de salida del contenedor) NO queda bloqueada.
  ⚠️ **Detrás de cualquier proxy nuevo (o Cloudflare con nube naranja delante de Railway) hay
  que VOLVER A MEDIR** antes de confiar en una cabecera: un servicio de eco (imagen
  `mendhak/http-https-echo`) enseña exactamente qué llega. No se deduce: se mide.
- **Estación de corte** (`estacion.py` + `estacion.html` + `/api/estacion/*`): **UNA fila del
  taller para TODAS las cuentas** en `datos_web/taller/` (decisión de Jose, 11-nov-2026); cada
  trabajo lleva `de`. La prueba sin cuenta tiene su fila chica (`TOPES_INVITADO`: es pública) en
  su carpeta temporal y solo la ve ESE navegador. ⚠️ Qué fila usar lo decide SOLO
  `_fila_de_estacion()` con `with estacion.en(...)`: una ruta nueva que no pase por ahí cae en la
  carpeta de la cuenta y la estación nunca vería el trabajo. ⚠️ La estación **avisa y ESPERA** un
  toque de "Cortar" (decisión de Jose): nunca cortar al llegar el trabajo — alguien pone el
  material. ⚠️ `estacion.html` NO lleva el motor: el servidor le inserta el bloque
  `motor-plotter` de `studio_ui.html` en la marca `MOTOR-PLOTTER` (un solo driver para todo).
  "hecho" = enviado entero; un cable arrancado es "error", nunca "hecho" ni "detenido". Pruebas:
  `node web/test_estacion.mjs` y la sección "K" de la auditoría.
- **Latido de la estación** (`_ESTACION_VIVA`, nov-2026): la estación pide la fila por **POST** con
  `{plotter: true|false}` y el editor consulta `GET /api/estacion/estado` (viva / plotter /
  pendientes) para pintar el botón único "Enviar Directo / Enviar Remoto". En memoria, con llave
  por FILA (`'taller'` o el invitado, que se limpia en `_limpiar_invitado`); caduca a los 20 s.
  ⚠️ "viva" = la página está abierta, no que haya alguien: la estación sigue esperando "Cortar".
- ⚠️ **`DS_HTTPS=1` en el Dockerfile** (nov-2026): fuerza la marca `Secure` de la cookie de sesión
  y manda HSTS. MEDIDO en vivo: sin él la cookie salía SIN `Secure`, porque en Railway `_es_https()`
  no confía en `X-Forwarded-Proto` (no es `DS_PROXY` ni túnel). No ponerlo en la Mac: entrando por
  la IP de la red local (http) el navegador descartaría la cookie y nadie podría iniciar sesión.
- **El dueño olvidó su contraseña → `python web/rescatar_dueno.py` EN el servidor** (`railway ssh`).
  Desde la web nadie puede restablecer al dueño (`restablecer_clave` lo rechaza sin `rescate=True`).
- **`/health`** (público, sin datos) lo consulta Railway por `railway.json` antes de dar por bueno un
  despliegue. **Un 500 se anota en `<datos>/errores.log`** (`_anotar_error`: hora, ruta, cuenta,
  traza; rota a los 300 KB). Los errores llegan a la gente en español: página con regreso, o JSON
  `{ok:false,error}` en `/api` (`_ERRORES`).
- **Parámetros de corte del plotter** (velocidad, presión, sobrecorte, esquinas): por cuenta, en la
  llave `cut` de la config del plotter (`load_cut`/`set_cut`), con topes; van junto al área en
  `/api/workarea`.
- ⚠️ **Volver tras entrar (`?siguiente=`) pasa SIEMPRE por `_destino()`**: solo rutas propias por
  lista de lo PERMITIDO. Un `//otro` o `/\otro` el navegador lo lee como otro sitio: el enlace de
  entrada sería un trampolín a una página falsa que pida la contraseña. Auditoría, sección "R".
- **`NOMBRE_VALIDO` no admite punto inicial**: el nombre es una carpeta, y `..` caería sobre los datos de todos.
- **Prueba sin cuenta**: el usuario `invitado:<vence>-<hex>` no está en `usuarios.json`, su carpeta la
  da `carpeta_de()` y lo que guarde en memoria se limpia en `_limpiar_invitado()`: ⚠️ una estructura
  nueva por cuenta en memoria va también ahí. Es público: una ruta pesada nueva necesita tope.
- ⚠️ Código de la interfaz que corre en `node web/test_plotter_web.mjs` no puede usar `window`: allá no existe.
- **La auditoría se corre con los DOS servidores.** La falla de waitress no aparecía con el simple:
  `pip install --target <carpeta> waitress` y `PYTHONPATH=<carpeta> python3 web/auditar_servidor.py`.
