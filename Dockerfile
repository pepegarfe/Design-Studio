# Design Studio — servidor web para Railway (Fase A del plan de mudanza, 11-nov-2026).
# La Mac + túnel sigue siendo el servidor hasta que la Fase C pruebe esto de punta a punta.
#
# Qué decide cada línea:
#  - python 3.12: el más probado con estas ruedas (pymupdf/shapely/vtracer) en Linux.
#  - potrace: programa aparte que hace el calco B/N; sin él esa función no existe.
#  - fuentes: Google Fonts bajadas AL CONSTRUIR (web/preparar_fuentes.py). Las de la Mac de
#    Jose (Helvetica, Futura...) no pueden ir: su licencia no permite ponerlas en un servidor.
#  - datos: en el VOLUMEN /data (cuentas, llave de sesión, fila del taller). Todo lo demás del
#    contenedor se borra en cada despliegue.
FROM python:3.12-slim

# libtk8.6: la imagen "slim" trae el módulo tkinter pero NO la librería que carga
# ("libtk8.6.so: cannot open shared object file", primera compilación en Railway, 11-nov-2026).
RUN apt-get update \
 && apt-get install -y --no-install-recommends potrace libtk8.6 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-servidor.txt .
RUN pip install --no-cache-dir -r requirements-servidor.txt

# Las fuentes van ANTES que el código: así un cambio de código no vuelve a bajar 97 MB.
COPY web/preparar_fuentes.py web/fuentes_google.txt web/
RUN python web/preparar_fuentes.py /app/fuentes

COPY . .

# ⚠️ Comprobación al CONSTRUIR: si falta una pieza, que falle aquí, en voz alta, y no en
# producción con una función muerta sin ningún error. tkinter: el motor (plotter_control.py)
# lo importa de entrada aunque en el servidor no se dibuje ninguna ventana.
RUN python -c "import tkinter, bottle, waitress, fitz, shapely, PIL, fontTools, vtracer, ezdxf, serial; \
import img_trace, studio_server; print('potrace:', img_trace._potrace_bin()); print('piezas OK')"

# ⚠️ DS_IP_CABECERA, NO DS_PROXY: en Railway el último X-Forwarded-For es SU servidor de borde
# (cambia en cada pedido) y el bloqueo de 8 fallos no funcionaba. X-Real-IP la sobrescribe
# Railway con la real (medido el 11-nov-2026). Detrás de OTRO proxy, volver a medir.
ENV DS_FUENTES=/app/fuentes \
    DS_DATOS=/data \
    DS_IP_CABECERA=X-Real-IP \
    PYTHONUNBUFFERED=1

# Railway dice el puerto en $PORT; el servidor lo lee de DS_PORT (8765 si no hay ninguno).
CMD ["sh", "-c", "DS_PORT=${PORT:-8765} exec python studio_server.py"]
