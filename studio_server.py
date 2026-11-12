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
import html
import tempfile
import socket
import re
import time
import threading
import contextlib
import http.cookies

from bottle import Bottle, BaseRequest, static_file, request, response, HTTPResponse, redirect

from studio_backend import (SERVICE, set_workarea as _set_workarea,
                            cnc_get as _cnc_get, cnc_set as _cnc_set,
                            load_workarea, load_cut, set_cut, load_vector, build_hpgl, test_square_hpgl,
                            cnc_toolpaths_preview as _cnc_preview, cnc_build_tap as _cnc_tap)
import img_trace as tracer
import text_vector as texter
import geo_ops as geo
import curve_fit as fitter
import nest_ops as nester
import export_ops as exporter
import web_auth as auth
import estacion
import plotter_control as core

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get('DS_PORT', 8765))   # otro puerto: lo usa web/auditar_servidor.py
app = Bottle()
# ⚠️ bottle rechaza por defecto todo pedido de más de 100 KB (error 413), y un diseño real lo
# pasa fácil: "Enviar al plotter" fallaba (caso real 2-nov-2026). Y como las rutas atrapan el
# error, respondían 200 con el 413 escondido en el mensaje. En internet este tope protege al
# servidor de pedidos gigantes: revisarlo en la fase de seguridad.
LIMITE = 64 * 1024 * 1024   # ningún pedido pasa de 64 MB (un diseño grande real pesa 1–5 MB)
BaseRequest.MEMFILE_MAX = LIMITE

# El control del plotter DESDE EL SERVIDOR (para un navegador sin Web Serial, p. ej. un iPad
# en la red del taller) va APAGADO: en internet el plotter está en la mesa de quien corta, no
# junto al servidor, y es una puerta de más. Se prende con DS_PLOTTER_SERVIDOR=1.
PLOTTER_EN_SERVIDOR = os.environ.get('DS_PLOTTER_SERVIDOR') == '1'
SIN_PLOTTER = ('Para conectar el plotter abre Design Studio en Chrome o Edge de computadora, o en '
               'Chrome de un teléfono o tablet Android (con dirección https). Safari, Firefox, '
               'iPhone e iPad no pueden usar el cable USB.')


def _workarea():
    return list(load_workarea())   # la MISMA función que el escritorio


def _json(obj, status=200):
    return HTTPResponse(body=json.dumps(obj), status=status,
                        headers={'Content-Type': 'application/json; charset=utf-8'})


# ── Entrar / salir (web_auth.py) ──────────────────────────────────────────────
# DS_HTTPS=1 (Railway): el sitio SOLO se sirve por https, así que la cookie de sesión lleva
# siempre la marca Secure y se manda HSTS. ⚠️ MEDIDO 11-nov-2026: sin esto la cookie salía SIN
# Secure, porque en Railway no se confía en X-Forwarded-Proto (no es DS_PROXY ni túnel).
# No ponerlo en la Mac: entrando por la IP de la red local (http://192.168.x) el navegador
# descartaría la cookie Secure y nadie podría iniciar sesión.
SOLO_HTTPS = os.environ.get('DS_HTTPS') == '1'


def _es_https():
    e = request.environ
    # Por el túnel de Cloudflare (llega desde esta Mac con CF-Connecting-IP) el https lo pone
    # Cloudflare: aquí llega en http, y X-Forwarded-Proto dice cómo entró el visitante.
    tunel = e.get('REMOTE_ADDR') in auth._LOCAL and e.get('HTTP_CF_CONNECTING_IP')
    return SOLO_HTTPS or e.get('wsgi.url_scheme') == 'https' or (
        (auth.DETRAS_DE_PROXY or tunel) and e.get('HTTP_X_FORWARDED_PROTO') == 'https')


_DESTINO_VALIDO = re.compile(r'/[A-Za-z0-9_\-/]*')


def _destino(valor):
    """A dónde volver tras entrar (?siguiente=/estacion). ⚠️ SOLO una ruta de ESTE sitio: un
    "https://otro" o "//otro" (el navegador lo lee como otro sitio) convertiría el enlace de
    entrada en un trampolín a una página falsa que pida la contraseña. Nada de '\\', '.', ':' ni
    '?': por eso una lista de lo permitido y no de lo prohibido."""
    v = valor if isinstance(valor, str) else ''
    if not _DESTINO_VALIDO.fullmatch(v) or v.startswith('//') or v in PUBLICAS:
        return '/'
    return v


