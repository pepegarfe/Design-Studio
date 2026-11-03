#!/usr/bin/env python3
"""
Design Studio — interfaz nueva (web) que REUSA el motor de Plotter Antike.

La cara (HTML/CSS/JS en studio_ui.html) corre dentro de una ventana nativa (pywebview);
la lógica pesada — leer SVG/DXF/AI, generar HPGL, hablar con el plotter — se importa tal
cual de plotter_control.py. No se reescribe el motor, solo la interfaz.
"""
import os
import sys
import json
import webview

import plotter_control as core   # el motor existente (parsers, HPGL, controlador)
from studio_backend import (SERVICE, set_workarea as _set_workarea,
                            cnc_get as _cnc_get, cnc_set as _cnc_set, flip_paths_y,
                            load_workarea, load_vector, build_hpgl,
                            cnc_toolpaths_preview as _cnc_preview, cnc_build_tap as _cnc_tap)
import img_trace as tracer
import text_vector as texter
import geo_ops as geo
import curve_fit as fitter
import nest_ops as nester
import updater
import export_ops as exporter

# En la app compilada (PyInstaller) los recursos van a sys._MEIPASS; como script, junto al .py.
if getattr(sys, 'frozen', False):
    HERE = sys._MEIPASS
else:
    HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- registro de arranque
# La app se distribuye SIN consola (`console=False` en el .spec), así que si se cuelga al
# arrancar no hay dónde ver nada: el usuario solo ve "No responde". Este registro es la
# única ventana a lo que pasó. Vive junto a la config (AppData en Windows).

_LOG_F = None


def _log(msg):
    """Escribe una línea con hora en arranque.log. Nunca falla ni interrumpe la app."""
    global _LOG_F
    try:
        import time as _t
        if _LOG_F is None:
            p = core._config_path().with_name('arranque.log')
            # Que no crezca sin fin: pasado 1 MB se empieza de cero.
            if p.exists() and p.stat().st_size > 1_000_000:
                p.unlink()
            _LOG_F = open(p, 'a', encoding='utf-8')
        _LOG_F.write(f'{_t.strftime("%H:%M:%S")}  {msg}\n')
        _LOG_F.flush()   # ⚠️ SIEMPRE: si la app muere a la fuerza, lo no volcado se pierde
    except Exception:
        pass


def _armar_vigilante():
    """Si el arranque se atora, vuelca la pila de TODOS los hilos al registro.

    `faulthandler` es del propio Python y hace justo esto. Convierte un "se queda en No
    responde" en "el hilo principal está detenido en tal archivo, tal línea"."""
    try:
        import faulthandler
        if _LOG_F is None:
            return
        faulthandler.enable(file=_LOG_F)                                  # y ante un cierre brusco
        faulthandler.dump_traceback_later(25, repeat=True, file=_LOG_F)   # cada 25 s si sigue vivo
        _log('vigilante armado (vuelca las pilas si el arranque pasa de 25 s)')
    except Exception as e:
        _log(f'vigilante NO armado: {e}')


def _desarmar_vigilante():
    try:
        import faulthandler
        faulthandler.cancel_dump_traceback_later()
    except Exception:
        pass


# Las dos viven en studio_backend: el servidor web usa EXACTAMENTE las mismas.
_load_workarea = load_workarea
_load_vector = load_vector


