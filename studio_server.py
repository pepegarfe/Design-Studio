#!/usr/bin/env python3
"""
Design Studio — servidor web local.

Sirve la interfaz (studio_ui.html) por HTTP y expone el motor de corte como una pequeña API.
Corre en la computadora conectada al plotter; cualquier dispositivo en la misma red abre el
navegador en http://<ip-de-esta-mac>:8765 y usa Design Studio SIN instalar nada.

La lógica pesada (leer SVG/DXF/AI, HPGL, plotter) se reutiliza de plotter_control.py.
"""
import os
import json
import tempfile
import socket

from bottle import Bottle, BaseRequest, static_file, request, response, HTTPResponse

from studio_backend import (SERVICE, set_workarea as _set_workarea,
                            cnc_get as _cnc_get, cnc_set as _cnc_set,
                            load_workarea, load_vector, build_hpgl, test_square_hpgl,
                            cnc_toolpaths_preview as _cnc_preview, cnc_build_tap as _cnc_tap)
import img_trace as tracer
import text_vector as texter
import geo_ops as geo
import curve_fit as fitter
import nest_ops as nester
import updater
import export_ops as exporter

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get('DS_PORT', 8765))   # otro puerto: lo usa web/auditar_servidor.py
app = Bottle()
# ⚠️ bottle rechaza por defecto todo pedido de más de 100 KB (error 413), y un diseño real lo
# pasa fácil: "Enviar al plotter" fallaba (caso real 2-nov-2026). Y como las rutas atrapan el
# error, respondían 200 con el 413 escondido en el mensaje. En internet este tope protege al
# servidor de pedidos gigantes: revisarlo en la fase de seguridad.
BaseRequest.MEMFILE_MAX = 200 * 1024 * 1024


def _workarea():
    return list(load_workarea())   # la MISMA función que el escritorio


def _json(obj, status=200):
    return HTTPResponse(body=json.dumps(obj), status=status,
                        headers={'Content-Type': 'application/json; charset=utf-8'})


@app.get('/')
def index():
    return static_file('studio_ui.html', root=HERE)


@app.get('/three.bundle.js')
def three_bundle():
    return static_file('three.bundle.js', root=HERE)


@app.get('/api/workarea')
def api_workarea():
    return _json({'work': _workarea()})


@app.post('/api/set_workarea')
def api_set_workarea():
    d = request.json or {}
    return _json(_set_workarea(d.get('w'), d.get('h')))


@app.get('/api/cnc')
def api_cnc_get():
    return _json(_cnc_get())


@app.post('/api/cnc')
def api_cnc_set():
    return _json(_cnc_set(request.json or {}))


@app.get('/api/tools_export')
def api_tools_export():
    cfg = _cnc_get()
    return _json({'ok': True, 'format': 'antike-tools',
                  'materials': cfg['materials'], 'tools': cfg['tools']})


@app.post('/api/tools_import')
def api_tools_import():
    d = request.json or {}
    if not d.get('tools'):
        return _json({'ok': False, 'error': 'Ese archivo no trae fresas.'})
    return _json(_cnc_set({'materials': d.get('materials'), 'tools': d['tools']}))


@app.post('/api/cnc_toolpath')
def api_cnc_toolpath():
    return _json(_cnc_preview(request.json or {}))


@app.post('/api/tap')
def api_tap():
    return _json(_cnc_tap(request.json or {}))


_TRACE_TMP = [None]   # la imagen que el calco está usando ahora


@app.post('/api/trace_upload')
def api_trace_upload():
    up = request.files.get('file')
    if up is None:
        return _json({'ok': False, 'error': 'No llegó ninguna imagen.'}, 400)
    ext = os.path.splitext(up.filename or 'img')[1].lower() or '.png'
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tmp.close()
    up.save(tmp.name, overwrite=True)
    r = tracer.set_source(tmp.name)
    # El calco relee la imagen en cada ajuste, así que esta se queda; la ANTERIOR ya no
    # la usa nadie. Sin esto cada imagen subida se quedaba en el disco para siempre.
    if r.get('ok'):
        sobra, _TRACE_TMP[0] = _TRACE_TMP[0], tmp.name
    else:
        sobra = tmp.name   # no se pudo abrir: no sirve para nada
    if sobra:
        try:
            os.unlink(sobra)
        except OSError:
            pass
    return _json(r)


@app.post('/api/trace')
def api_trace():
    return _json(tracer.trace(request.json or {}))


@app.get('/api/fonts')
def api_fonts():
    return _json(texter.list_fonts())


@app.post('/api/text')
def api_text():
    return _json(texter.text_paths(request.json or {}))


@app.post('/api/boolean')
def api_boolean():
    return _json(geo.boolean_op(request.json or {}))


@app.post('/api/offset')
def api_offset():
    return _json(geo.offset_op(request.json or {}))


@app.post('/api/fit')
def api_fit():
    return _json(fitter.fit_nodes(request.json or {}))


@app.post('/api/fit_many')
def api_fit_many():
    return _json(fitter.fit_nodes_many(request.json or {}))


@app.post('/api/expand')
def api_expand():
    return _json(geo.expand_op(request.json or {}))


@app.post('/api/round')
def api_round():
    return _json(geo.round_op(request.json or {}))


@app.post('/api/divide')
def api_divide():
    return _json(geo.divide_op(request.json or {}))