def _abrir_sesion(usuario, siguiente='/'):
    response.set_cookie(auth.COOKIE, auth.emitir_sesion(usuario), max_age=auth.DURACION, path='/',
                        httponly=True, samesite='lax', secure=_es_https())
    redirect(_destino(siguiente))


def _pantalla(modo, mensaje='', usuario='', status=200):
    siguiente = _destino(request.params.getunicode('siguiente'))
    return HTTPResponse(body=auth.pagina(modo, mensaje, usuario, siguiente), status=status,
                        headers={'Content-Type': 'text/html; charset=utf-8'})


def _modo_sin_sesion():
    if auth.hay_cuentas():
        return 'entrar'
    return 'crear' if auth.es_esta_computadora(request.environ) else 'cerrado'


@app.get('/entrar')
def entrar_get():
    if auth.usuario_de(request.get_cookie(auth.COOKIE)):
        redirect(_destino(request.params.getunicode('siguiente')))
    return _pantalla(_modo_sin_sesion())


@app.post('/entrar')
def entrar_post():
    if not auth.hay_cuentas():
        return _pantalla(_modo_sin_sesion())
    usuario = (request.forms.getunicode('usuario') or '').strip().lower()
    err = auth.intentar_entrar(request.environ, usuario, request.forms.getunicode('clave') or '')
    if err:
        return _pantalla('entrar', err, usuario, 401)
    _abrir_sesion(usuario, request.forms.getunicode('siguiente'))


@app.post('/crear')
def crear_post():
    # Solo la PRIMERA cuenta, y solo desde esta computadora. Las demás las crea el dueño en /cuentas.
    if auth.hay_cuentas() or not auth.es_esta_computadora(request.environ):
        return _pantalla(_modo_sin_sesion(), 'No se puede crear la cuenta desde aquí.', status=403)
    usuario = (request.forms.getunicode('usuario') or '').strip().lower()
    clave = request.forms.getunicode('clave') or ''
    if clave != (request.forms.getunicode('clave2') or ''):
        return _pantalla('crear', 'Las dos contraseñas no son iguales.', usuario, 400)
    err = auth.crear_cuenta(usuario, clave)
    if err:
        return _pantalla('crear', err, usuario, 400)
    _abrir_sesion(usuario)


@app.post('/invitado')
def invitado_post():
    # Sin cuentas el servidor aún no tiene dueño: nada se abre antes de eso.
    if not auth.INVITADOS_ACTIVOS or not auth.hay_cuentas():
        return _pantalla(_modo_sin_sesion(), 'La prueba sin cuenta no está disponible.', status=403)
    # Con una sesión abierta no se reemplaza: otra página no puede sacarte de tu cuenta con un formulario.
    siguiente = _destino(request.forms.getunicode('siguiente'))
    if auth.usuario_de(request.get_cookie(auth.COOKIE)):
        redirect(siguiente)
    _limpiar_vencidos()
    cookie, usuario, err = auth.abrir_invitado(request.environ)
    if err:
        return _pantalla('entrar', err, status=429)
    # Sin max_age: la cookie muere al cerrar el navegador (y a las 2 horas, por dentro).
    response.set_cookie(auth.COOKIE, cookie, path='/', httponly=True, samesite='lax', secure=_es_https())
    redirect(siguiente)


def _limpiar_invitado(usuario):
    """Lo que un visitante deja en memoria y en temporales, además de su carpeta."""
    tmp = _CALCO.pop(usuario, {}).get('tmp')
    if tmp:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    nester.olvidar(usuario)
    _ESTACION_VIVA.pop(usuario, None)


def _limpiar_vencidos(todos=False):
    for u in auth.purgar_invitados(todos):
        _limpiar_invitado(u)


@app.get('/salir')
def salir():
    quien = auth.usuario_de(request.get_cookie(auth.COOKIE))
    if auth.es_invitado(quien):
        auth.cerrar_invitado(quien)
        _limpiar_invitado(quien)
    response.delete_cookie(auth.COOKIE, path='/')
    redirect('/entrar')


def _yo():
    return request.environ.get('ds.usuario')   # lo pone _guardia, que ya comprobó la sesión


def _sin_cache(html_, status=200):
    # no-store: la página puede llevar una contraseña temporal; que no quede en el historial.
    return HTTPResponse(body=html_, status=status, headers={'Content-Type': 'text/html; charset=utf-8',
                                                            'Cache-Control': 'no-store'})