class Api:
    """Métodos que la interfaz web puede llamar (window.pywebview.api.*)."""

    def __init__(self):
        # ⚠️ EL GUION BAJO NO ES ESTILO: ES LO QUE EVITA UN ABRAZO MORTAL. NO se lo quites.
        # pywebview RECORRE este objeto para exponerle sus métodos al JavaScript, y se mete
        # dentro de cualquier atributo público que sea un objeto (`util.py` get_functions).
        # Si la ventana cuelga de un atributo público, el recorrido toca `window.width`, cuyo
        # getter le PREGUNTA EL TAMAÑO A LA VENTANA NATIVA... que en ese instante todavía se
        # está creando en otro hilo. Los dos se esperan y la app se queda en "No responde"
        # PARA SIEMPRE. Es una carrera: en Mac casi nunca se pierde; en Windows, 2 de cada 3.
        # Los nombres que empiezan con `_` los SALTA (`if name.startswith('_'): continue`).
        self._window = None

    def get_workarea(self):
        ww, wh = _load_workarea()
        return {'work': [ww, wh]}

    def set_workarea(self, w, h):
        return _set_workarea(w, h)

    # --- CNC (Fase A): máquina activa, material y biblioteca de fresas ---
    def cnc_get(self):
        return _cnc_get()

    def cnc_set(self, patch):
        return _cnc_set(patch or {})

    def tools_export(self):
        """Guarda la biblioteca (materiales + fresas) como JSON con diálogo nativo."""
        cfg = _cnc_get()
        res = self._window.create_file_dialog(webview.SAVE_DIALOG,
                                             save_filename='fresas-antike.json')
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res if isinstance(res, str) else res[0]
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'format': 'antike-tools', 'materials': cfg['materials'],
                           'tools': cfg['tools']}, f, ensure_ascii=False, indent=1)
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo guardar: {e}'}
        return {'ok': True, 'path': os.path.basename(path)}

    def tools_import(self):
        """Abre un JSON de biblioteca y REEMPLAZA materiales + fresas (validando)."""
        res = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=('Biblioteca de fresas (*.json)', 'Todos los archivos (*.*)'))
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res[0] if isinstance(res, (list, tuple)) else res
        try:
            d = json.loads(open(path, encoding='utf-8').read())
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo leer: {e}'}
        if not d.get('tools'):
            return {'ok': False, 'error': 'Ese archivo no trae fresas.'}
        return _cnc_set({'materials': d.get('materials'), 'tools': d['tools']})

    def cnc_toolpath(self, data):
        """Trayectorias del centro de la fresa, para previsualizar en el lienzo."""
        return _cnc_preview(data or {})

    def save_png(self, data):
        """Guarda una captura PNG de la Vista 3D (llega como data-URL base64)."""
        import base64
        d = data or {}
        try:
            raw = base64.b64decode((d.get('data') or '').split(',', 1)[1])
        except Exception:
            return {'ok': False, 'error': 'Captura vacía o corrupta.'}
        res = self._window.create_file_dialog(webview.SAVE_DIALOG,
                                             save_filename=d.get('name') or 'vista3d.png')
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res if isinstance(res, str) else res[0]
        if not path.lower().endswith('.png'):
            path += '.png'
        try:
            with open(path, 'wb') as f:
                f.write(raw)
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo guardar: {e}'}
        return {'ok': True, 'path': os.path.basename(path)}

    def cnc_tap_text(self, data):
        """El G-code como TEXTO (sin diálogo): lo consume la Vista 3D, que simula
        el corte comiéndose el mismo .tap que se llevaría la máquina."""
        return _cnc_tap(data or {})

    def save_tap(self, data):
        """Genera el G-code y lo guarda como .tap con diálogo nativo."""
        r = _cnc_tap(data or {})
        if not r.get('ok'):
            return r
        name = ((data or {}).get('name') or 'diseno').rsplit('.', 1)[0] + '.tap'
        res = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name)
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res if isinstance(res, str) else res[0]
        if not path.lower().endswith('.tap'):
            path += '.tap'
        try:
            with open(path, 'w', newline='\n') as f:
                f.write(r['tap'])
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo guardar: {e}'}
        return {'ok': True, 'path': os.path.basename(path),
                'lines': r['lines'], 'secs': r['secs'], 'skipped': r['skipped']}

    # --- Calco de imagen ---
    def trace_pick(self):
        res = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=('Imágenes (*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.webp)', 'Todos los archivos (*.*)'))
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res[0] if isinstance(res, (list, tuple)) else res
        return tracer.set_source(path)

    def trace_apply(self, options):
        return tracer.trace(options or {})

    # --- Texto con fuentes del sistema ---
    def fonts(self):
        return texter.list_fonts()

    def text_make(self, data):
        return texter.text_paths(data or {})

    # --- Booleanas y contorno (diseño) ---
    def geo_boolean(self, data):
        return geo.boolean_op(data or {})

    def geo_offset(self, data):
        return geo.offset_op(data or {})

    def fit_nodes(self, data):
        """Polilínea → anclas+manijas Bézier, para la edición de nodos."""
        return fitter.fit_nodes(data or {})

    def fit_many(self, data):
        """Suavizar en lote: re-ajusta curvas sobre polilíneas facetadas."""
        return fitter.fit_nodes_many(data or {})

    def geo_expand(self, data):
        return geo.expand_op(data or {})

    def geo_round(self, data):
        return geo.round_op(data or {})

    def geo_divide(self, data):
        return geo.divide_op(data or {})

    def geo_nest(self, data):
        """Acomodo de piezas en la hoja (nesting BLF con rotaciones)."""
        return nester.nest_op(data or {})

    def geo_nest_start(self, data):
        """Nesting EN VIVO: arranca el cálculo en un hilo y devuelve el id."""
        return nester.nest_start(data or {})

    def geo_nest_status(self, data):
        return nester.nest_status(data or {})

    # --- Exportar como… (PNG/JPG/PDF/SVG/DXF) ---
    def export_as(self, data):
        """Genera el archivo y lo guarda con el diálogo nativo del sistema."""
        d = data or {}
        r = exporter.export_bytes(d.get('format'), d)
        if not r.get('ok'):
            return r
        ext = r['ext']
        name = (d.get('name') or 'diseno').rsplit('.', 1)[0] + '.' + ext
        res = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name)
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res if isinstance(res, str) else res[0]
        if not path.lower().endswith('.' + ext):
            path += '.' + ext
        try:
            with open(path, 'wb') as f:
                f.write(r['bytes'])
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo guardar: {e}'}
        return {'ok': True, 'path': path, 'size': len(r['bytes'])}

    # --- Actualizaciones (solo tiene efecto en la app compilada) ---
    def update_check(self):
        return updater.check()

    def update_start(self, data):
        return updater.start((data or {}).get('url'))

    def update_status(self, data):
        return updater.status((data or {}).get('job'))

    def update_apply(self, data):
        """Instala y CIERRA la ventana: el ayudante externo reemplaza la app y la relanza."""
        res = updater.apply((data or {}).get('job'))
        if res.get('ok'):
            # Un respiro para que la respuesta llegue al JS antes de que muera la ventana.
            import threading
            threading.Timer(0.6, self._quit).start()
        return res

    def _quit(self):
        try:
            self._window.destroy()
        except Exception:
            os._exit(0)

    # --- Autoguardado ---
    def autosave_save(self, data):
        from studio_backend import autosave_save as f
        return f(data or {})

    def autosave_load(self):
        from studio_backend import autosave_load as f
        return f()

    def autosave_clear(self):
        from studio_backend import autosave_clear as f
        return f()

    def ref_image(self):
        """Imagen de referencia: diálogo nativo → data-URL para pintarla de fondo."""
        res = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=('Imágenes (*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.webp)', 'Todos los archivos (*.*)'))
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res[0] if isinstance(res, (list, tuple)) else res
        import base64
        import mimetypes
        mime = mimetypes.guess_type(path)[0] or 'image/png'
        try:
            data = base64.b64encode(open(path, 'rb').read()).decode()
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo leer la imagen: {e}'}
        return {'ok': True, 'data': f'data:{mime};base64,{data}'}

    def open_design(self):
        """Abre un diálogo nativo. Acepta un diseño (SVG/DXF/AI), un proyecto (.dstudio)
        o una imagen (PNG/JPG…) que se manda directo al calco."""
        res = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=('Diseños imágenes y proyectos '
                        '(*.svg;*.dxf;*.ai;*.dstudio;*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.webp;*.tif;*.tiff)',
                        'Todos los archivos (*.*)'))
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res[0] if isinstance(res, (list, tuple)) else res
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tif', '.tiff'):
            r = tracer.set_source(path)
            if isinstance(r, dict) and r.get('ok'):
                r['kind'] = 'image'
            return r
        if ext == '.dstudio':
            try:
                proj = json.loads(open(path, encoding='utf-8').read())
                return {'ok': True, 'kind': 'project', 'project': proj,
                        'name': os.path.basename(path)}
            except Exception as e:
                return {'ok': False, 'error': f'No se pudo abrir el proyecto: {e}'}
        return _load_vector(path)

    def import_design(self):
        """Como open_design pero para SUMAR a la mesa (no reemplaza): solo vectores
        y proyectos. Las imágenes van por Abrir — el calco siempre reemplaza."""
        res = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=('Diseños y proyectos (*.svg;*.dxf;*.ai;*.dstudio)',
                        'Todos los archivos (*.*)'))
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res[0] if isinstance(res, (list, tuple)) else res
        if os.path.splitext(path)[1].lower() == '.dstudio':
            try:
                proj = json.loads(open(path, encoding='utf-8').read())
                return {'ok': True, 'kind': 'project', 'project': proj,
                        'name': os.path.basename(path)}
            except Exception as e:
                return {'ok': False, 'error': f'No se pudo abrir el proyecto: {e}'}
        return _load_vector(path)

    def _hpgl(self, data):
        return build_hpgl(data)   # el MISMO que usan el envío al plotter y el servidor web

    def gen_hpgl(self, data):
        try:
            hpgl = self._hpgl(data)
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo generar el HPGL: {e}'}
        return {'ok': True, 'hpgl': hpgl, 'lines': hpgl.count('\n') + 1, 'bytes': len(hpgl)}

    def save_hpgl(self, data):
        try:
            hpgl = self._hpgl(data)
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        name = (data.get('name') or 'diseno').rsplit('.', 1)[0] + '.hpgl'
        res = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name)
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res if isinstance(res, str) else res[0]
        try:
            with open(path, 'w') as f:
                f.write(hpgl)
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo guardar: {e}'}
        return {'ok': True, 'path': os.path.basename(path)}

    def save_project(self, data):
        """Guarda el proyecto completo (trazados + transforms + área + corte) a un .dstudio."""
        name = (data.get('name') or 'proyecto')
        name = name.rsplit('.', 1)[0] + '.dstudio'
        res = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name)
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res if isinstance(res, str) else res[0]
        if not path.lower().endswith('.dstudio'):
            path += '.dstudio'
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo guardar: {e}'}
        return {'ok': True, 'path': os.path.basename(path)}

    # --- Plotter (Fase 3, SIN verificar con hardware) — delega en el servicio compartido ---
    def ports(self):            return SERVICE.ports()
    def plotter_status(self):   return SERVICE.status()
    def connect(self, port, baud=9600): return SERVICE.connect(port, baud)
    def disconnect(self):       return SERVICE.disconnect()
    def jog(self, direction, dist=1): return SERVICE.jog(direction, dist)
    def pen(self, down):        return SERVICE.pen(bool(down))
    def command(self, which):   return SERVICE.command(which)
    def send_design(self, data): return SERVICE.send_design(data)
    def send_progress(self):    return SERVICE.progress()
    def cancel(self):           return SERVICE.cancel()
    def test_cut(self):         return SERVICE.test_cut()