@app.post('/api/nest')
def api_nest():
    return _json(nester.nest_op(request.json or {}))


@app.post('/api/nest_start')
def api_nest_start():
    return _json(nester.nest_start(request.json or {}))


@app.post('/api/nest_status')
def api_nest_status():
    return _json(nester.nest_status(request.json or {}))


@app.post('/api/export')
def api_export():
    """Devuelve el archivo YA GENERADO como descarga (no JSON: son binarios y pesan)."""
    d = request.json or {}
    r = exporter.export_bytes(d.get('format'), d)
    if not r.get('ok'):
        return _json(r)
    tipos = {'png': 'image/png', 'jpg': 'image/jpeg', 'pdf': 'application/pdf',
             'svg': 'image/svg+xml', 'dxf': 'application/dxf'}
    name = (d.get('name') or 'diseno').rsplit('.', 1)[0] + '.' + r['ext']
    return HTTPResponse(body=r['bytes'], status=200, headers={
        'Content-Type': tipos.get(r['ext'], 'application/octet-stream'),
        'Content-Disposition': f'attachment; filename="{name}"'})


@app.get('/api/update_check')
def api_update_check():
    return _json(updater.check())


@app.post('/api/update_start')
def api_update_start():
    return _json(updater.start((request.json or {}).get('url')))


@app.post('/api/update_status')
def api_update_status():
    return _json(updater.status((request.json or {}).get('job')))


@app.post('/api/update_apply')
def api_update_apply():
    # En modo web el servidor NO se auto-reemplaza (updater.apply se niega si no es
    # la app compilada); la respuesta explica que se actualiza con git pull.
    return _json(updater.apply((request.json or {}).get('job')))


@app.post('/api/autosave_save')
def api_autosave_save():
    from studio_backend import autosave_save as f
    return _json(f(request.json or {}))


@app.get('/api/autosave_load')
def api_autosave_load():
    from studio_backend import autosave_load as f
    return _json(f())


@app.post('/api/autosave_clear')
def api_autosave_clear():
    from studio_backend import autosave_clear as f
    return _json(f())


@app.post('/api/parse')
def api_parse():
    up = request.files.get('file')
    if up is None:
        return _json({'ok': False, 'error': 'No llegó ningún archivo.'}, 400)
    name = up.filename or 'archivo'
    ext = os.path.splitext(name)[1].lower()
    if ext not in ('.svg', '.dxf', '.ai'):
        return _json({'ok': False, 'error': 'Formato no soportado (usa SVG, DXF o AI).'})
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tmp.close()
    try:
        up.save(tmp.name, overwrite=True)
        r = load_vector(tmp.name)   # el MISMO lector que el escritorio
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    if r.get('ok'):
        r['name'] = name   # el nombre real, no el del temporal
    return _json(r)


@app.post('/api/hpgl')
def api_hpgl():
    try:
        data = request.json or {}
        hpgl = build_hpgl(data)   # el MISMO que corta el escritorio
    except Exception as e:
        return _json({'ok': False, 'error': f'No se pudo generar el HPGL: {e}'})
    return _json({'ok': True, 'hpgl': hpgl, 'lines': hpgl.count('\n') + 1, 'bytes': len(hpgl)})



@app.get('/api/test_square')
def api_test_square():
    # Para el navegador que maneja el plotter él mismo (Web Serial): solo pide el HPGL.
    hpgl = test_square_hpgl(10)
    return _json({'ok': True, 'hpgl': hpgl, 'lines': hpgl.count('\n') + 1, 'bytes': len(hpgl)})


# ── Plotter (Fase 3 — SIN verificar con hardware) ───────────────────────────────
@app.get('/api/ports')
def api_ports():
    return _json(SERVICE.ports())

@app.get('/api/status')
def api_status():
    return _json(SERVICE.status())

@app.post('/api/connect')
def api_connect():
    d = request.json or {}
    return _json(SERVICE.connect(d.get('port'), d.get('baud', 9600)))

@app.post('/api/disconnect')
def api_disconnect():
    return _json(SERVICE.disconnect())

@app.post('/api/jog')
def api_jog():
    d = request.json or {}
    return _json(SERVICE.jog(d.get('direction'), d.get('dist', 1)))

@app.post('/api/pen')
def api_pen():
    d = request.json or {}
    return _json(SERVICE.pen(bool(d.get('down'))))

@app.post('/api/command')
def api_command():
    d = request.json or {}
    return _json(SERVICE.command(d.get('which')))

@app.post('/api/send')
def api_send():
    return _json(SERVICE.send_design(request.json or {}))

@app.get('/api/send_progress')
def api_send_progress():
    return _json(SERVICE.progress())

@app.post('/api/cancel')
def api_cancel():
    return _json(SERVICE.cancel())

@app.post('/api/testcut')
def api_testcut():
    return _json(SERVICE.test_cut())


def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def main():
    import threading
    threading.Thread(target=texter.list_fonts, daemon=True).start()   # calienta el caché de fuentes
    ip = _lan_ip()
    print(f"Design Studio en:")
    print(f"  · esta Mac:        http://localhost:{PORT}")
    print(f"  · otros dispositivos (misma red): http://{ip}:{PORT}")
    from bottle import run
    run(app, host='0.0.0.0', port=PORT, quiet=True)


if __name__ == '__main__':
    main()