@app.get('/clave')
def clave_get():
    if auth.es_invitado(_yo()):
        redirect('/')
    return _sin_cache(auth.pagina_clave(obligada=auth.debe_cambiar_clave(_yo())))


@app.post('/clave')
def clave_post():
    yo = _yo()
    if auth.es_invitado(yo):
        redirect('/')
    nueva = request.forms.getunicode('nueva') or ''
    if nueva != (request.forms.getunicode('nueva2') or ''):
        err = 'Las dos contraseñas nuevas no son iguales.'
    else:
        err = auth.cambiar_clave(request.environ, yo, request.forms.getunicode('actual') or '', nueva)
    if err:
        return _sin_cache(auth.pagina_clave(err, auth.debe_cambiar_clave(yo)), 400)
    _abrir_sesion(yo)   # cambiar la contraseña invalida las sesiones: esta sigue con una nueva


def _pagina_error(titulo, texto):
    return auth._marco(titulo, titulo, texto, '<p class="pie"><a href="/">Volver a Design Studio</a></p>')


def _solo_dueno():
    if not auth.es_dueno(_yo()):
        raise HTTPResponse(body=_pagina_error('Solo para el dueño', 'Esta página es de la cuenta del dueño del taller.'),
                           status=403, headers={'Content-Type': 'text/html; charset=utf-8'})


# Errores en español y con salida. Antes salía la página genérica de bottle en inglés ("Error:
# 404 Not Found") y, en /api, un HTML que la interfaz no sabía leer (aviso críptico o nada).
_ERRORES = {
    404: ('Esa página no existe', 'La dirección no lleva a ningún lado. Puede que el enlace esté mal escrito.',
          'Esa función no existe en el servidor.'),
    405: ('Esa página no existe', 'La dirección no se puede abrir así.', 'Esa función no admite ese tipo de pedido.'),
    500: ('Algo falló en el servidor', 'No fue culpa tuya. Inténtalo de nuevo en un momento; si se repite, avísale a quien administra el taller.',
          'El servidor tuvo un problema. Inténtalo de nuevo.'),
}


def _anotar_error(err):
    """Un 500 deja rastro en <datos>/errores.log (hora, ruta, cuenta y la traza). Sin esto solo
    quedaba lo que Railway guarde en sus registros, y ahí nadie mira hasta que un cliente se queja."""
    try:
        p = os.path.join(auth.DATOS, 'errores.log')
        if os.path.exists(p) and os.path.getsize(p) > 300_000:      # que no crezca sin fin
            os.replace(p, p + '.viejo')
        with open(p, 'a', encoding='utf-8') as f:
            f.write('\n=== %s  %s %s  cuenta=%s  build=%s\n%s\n' % (
                time.strftime('%Y-%m-%d %H:%M:%S'), request.method, request.path,
                'invitado' if auth.es_invitado(_yo()) else (_yo() or '-'), BUILD,
                (getattr(err, 'traceback', None) or str(getattr(err, 'exception', '') or err.body))[:6000]))
    except Exception:
        pass


def _error(err):
    titulo, texto, corto = _ERRORES.get(err.status_code, _ERRORES[500])
    if err.status_code >= 500:
        _anotar_error(err)
    if request.path.startswith('/api/'):
        response.content_type = 'application/json; charset=utf-8'
        return json.dumps({'ok': False, 'error': corto})
    response.content_type = 'text/html; charset=utf-8'
    return _pagina_error(titulo, texto)


for _cod in _ERRORES:
    app.error(_cod)(_error)


@app.get('/cuentas')
def cuentas_get():
    _solo_dueno()
    return _sin_cache(auth.pagina_cuentas())


@app.post('/cuentas')
def cuentas_post():
    _solo_dueno()
    accion = request.forms.getunicode('accion')
    usuario = (request.forms.getunicode('usuario') or '').strip().lower()
    clave, err = None, None
    if accion == 'alta':
        clave, err = auth.alta(usuario)
    elif accion == 'restablecer':
        clave, err = auth.restablecer_clave(usuario)
    elif accion in ('activar', 'desactivar'):
        err = auth.poner_activa(usuario, accion == 'activar')
    else:
        err = 'Acción desconocida.'
    return _sin_cache(auth.pagina_cuentas(err or '', usuario, clave or ''), 400 if err else 200)


