---
paths:
  - studio_server.py
  - web_auth.py
  - Dockerfile
  - requirements-servidor.txt
  - railway.json
  - iconos/**
  - web/crear_iconos_pwa.py
  - estacion.html
---
# Distribución: dos PWA y actualización automática

Verificado contra el código el 18-nov-2026 (movido del `CLAUDE.md`). Desplegar = `git push` a
`master` (ver `CLAUDE.md`). Historia: [[idea-web-online]], [[sin-escritorio-pwa]].

- **Dos apps instalables en el mismo sitio**, cada una con su manifiesto, su `id` y su logo
  (`MANIFIESTOS` en `studio_server.py`): **Design Studio** (`/`, cuadro magenta con la cabeza de
  corte) y **Estación de corte** (`/estacion`, cuadro oscuro con el botón de cortar). Los logos
  salen de `python3 web/crear_iconos_pwa.py` → `iconos/` (**sí va a git**: el servidor los sirve).
- ⚠️ **El manifiesto, `/favicon.ico` y `/iconos/*` son PÚBLICOS** (`PUBLICAS` y el prefijo en
  `_guardia`): el navegador los pide **sin cookie** y antes de entrar. Si un recurso nuevo de la
  PWA queda detrás de la sesión, recibe un 302 a `/entrar` y la app **deja de ser instalable sin
  ningún error visible**.
- ⚠️ **Cada página enlaza SU icono con `<link rel="icon">`** (editor, estación y las de
  `web_auth._marco`). Sin ese enlace Chrome muestra lo que tenga guardado para el dominio.
- ⚠️ **A propósito NO hay service worker que guarde copias.** La app necesita al servidor para
  todo, y una copia guardada es justo lo que deja a un teléfono con la versión vieja. La
  actualización va así: `/` se sirve con `no-cache`, el servidor publica `BUILD` (huella de sus
  `.py/.html/.js`, cambia en cada despliegue) en `/api/update_check` y en la fila de la estación;
  la estación **se recarga sola cuando no está cortando**, y el editor se recarga solo **si no hay
  diseño abierto** (si lo hay, deja un botón "Actualizar": recargar tiraría lo no guardado).
  **Si agregas un service worker, esta garantía se rompe**: mídelo antes.
- ⚠️ **Para probar si una página es instalable, el oyente de `beforeinstallprompt` va DENTRO de la
  página**: puesto después desde fuera llega tarde y parece que no es instalable (pasó con la
  estación, 11-nov-2026).
- ⚠️ **PyMuPDF fijo en `1.28.0`** (`requirements-servidor.txt`, siempre por debajo de 2): PyMuPDF 2.0
  arrastra `pymupdf-layout`, que al importar busca un modelo `.yaml`. Antes de subirla, construye la
  imagen y prueba.
- **En el servidor TODAS las librerías son obligatorias**: el `Dockerfile` las importa al construir
  (`RUN python -c "import tkinter, bottle, …"`) y la construcción falla si falta una, para no llegar a
  producción con una función muerta sin error. (Las "dependencias opcionales" con flags `HAS_*` son
  de la app de escritorio: ver `motor-y-escritorio-legado.md`.)