def diagnostico():
    """`DesignStudio --diagnostico` — qué trae dentro la app y qué le falta.

    Vale sobre todo en la app COMPILADA: puede arrancar perfecta y tener el texto o el
    acomodo muertos porque una librería no quedó empaquetada. Mejor verlo aquí que
    descubrirlo con el material en la máquina."""
    import cnc_gcode
    # ⚠️ La consola de Windows (cp1252) NO puede escribir ✓ ✗ · → y el programa TRUENA
    # al imprimirlos. Se comprueba antes y, si no caben, se usa texto pelado.
    try:
        '✓·→'.encode(sys.stdout.encoding or 'utf-8')
        SI, NO, PT, FL = '✓', '✗ FALTA ', '·', '→'
    except Exception:
        SI, NO, PT, FL = 'OK', 'FALTA ', '-', '=>'
    print(f'Design Studio {updater.current_version()}')
    print(f'  compilada: {"si" if getattr(sys, "frozen", False) else "no (corriendo del codigo)"}')
    print(f'  python {sys.version.split()[0]} {PT} {sys.platform}')
    filas = [
        ('Plotter (puerto serial)', core.HAS_SERIAL, 'pyserial'),
        ('Abrir DXF', core.HAS_DXF, 'ezdxf'),
        ('Abrir AI', core.HAS_MUPDF, 'pymupdf'),
        ('Texto con fuentes', texter.HAS_FONTS, 'fontTools'),
        ('Booleanas y contorno', geo.HAS_SHAPELY, 'shapely'),
        ('Acomodar en la hoja', nester.HAS_SHAPELY, 'shapely'),
        ('CNC (trayectorias)', cnc_gcode.HAS_SHAPELY, 'shapely'),
    ]
    try:
        potrace = tracer._potrace_bin()
    except Exception as e:
        potrace = f'FALTA ({e})'
    try:
        import vtracer  # noqa: F401
        vt = True
    except Exception:
        vt = False
    filas.append(('Calco a color', vt, 'vtracer'))
    # ⚠️ LA VENTANA MISMA. Sin esto el diagnostico decia "todo completo" en una app que
    # MORIA al abrirse: `webview.start()` carga el motor grafico de forma perezosa, o sea
    # DESPUES de este chequeo. En Windows ese motor necesita pythonnet (`import clr`), el
    # puente Python <-> .NET; si .NET se niega a cargarlo, el usuario ve un muro de
    # traceback en vez de un mensaje util. Aqui se reproduce el mismo import, antes.
    ventana, ventana_error = True, ''
    try:
        import webview  # noqa: F401
        if sys.platform == 'win32':
            import clr  # noqa: F401
    except Exception as e:
        ventana, ventana_error = False, f'{e.__class__.__name__}: {e}'
    filas.append(('Ventana (motor grafico)', ventana, 'pywebview/pythonnet'))
    ancho = max(len(f[0]) for f in filas)
    malos = 0
    for nombre, ok, lib in filas:
        malos += 0 if ok else 1
        print(f'  {nombre.ljust(ancho)}  {SI if ok else NO + lib}')
    print(f'  {"Calco B/N (potrace)".ljust(ancho)}  {potrace}')
    if 'FALTA' in str(potrace):
        malos += 1
    if not ventana:
        print(f'     causa: {ventana_error}')
        if sys.platform == 'win32':
            # ⚠️ La ruta se DEDUCE de donde esta el .exe, no se escribe a mano: quien
            # instalo antes del cambio de fabricante (Antike -> BuiltByJose) sigue en la
            # carpeta vieja hasta que reinstale, y una ruta fija le daria el consejo mal.
            raiz = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else HERE
            # Sin acentos: la consola de Windows (cp1252) truena al imprimirlos.
            print('     Windows suele BLOQUEAR los DLL que salieron de un .zip bajado de')
            print('     internet. Abre PowerShell y corre (una sola linea):')
            print(f'       Get-ChildItem "{raiz}" -Recurse -File | Unblock-File')
    print(f'  {FL} todo completo' if not malos else f'  {FL} FALTAN {malos} piezas')
    return 0 if not malos else 1