# ── Apps instalables (PWA) y actualización automática ─────────────────────────────────────
# Hay DOS apps en el mismo sitio: el editor ("/") y la estación de corte ("/estacion"), cada
# una con su manifiesto, su `id` y su logo (iconos/, generados por web/crear_iconos_pwa.py).
#
# ⚠️ A propósito NO hay service worker que guarde copias: la app necesita al servidor para
# todo, y una copia guardada es justo lo que deja a un teléfono con la versión VIEJA. La
# actualización va así: las páginas se sirven con `no-cache` (el navegador pregunta siempre) y
# cada una compara `BUILD` contra el suyo — si cambió, se recarga sola (la estación, cuando no
# está cortando; el editor, si no hay diseño abierto, y si lo hay ofrece un botón).
def _build():
    import hashlib
    h = hashlib.sha256()
    for n in sorted(os.listdir(HERE)):
        if n.endswith(('.py', '.html', '.js')):
            try:
                with open(os.path.join(HERE, n), 'rb') as f:
                    h.update(n.encode() + f.read())
            except OSError:
                pass
    return h.hexdigest()[:12]


BUILD = _build()   # cambia con cada despliegue (el servidor arranca de nuevo)

_ICONOS = lambda n: [  # noqa: E731
    {'src': f'/iconos/{n}-192.png', 'sizes': '192x192', 'type': 'image/png'},
    {'src': f'/iconos/{n}-512.png', 'sizes': '512x512', 'type': 'image/png'},
    {'src': f'/iconos/{n}-maskable-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'}]
MANIFIESTOS = {
    '/manifest.webmanifest': {
        'id': '/', 'start_url': '/', 'scope': '/', 'name': 'Design Studio', 'short_name': 'Studio',
        'description': 'Diseña y corta en plotter o CNC.', 'lang': 'es', 'display': 'standalone',
        'background_color': '#EDEEF1', 'theme_color': '#D11E68', 'icons': _ICONOS('studio')},
    '/estacion.webmanifest': {
        'id': '/estacion', 'start_url': '/estacion', 'scope': '/estacion', 'name': 'Estación de corte',
        'short_name': 'Estación', 'description': 'La fila de corte del taller, junto al plotter.',
        'lang': 'es', 'display': 'standalone', 'background_color': '#171A20', 'theme_color': '#171A20',
        'icons': _ICONOS('estacion')},
}


def _manifiesto():
    return HTTPResponse(body=json.dumps(MANIFIESTOS[request.path], ensure_ascii=False),
                        headers={'Content-Type': 'application/manifest+json; charset=utf-8',
                                 'Cache-Control': 'no-cache'})


for _ruta in MANIFIESTOS:
    app.get(_ruta)(_manifiesto)


@app.get('/iconos/<nombre:re:[a-z0-9-]+\\.(?:png|ico)>')
def icono(nombre):
    return static_file(nombre, root=os.path.join(HERE, 'iconos'))


@app.get('/health')
def health():
    """Para Railway (railway.json): ¿el servidor contesta? Público y sin datos de nadie."""
    return _json({'ok': True, 'build': BUILD})


@app.get('/favicon.ico')
def favicon():
    return static_file('studio.ico', root=os.path.join(HERE, 'iconos'))


@app.get('/')
def index():
    r = static_file('studio_ui.html', root=HERE)
    r.set_header('Cache-Control', 'no-cache')   # que el navegador pregunte SIEMPRE si cambió
    return r


@app.get('/three.bundle.js')
def three_bundle():
    return static_file('three.bundle.js', root=HERE)


@app.get('/api/workarea')
def api_workarea():
    return _json({'work': _workarea(), 'cut': load_cut()})


@app.post('/api/set_cut')
def api_set_cut():
    return _json(set_cut(request.json or {}))


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


_CALCO = {}   # cuenta → la imagen que su calco está usando ahora


def _calco():
    return _CALCO.setdefault(_yo(), {})


@app.post('/api/trace_upload')
def api_trace_upload():
    up = request.files.get('file')
    if up is None:
        return _json({'ok': False, 'error': 'No llegó ninguna imagen.'}, 400)
    ext = os.path.splitext(up.filename or 'img')[1].lower() or '.png'
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tmp.close()
    up.save(tmp.name, overwrite=True)
    est = _calco()
    r = tracer.set_source(tmp.name, est)
    # El calco relee la imagen en cada ajuste, así que esta se queda; la ANTERIOR ya no
    # la usa nadie. Sin esto cada imagen subida se quedaba en el disco para siempre.
    if r.get('ok'):
        sobra, est['tmp'] = est.get('tmp'), tmp.name
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
    return _json(tracer.trace(request.json or {}, _calco()))


