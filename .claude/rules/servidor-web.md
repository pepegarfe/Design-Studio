---
paths:
  - studio_server.py
  - web_auth.py
  - studio_backend.py
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
- **`NOMBRE_VALIDO` no admite punto inicial**: el nombre es una carpeta, y `..` caería sobre los datos de todos.
- **Prueba sin cuenta**: el usuario `invitado:<vence>-<hex>` no está en `usuarios.json`, su carpeta la
  da `carpeta_de()` y lo que guarde en memoria se limpia en `_limpiar_invitado()`: ⚠️ una estructura
  nueva por cuenta en memoria va también ahí. Es público: una ruta pesada nueva necesita tope.
- ⚠️ Código de la interfaz que corre en `node web/test_plotter_web.mjs` no puede usar `window`: allá no existe.
- **La auditoría se corre con los DOS servidores.** La falla de waitress no aparecía con el simple:
  `pip install --target <carpeta> waitress` y `PYTHONPATH=<carpeta> python3 web/auditar_servidor.py`.