def main():
    if '--diagnostico' in sys.argv:
        sys.exit(diagnostico())
    _log('=== ARRANQUE ===')
    _log(f'version {updater.current_version()} | python {sys.version.split()[0]} | '
         f'{sys.platform} | compilada={bool(getattr(sys, "frozen", False))}')
    _armar_vigilante()
    api = Api()
    win = webview.create_window(
        'Design Studio', os.path.join(HERE, 'studio_ui.html'),
        js_api=api, width=1300, height=820, min_size=(1040, 660),
        background_color='#0E1013')
    api._window = win     # ⚠️ con guion bajo a propósito — ver el comentario en Api.__init__
    _log('ventana creada (aun no dibujada)')

    # Calentar el listado de fuentes: cuando el usuario abra el modal de Texto ya está
    # listo (con caché de disco es instantáneo; sin él, el escaneo tarda segundos —
    # MUCHOS en Windows, donde el antivirus inspecciona cada uno de los ~400 archivos
    # que abre una app sin firmar).
    #
    # ⚠️ NUNCA lanzar esto ANTES de `create_window`. Así estaba y colgaba la app en
    # Windows ~2 de cada 3 arranques: el escaneo es Python puro y acapara el intérprete
    # (un solo hilo a la vez), justo mientras la ventana nace y necesita entrar a Python
    # para armarse. Carrera perdida = ventana "No responde" para siempre. En Mac no se
    # notaba porque el escaneo dura 3 s en vez de un minuto.
    #
    # `events.loaded` corre cuando la página YA cargó, y pywebview lo despacha en su
    # propio hilo. Puede dispararse más de una vez: no importa, `list_fonts` cachea.
    def _calentar_fuentes():
        import time
        _log('pagina cargada  <-- si el registro llega aqui, la ventana SI vivio')
        _desarmar_vigilante()   # arrancó bien: ya no hace falta vigilar
        time.sleep(1.5)         # margen para que la ventana termine de asentarse
        try:
            r = texter.list_fonts()
            _log(f'fuentes listas: {len(r.get("fonts") or [])}')
        except Exception as e:
            _log(f'fuentes fallaron: {e}')   # el modal de Texto lo reintentará
    win.events.loaded += _calentar_fuentes

    _log('entrando a webview.start() -- de aqui no se sale hasta cerrar')
    webview.start()
    _log('=== CERRADA NORMALMENTE ===')


if __name__ == '__main__':
    main()