@app.get('/api/fonts')
def api_fonts():
    return _json(texter.list_fonts())


def _fuente_http(datos, tipo):
    """Una fuente (o su muestra) para el navegador. Solo sale lo que está en la lista de fuentes:
    el índice lo resuelve text_vector contra esa lista, nunca una ruta que mande el cliente."""
    if not datos:
        return HTTPResponse(status=404, body='')
    return HTTPResponse(body=datos, status=200, headers={
        'Content-Type': tipo, 'Cache-Control': 'private, max-age=604800'})


@app.get('/api/font_muestra')
def api_font_muestra():
    return _fuente_http(texter.font_sample(request.query.get('i')), 'font/woff')


@app.get('/api/font_archivo')
def api_font_archivo():
    datos, tipo = texter.font_file(request.query.get('i'))
    return _fuente_http(datos, tipo or 'font/ttf')


@app.post('/api/text')
def api_text():
    d = request.json or {}
    # Solo fuentes de la lista: si no, se le podía pasar CUALQUIER archivo del servidor como
    # "fuente" y, por el mensaje de error, saber si existe.
    lista = texter.list_fonts().get('fonts') or []
    if d.get('path') not in {f.get('path') for f in lista}:
        return _json({'ok': False, 'error': 'Esa fuente no está en la lista de fuentes.'})
    return _json(texter.text_paths(d))


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


SIN_ACOMODO = 'En la prueba sin cuenta se corre un acomodo a la vez: espera a que termine.'


@app.post('/api/nest')
def api_nest():
    if auth.es_invitado(_yo()):   # este camino no se puede contar: en la prueba solo va nest_start
        return _json({'ok': False, 'error': SIN_ACOMODO})
    return _json(nester.nest_op(request.json or {}))


@app.post('/api/nest_start')
def api_nest_start():
    if auth.es_invitado(_yo()) and nester.en_marcha(_yo()):
        return _json({'ok': False, 'error': SIN_ACOMODO})
    return _json(nester.nest_start(request.json or {}, _yo()))


@app.post('/api/nest_status')
def api_nest_status():
    return _json(nester.nest_status(request.json or {}, _yo()))


# ⚠️ PyMuPDF (exportar PDF/PNG/JPG, abrir .ai) NO aguanta dos hilos a la vez: lo dice su documentación y
# el fallo puede tumbar TODO el servidor, no solo ese pedido. Va de uno en uno.
_PYMUPDF = threading.Lock()


@app.post('/api/export')
def api_export():
    """Devuelve el archivo YA GENERADO como descarga (no JSON: son binarios y pesan)."""
    d = request.json or {}
    # PNG y JPG también: se generan a partir del PDF.
    with (contextlib.nullcontext() if d.get('format') in ('svg', 'dxf') else _PYMUPDF):
        r = exporter.export_bytes(d.get('format'), d)
    if not r.get('ok'):
        return _json(r)
    tipos = {'png': 'image/png', 'jpg': 'image/jpeg', 'pdf': 'application/pdf',
             'svg': 'image/svg+xml', 'dxf': 'application/dxf'}
    # Sin comillas ni saltos de línea: el nombre va dentro de una cabecera de la respuesta.
    base = re.sub(r'[^\w .()-]', '_', str(d.get('name') or 'diseno').rsplit('.', 1)[0])[:80].strip() or 'diseno'
    name = base + '.' + r['ext']
    return HTTPResponse(body=r['bytes'], status=200, headers={
        'Content-Type': tipos.get(r['ext'], 'application/octet-stream'),
        'Content-Disposition': f'attachment; filename="{name}"'})


# La versión web no se instala: siempre es la que corre el servidor. De aquí salen la huella
# `build` (con la que cada página sabe si quedó vieja y debe recargarse) y los datos del menú de
# cuenta. Las rutas update_start/status/apply del escritorio se borraron el 12-nov-2026.
@app.get('/api/update_check')
def api_update_check():
    return _json({'ok': True, 'web': True, 'newer': False, 'build': BUILD,
                  'usuario': _yo(), 'dueno': auth.es_dueno(_yo()), 'invitado': auth.es_invitado(_yo())})


