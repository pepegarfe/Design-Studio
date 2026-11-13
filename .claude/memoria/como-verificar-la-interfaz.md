---
name: como-verificar-la-interfaz
description: "Cómo probar la interfaz web de Design Studio SIN abrir el Chrome de Jose — navegador invisible de Playwright sobre una copia del proyecto, teléfono táctil simulado, comparación de G-code y comprobación del sitio en vivo; con las trampas que costaron errores el 12-nov-2026"
metadata:
  node_type: memory
  type: reference
  originSessionId: 7c7f36ce-19d2-4a33-afda-0d07dab90adc
  modified: 2026-11-13T01:02:30.285Z
---

# Cómo se verifica la interfaz (sin tocar el Chrome de Jose)

Jose prohíbe abrir su Chrome sin pedirlo. El 12-nov-2026 autorizó usar **`/tmp`** para montar un
navegador invisible; esa carpeta **no sobrevive** entre sesiones, así que hay que volver a armarla.
Esta nota es la receta.

## Montaje (5 minutos)
- **Navegador**: el Chromium de Playwright ya está en
  `~/Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/` (verificado el 12-nov). En una
  carpeta temporal: `npm i playwright-core` y lanzarlo con `executablePath` apuntando ahí.
- **Servidor de prueba**: copiar `*.py *.json *.html *.js version.txt vendor/ iconos/` a una
  carpeta temporal y arrancar `DS_PORT=8799 DS_DATOS=<temporal>/_datos python3 studio_server.py`.
  ⚠️ Nunca sobre la carpeta real: escribe configuración. La primera visita crea la cuenta del dueño
  (formulario `usuario`/`clave`/`clave2`); después, entrar con esa.
- **Apagarlo** con `lsof -ti tcp:8799 | xargs kill`, **no** con `pkill -f studio_server.py`: eso
  cerraría también un servidor real de Jose si lo tuviera abierto.
- `window.__DS` expone estado para las pruebas (`doc`, `sel`, `tp`, `bboxOf`, `colOf`,
  `cnc.prev`, `cnc.tpaths`, `hpglPayload`).

## Trampas que costaron errores
- **Teléfono = puntero TÁCTIL, no ventana angosta.** Contexto con
  `hasTouch:true, isMobile:true`. Bajo `@media (pointer:coarse)` los botones crecen; con una ventana
  de 390 px y ratón no se ve, y así se me pasaron botones encimados que Jose sí vio.
- **Una prueba que no imprime nada NO pasó.** Dos veces un guion desactualizado (no pulsaba un
  cuadro nuevo) dejó una comparación "idéntica" entre dos archivos vacíos. Exigir siempre el número
  de líneas o el nombre del archivo en la salida.
- **Las fuentes y el fallo que no aparece.** El navegador de prueba corre en la Mac, que tiene las
  fuentes instaladas. Para probar el selector hay que usar `DS_FUENTES` con familias renombradas.
- **Railway es varias veces más lento que la Mac.** Lo que aquí tarda 1 s allá se siente roto;
  medir en vivo cuando el cambio toca cálculo.
- **Clic en una figura ya seleccionada dentro de un grupo no la selecciona sola**: primero hay que
  pulsar una zona vacía del lienzo (no la regla de arriba).

## Antes y después de subir
1. **Sintaxis de los dos `<script>` de `studio_ui.html`** (extraerlos y pasarlos por
   `new Function(...)` en node). Esto habría evitado romper el editor en producción.
2. **G-code idéntico**: generar el mismo corte con la interfaz nueva y con la de `HEAD` (misma
   copia, cambiando solo el HTML por `git show HEAD:studio_ui.html`) y comparar byte a byte. Para
   el generador: 80 combinaciones de puentes × rampa × última pasada × lado contra el módulo viejo.
3. Las pruebas del repo: `auditar_gcode.py`, `web/auditar_servidor.py`, los tres `web/test_*.mjs`.
4. **Después del push**: esperar a que `/health` conteste la huella `BUILD` calculada aquí
   (`import studio_server; studio_server.BUILD`), y luego **bajar la página EN VIVO** entrando por
   `/invitado` y repetir la comprobación de sintaxis. Las rutas nuevas también se pueden probar así.
