#!/usr/bin/env python3
"""
Calco de imagen (Image Trace) para Design Studio.

Convierte una imagen de píxeles en trazos vectoriales de corte:
- B/N (silueta): Pillow (gris + umbral) -> potrace -> curvas Bézier suaves. Máxima fidelidad
  de contorno para logos/letras/siluetas. Es la familia del "Calco de imagen" de Illustrator.
- Color: vtracer -> separa por colores en capas vectoriales.

En ambos casos la salida es un SVG que se parsea con el motor existente (core.SVGParser),
así fluye por el mismo camino que un diseño importado (lienzo + HPGL).
"""
import os
import shutil
import tempfile
import subprocess

from PIL import Image, ImageOps

import plotter_control as core
from studio_backend import flip_paths_y

# Imagen fuente cargada (para re-calcar al cambiar los controles sin re-subirla).
_STATE = {'path': None, 'name': None}


def _potrace_bin():
    """Ruta absoluta de potrace. Lanzada desde Finder (ícono del Escritorio) o desde un
    entorno recortado, la app NO tiene /opt/homebrew/bin en el PATH y el nombre pelado
    'potrace' truena con 'No such file or directory'.

    En la app COMPILADA se busca primero el potrace que viaja DENTRO del paquete: el
    usuario final no tiene Homebrew, así que sin esta copia el calco B/N no existiría."""
    import sys
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        exe = 'potrace.exe' if sys.platform == 'win32' else 'potrace'
        own = os.path.join(base, exe)
        if os.path.exists(own):
            return own
    p = shutil.which('potrace')
    if p:
        return p
    for cand in ('/opt/homebrew/bin/potrace', '/usr/local/bin/potrace', '/opt/local/bin/potrace'):
        if os.path.exists(cand):
            return cand
    raise RuntimeError('No se encontró potrace. Instálalo con: brew install potrace')


def set_source(path):
    try:
        im = Image.open(path)
        _STATE['path'] = path
        _STATE['name'] = os.path.basename(path)
        return {'ok': True, 'size': [im.width, im.height], 'name': _STATE['name']}
    except Exception as e:
        return {'ok': False, 'error': f'No se pudo abrir la imagen: {e}'}


def has_source():
    return bool(_STATE.get('path')) and os.path.exists(_STATE['path'])


def _svg_to_paths(svg_path):
    styled = core.SVGParser().parse(svg_path)
    paths, xs, ys = [], [], []
    for d in styled:
        pts = d.get('pts') or []
        if len(pts) < 2:
            continue
        rp = [[round(float(x), 3), round(float(y), 3)] for (x, y) in pts]
        paths.append({'pts': rp})
        for x, y in rp:
            xs.append(x); ys.append(y)
    bbox = [min(xs), min(ys), max(xs), max(ys)] if xs else [0, 0, 0, 0]
    # La fuente aquí SIEMPRE es un SVG (potrace/vtracer) => Y-abajo => voltear a Y-arriba.
    # El volteo es sobre el centro del conjunto, así que el bbox no cambia.
    return flip_paths_y(paths), bbox


def _prep_bw(path, threshold, invert, max_side=1400):
    g = Image.open(path).convert('L')
    if max(g.size) < max_side:                      # subir resolución si es chica (mejora el trazo)
        s = max_side / max(g.size)
        g = g.resize((max(1, int(g.width * s)), max(1, int(g.height * s))))
    if invert:
        g = ImageOps.invert(g)
    # potrace traza lo NEGRO. Píxeles oscuros (<=umbral) -> negro (0) -> se cortan.
    return g.point(lambda p: 0 if p <= threshold else 255, 'L').convert('1')


def trace(options):
    if not has_source():
        return {'ok': False, 'error': 'No hay imagen cargada.'}
    path = _STATE['path']
    mode = options.get('mode', 'bw')
    svg = tempfile.mktemp(suffix='.svg')
    sobras = [svg]   # archivos de trabajo: se borran al terminar, salga bien o mal
    try:
        if mode == 'color':
            import vtracer
            # El binding de vtracer crashea si se le pasan parámetros (bug de la versión),
            # así que controlamos la cantidad de colores REDUCIÉNDOLOS con Pillow antes, y
            # llamamos a vtracer con sus defaults (que sí funcionan). El suavizado/manchas se
            # controla con un filtro de mediana previo.
            im = Image.open(path).convert('RGB')
            spk = int(options.get('speckle', 4))
            if spk > 0:
                from PIL import ImageFilter
                im = im.filter(ImageFilter.MedianFilter(size=3 if spk < 6 else 5))
            colors = int(options.get('colors', 6))
            if 2 <= colors < 256:
                im = im.quantize(colors=colors, dither=Image.NONE).convert('RGB')
            src_png = tempfile.mktemp(suffix='.png')
            sobras.append(src_png)
            im.save(src_png)
            vtracer.convert_image_to_svg_py(src_png, svg)
        else:
            bw = _prep_bw(path, int(options.get('threshold', 128)),
                          bool(options.get('invert', False)))
            pbm = tempfile.mktemp(suffix='.pbm')
            sobras.append(pbm)
            bw.save(pbm)
            subprocess.run(
                [_potrace_bin(), '-s', '-o', svg,
                 '--turdsize', str(int(options.get('speckle', 2))),
                 '--alphamax', str(float(options.get('smooth', 1.0))),
                 pbm],
                check=True, capture_output=True)
        paths, bbox = _svg_to_paths(svg)
    except Exception as e:
        return {'ok': False, 'error': f'No se pudo calcar: {e}'}
    finally:
        # Sin esto, CADA ajuste del calco dejaba 2 archivos en la carpeta temporal.
        for f in sobras:
            try:
                os.unlink(f)
            except OSError:
                pass
    if not paths:
        return {'ok': False, 'error': 'El calco no encontró trazos (prueba otro umbral o invertir).'}
    return {'ok': True, 'name': _STATE['name'], 'paths': paths, 'bbox': bbox}