@app.post('/api/autosave_save')
def api_autosave_save():
    if auth.es_invitado(_yo()):
        return _json({'ok': True})   # la prueba sin cuenta no deja nada guardado
    from studio_backend import autosave_save as f
    return _json(f(request.json or {}))


@app.get('/api/autosave_load')
def api_autosave_load():
    if auth.es_invitado(_yo()):
        return _json({'ok': True, 'exists': False})
    from studio_backend import autosave_load as f
    return _json(f())


@app.post('/api/autosave_clear')
def api_autosave_clear():
    if auth.es_invitado(_yo()):
        return _json({'ok': True})
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
        with (_PYMUPDF if ext == '.ai' else contextlib.nullcontext()):
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



# ── Estación de corte (estacion.py): un Android fijo en el taller corta lo que le manden ──
def _motor_plotter():
    """El <script id="motor-plotter"> de studio_ui.html, tal cual: la estación corta con el
    MISMO motor (y el mismo driver FTDI de Android) que la app, sin una segunda copia."""
    with open(os.path.join(HERE, 'studio_ui.html'), encoding='utf-8') as f:
        m = re.search(r'<script id="motor-plotter">[\s\S]*?</script>', f.read())
    return m.group(0) if m else ''


@app.get('/estacion')
def estacion_pagina():
    with open(os.path.join(HERE, 'estacion.html'), encoding='utf-8') as f:
        pagina = f.read()
    # Una prueba se llama "invitado:<vence>-<hex>": en pantalla solo "prueba sin cuenta".
    invitado = auth.es_invitado(_yo())
    quien = 'prueba sin cuenta' if invitado else (_yo() or '')
    fila = ('Fila solo de este navegador' if invitado
            else 'Estación del taller: recibe de todas las cuentas')
    return _sin_cache(pagina.replace('<!--MOTOR-PLOTTER-->', _motor_plotter())
                            .replace('{{FILA}}', fila)
                            .replace('{{USUARIO}}', html.escape(quien)))


def _fila_de_estacion():
    """UNA estación del taller para todas las cuentas (en la carpeta común de datos); una prueba
    sin cuenta, su fila chica en su carpeta temporal. ⚠️ Toda ruta de la estación pasa por aquí."""
    if auth.es_invitado(_yo()):
        return os.path.dirname(core._config_path())
    return os.path.join(auth.DATOS, 'taller')


@app.post('/api/estacion/mandar')
def api_estacion_mandar():
    try:
        data = request.json or {}
        hpgl = build_hpgl(data)   # el MISMO que corta el escritorio
    except Exception as e:
        return _json({'ok': False, 'error': f'No se pudo generar el HPGL: {e}'})
    invitado = auth.es_invitado(_yo())
    with estacion.en(_fila_de_estacion()):
        return _json(estacion.mandar(hpgl, data.get('nombre'), invitado=invitado,
                                     de='' if invitado else _yo()))


@app.get('/api/estacion/fila')
def api_estacion_fila():
    with estacion.en(_fila_de_estacion()):
        return _json({**estacion.fila(), 'build': BUILD})


# Latido de la estación: cada vez que la página de la estación pide la fila (cada 5 s) dice si
# tiene el plotter conectado. Vive en MEMORIA (un reinicio lo borra y la estación lo repone en
# segundos). La llave es la FILA, no la cuenta: 'taller' para todas, o el invitado para la suya
# (⚠️ esa se limpia en _limpiar_invitado). "Viva" = la página está abierta, NO que haya alguien.
_ESTACION_VIVA = {}
ESTACION_CADUCA = 20.0   # s sin latido = ya no hay estación (pregunta cada 5)


def _llave_estacion():
    return _yo() if auth.es_invitado(_yo()) else 'taller'


@app.post('/api/estacion/fila')
def api_estacion_fila_latido():
    _ESTACION_VIVA[_llave_estacion()] = (time.time(), bool((request.json or {}).get('plotter')))
    return api_estacion_fila()


@app.get('/api/estacion/estado')
def api_estacion_estado():
    """Para el botón de envío del editor: ¿hay estación abierta?, ¿con plotter?, ¿cuántos esperan?"""
    t, plotter = _ESTACION_VIVA.get(_llave_estacion(), (0.0, False))
    viva = time.time() - t < ESTACION_CADUCA
    with estacion.en(_fila_de_estacion()):
        pend = sum(1 for x in estacion.fila()['trabajos'] if x.get('estado') == 'pendiente')
    return _json({'ok': True, 'viva': viva, 'plotter': viva and plotter, 'pendientes': pend})


def _estacion(f, *campos):
    d = request.json or {}
    with estacion.en(_fila_de_estacion()):
        return _json(f(*[d.get(c) for c in campos]))


@app.post('/api/estacion/tomar')
def api_estacion_tomar():
    return _estacion(estacion.tomar, 'id')


@app.post('/api/estacion/terminar')
def api_estacion_terminar():
    return _estacion(estacion.terminar, 'id', 'resultado', 'detalle')


@app.post('/api/estacion/quitar')
def api_estacion_quitar():
    return _estacion(estacion.quitar, 'id')


@app.post('/api/estacion/vista')
def api_estacion_vista():
    return _estacion(estacion.vista, 'id')


@app.get('/api/test_square')
def api_test_square():
    # Para el navegador que maneja el plotter él mismo (Web Serial): solo pide el HPGL.
    hpgl = test_square_hpgl(10)
    return _json({'ok': True, 'hpgl': hpgl, 'lines': hpgl.count('\n') + 1, 'bytes': len(hpgl)})


# ── Plotter conectado AL SERVIDOR (apagado por defecto: ver PLOTTER_EN_SERVIDOR) ──
def _plotter(f, *a):
    return _json(f(*a) if PLOTTER_EN_SERVIDOR else {'ok': False, 'error': SIN_PLOTTER})


@app.get('/api/ports')
def api_ports():
    if not PLOTTER_EN_SERVIDOR:
        return _json({'ok': True, 'ports': [], 'items': [], 'has_serial': False, 'aviso': SIN_PLOTTER})
    return _json(SERVICE.ports())

@app.get('/api/status')
def api_status():
    if not PLOTTER_EN_SERVIDOR:
        return _json({'ok': True, 'connected': False, 'port': None, 'has_serial': False,
                      'last_port': None, 'last_baud': None, 'aviso': SIN_PLOTTER})
    return _json(SERVICE.status())

@app.post('/api/connect')
def api_connect():
    d = request.json or {}
    return _plotter(SERVICE.connect, d.get('port'), d.get('baud', 9600))

@app.post('/api/disconnect')
def api_disconnect():
    return _plotter(SERVICE.disconnect)

@app.post('/api/jog')
def api_jog():
    d = request.json or {}
    return _plotter(SERVICE.jog, d.get('direction'), d.get('dist', 1))

@app.post('/api/pen')
def api_pen():
    d = request.json or {}
    return _plotter(SERVICE.pen, bool(d.get('down')))

@app.post('/api/command')
def api_command():
    d = request.json or {}
    return _plotter(SERVICE.command, d.get('which'))

@app.post('/api/send')
def api_send():
    return _plotter(SERVICE.send_design, request.json or {})

@app.get('/api/send_progress')
def api_send_progress():
    return _plotter(SERVICE.progress)

@app.post('/api/cancel')
def api_cancel():
    return _plotter(SERVICE.cancel)

@app.post('/api/testcut')
def api_testcut():
    return _plotter(SERVICE.test_cut)


def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


PUBLICAS = ('/entrar', '/crear', '/salir', '/invitado',
            # el manifiesto y los iconos los pide el navegador SIN cookie (y antes de entrar)
            '/manifest.webmanifest', '/estacion.webmanifest', '/favicon.ico', '/health')
# Lo que la cuenta del dueño hereda de cuando no había cuentas (se copia, no se mueve).
HEREDA_EL_DUENO = ('plotter_config.json', 'cnc_config.json', 'autosave.dstudio')
SEGURIDAD = [('X-Content-Type-Options', 'nosniff'),   # el navegador no "adivina" tipos de archivo
             ('X-Frame-Options', 'DENY'),             # nadie puede meter la app dentro de otra página
             ('Referrer-Policy', 'same-origin')]


def _guardia(wsgi):
    """Antes de bottle: sin sesión válida no se llega a NINGUNA ruta (salvo entrar/salir).
    Va por fuera de bottle para que ninguna ruta nueva se quede sin protección por olvido.
    Aquí también se fija la carpeta de datos de la cuenta, por la misma razón: ninguna ruta
    tiene que acordarse de pedirla, y por lo tanto ninguna puede olvidarlo."""
    def con_guardia(environ, start_response):
        def responder(status, headers, exc_info=None):
            return start_response(status, list(headers) + SEGURIDAD + (
                [('Strict-Transport-Security', 'max-age=15552000')] if SOLO_HTTPS else []), exc_info)

        def corto(status, tipo, cuerpo, extra=()):
            responder(status, [('Content-Type', tipo), ('Content-Length', str(len(cuerpo)))] + list(extra))
            return [cuerpo]

        ruta = environ.get('PATH_INFO') or '/'
        carpeta = None
        if ruta not in PUBLICAS and not ruta.startswith('/iconos/'):
            try:
                c = http.cookies.SimpleCookie(environ.get('HTTP_COOKIE') or '')
                token = c[auth.COOKIE].value if auth.COOKIE in c else None
            except http.cookies.CookieError:
                token = None
            usuario = auth.usuario_de(token)
            if not usuario:
                if ruta.startswith('/api/'):
                    return corto('401 Unauthorized', 'application/json; charset=utf-8', json.dumps(
                        {'ok': False, 'login': True, 'error': 'Tu sesión terminó: vuelve a entrar.'}).encode('utf-8'))
                # Que al entrar vuelva a donde iba (la estación del taller, sobre todo).
                destino = '/entrar' + (f'?siguiente={ruta}' if ruta != '/' and _destino(ruta) == ruta
                                       and environ.get('REQUEST_METHOD') == 'GET' else '')
                return corto('302 Found', 'text/plain', b'', [('Location', destino)])
            environ['ds.usuario'] = usuario
            # Contraseña temporal: nada funciona hasta cambiarla.
            if ruta != '/clave' and auth.debe_cambiar_clave(usuario):
                if ruta.startswith('/api/'):
                    return corto('401 Unauthorized', 'application/json; charset=utf-8', json.dumps(
                        {'ok': False, 'login': True, 'error': 'Primero cambia tu contraseña temporal.'}).encode('utf-8'))
                return corto('302 Found', 'text/plain', b'', [('Location', '/clave')])
            carpeta = auth.carpeta_de(usuario, core._config_compartida().parent, HEREDA_EL_DUENO)
        try:
            largo = int(environ.get('CONTENT_LENGTH') or 0)
        except ValueError:
            largo = 0
        if largo > LIMITE:
            return corto('413 Request Entity Too Large', 'application/json; charset=utf-8', json.dumps(
                {'ok': False, 'error': f'Es demasiado grande (más de {LIMITE // 1048576} MB).'}).encode('utf-8'))
        ficha = core._CARPETA_USUARIO.set(carpeta)
        try:
            return wsgi(environ, responder)
        finally:
            core._CARPETA_USUARIO.reset(ficha)   # el hilo atenderá a otra cuenta después
    return con_guardia


def _servir(wsgi):
    """Atiende a varios a la vez: si no, el acomodo largo de uno congela a todos.
    waitress (para internet) si está instalado; si no, la versión simple de Python, que basta en
    la Mac. La auditoría corre con las dos."""
    try:
        from waitress import serve
    except ImportError:
        from socketserver import ThreadingMixIn
        from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server

        class Servidor(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        class Callado(WSGIRequestHandler):
            def log_message(self, *a):
                pass
        print('  (servidor: el simple de Python)')
        make_server('0.0.0.0', PORT, wsgi, server_class=Servidor, handler_class=Callado).serve_forever()
        return
    print('  (servidor: waitress)')
    # ⚠️ clear_untrusted_proxy_headers=False: por defecto waitress BORRA X-Forwarded-For, y sin esa
    # cabecera web_auth cree que el visitante está en esta computadora: alguien de fuera podría
    # crear la cuenta del dueño, y detrás de un proxy el bloqueo por fallos sería uno para todos.
    serve(wsgi, host='0.0.0.0', port=PORT, threads=8, max_request_body_size=LIMITE,
          clear_untrusted_proxy_headers=False)


def main():
    import threading
    threading.Thread(target=texter.list_fonts, daemon=True).start()   # calienta el caché de fuentes
    _limpiar_vencidos(todos=True)   # reiniciar borra las pruebas que hubieran quedado

    def barrer():
        while True:
            time.sleep(600)
            _limpiar_vencidos()
    threading.Thread(target=barrer, daemon=True).start()
    ip = _lan_ip()
    print(f"Design Studio en:")
    print(f"  · esta Mac:        http://localhost:{PORT}")
    print(f"  · otros dispositivos (misma red): http://{ip}:{PORT}")
    _servir(_guardia(app))


if __name__ == '__main__':
    main()
