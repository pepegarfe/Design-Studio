"""La fila de la ESTACIÓN DE CORTE (versión web).

Un teléfono Android viejo queda fijo en el taller, enchufado al plotter, con /estacion abierta
en Chrome. Desde cualquier lado se "manda a la estación" un diseño: el servidor arma el HPGL
(el MISMO build_hpgl del escritorio) y lo deja aquí. La estación pregunta cada pocos segundos,
AVISA y espera a que alguien toque "Cortar": el plotter nunca arranca sin nadie mirando
(decisión de Jose, 5-nov-2026: alguien tiene que poner el material).

Cada cuenta tiene SU fila, en su carpeta (`core._config_path()`): la estación entra con una
cuenta y solo ve los trabajos de esa cuenta. Una prueba sin cuenta tiene una fila chica
(TOPES_INVITADO) en su carpeta temporal: solo la ve ESE navegador (la prueba es su cookie).

Estados: pendiente → cortando → hecho | error | cancelado. "hecho" quiere decir ENVIADO
entero al plotter; el 721 sigue cortando lo que guardó en su memoria.
"""
import json
import re
import time
import uuid
from pathlib import Path

import plotter_control as core
from studio_backend import _en_fila, _escribir

MAX_PENDIENTES = 30                 # una fila más larga es un error, no un taller
MAX_HISTORIAL = 20                  # terminados que se recuerdan (los más recientes)
MAX_BYTES = 20 * 1024 * 1024        # un trabajo (un diseño grande real: 1–5 MB de HPGL)
MAX_BYTES_FILA = 100 * 1024 * 1024  # lo que puede ocupar la fila de una cuenta en el disco
# "Probar sin cuenta" es PÚBLICO (hasta 20 pruebas a la vez): su fila es más chica, para que
# nadie llene el disco abriendo pruebas. Vive en la carpeta temporal de la prueba y se borra con ella.
TOPES_INVITADO = {'pendientes': 5, 'bytes': 5 * 1024 * 1024, 'fila': 20 * 1024 * 1024}
ID_VALIDO = re.compile(r'^[0-9a-f]{12}$')   # el id es un nombre de archivo: nada de '..' ni '/'
TERMINALES = ('hecho', 'error', 'cancelado')


def _rutas():
    base = Path(core._config_path())
    return base.with_name('estacion.json'), base.with_name('estacion')


def _leer():
    indice, _ = _rutas()
    try:
        d = json.loads(indice.read_text(encoding='utf-8'))
        return d if isinstance(d.get('trabajos'), list) else {'trabajos': []}
    except (OSError, ValueError):
        return {'trabajos': []}


def _guardar(d):
    indice, carpeta = _rutas()
    carpeta.mkdir(parents=True, exist_ok=True)
    _escribir(indice, json.dumps(d, ensure_ascii=False, indent=1))


def _archivo(i):
    return _rutas()[1] / f'{i}.hpgl'


def _podar(d):
    """Olvida los terminados viejos (y borra su HPGL) para que la fila no crezca sin fin."""
    terminados = [t for t in d['trabajos'] if t['estado'] in TERMINALES]
    terminados.sort(key=lambda t: t.get('actualizado', 0), reverse=True)
    sobran = {t['id'] for t in terminados[MAX_HISTORIAL:]}
    for i in sobran:
        _archivo(i).unlink(missing_ok=True)
    d['trabajos'] = [t for t in d['trabajos'] if t['id'] not in sobran]


def _publico(t):
    return {k: t.get(k) for k in ('id', 'nombre', 'estado', 'creado', 'actualizado',
                                  'lineas', 'bytes', 'detalle', 'ancho_mm', 'alto_mm')}


def _trazos(hpgl):
    """Los trazos que la cuchilla va a cortar, leídos del MISMO HPGL que irá al plotter (en
    unidades HPGL, 40 = 1 mm). 'PU;' sin coordenadas levanta y el siguiente PD sigue desde ahí:
    así fuerza esquinas build_hpgl."""
    trazos, cur, x, y = [], None, 0.0, 0.0
    for cmd in hpgl.replace('\n', '').split(';'):
        c = cmd.strip()
        if len(c) < 2:
            continue
        op = c[:2].upper()
        nums = [float(v) for v in re.findall(r'-?\d+(?:\.\d+)?', c[2:])]
        pts = list(zip(nums[0::2], nums[1::2]))
        if op == 'PU':
            cur = None
            if pts:
                x, y = pts[-1]
        elif op == 'PD':
            if cur is None:
                cur = [(x, y)]
                trazos.append(cur)
            for p in pts:
                cur.append(p)
                x, y = p
    return [t for t in trazos if len(t) > 1]


def _medidas(trazos):
    xs = [p[0] for t in trazos for p in t]
    ys = [p[1] for t in trazos for p in t]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def vista(i, max_puntos=4000):
    """Dibujo del trabajo para la pantalla de la estación: un 'd' de SVG en mm, con la Y hacia
    abajo como en pantalla. Se aligera a ~max_puntos: es para reconocer el diseño, no para cortar."""
    t = _buscar(_leer(), i)
    if not t:
        return {'ok': False, 'error': 'Ese trabajo ya no existe.'}
    try:
        trazos = _trazos(_archivo(t['id']).read_text(encoding='utf-8'))
    except OSError:
        return {'ok': False, 'error': 'Se perdió el archivo de ese trabajo.'}
    m = _medidas(trazos)
    if not m:
        return {'ok': True, 'ancho_mm': 0, 'alto_mm': 0, 'd': ''}
    x0, y0, x1, y1 = m
    total = sum(len(tr) for tr in trazos)
    paso = max(1, -(-total // max_puntos))
    partes = []
    for tr in trazos:
        pts = tr[::paso]
        if pts[-1] != tr[-1]:
            pts.append(tr[-1])
        partes.append('M' + ' L'.join(f'{(px - x0) / 40:.1f} {(y1 - py) / 40:.1f}' for px, py in pts))
    return {'ok': True, 'ancho_mm': round((x1 - x0) / 40, 1), 'alto_mm': round((y1 - y0) / 40, 1),
            'd': ' '.join(partes)}


def _buscar(d, i):
    if not isinstance(i, str) or not ID_VALIDO.match(i):
        return None
    return next((t for t in d['trabajos'] if t['id'] == i), None)


@_en_fila
def mandar(hpgl, nombre, invitado=False):
    max_pend, max_bytes, max_fila = ((TOPES_INVITADO['pendientes'], TOPES_INVITADO['bytes'],
                                      TOPES_INVITADO['fila']) if invitado
                                     else (MAX_PENDIENTES, MAX_BYTES, MAX_BYTES_FILA))
    if not isinstance(hpgl, str) or not hpgl.strip():
        return {'ok': False, 'error': 'El diseño está vacío: no hay nada que cortar.'}
    datos = hpgl.encode('utf-8')
    if len(datos) > max_bytes:
        return {'ok': False, 'error': f'El diseño es demasiado grande para la estación '
                                      f'(más de {max_bytes // 1048576} MB).'}
    d = _leer()
    pendientes = [t for t in d['trabajos'] if t['estado'] == 'pendiente']
    if len(pendientes) >= max_pend:
        return {'ok': False, 'error': f'La estación ya tiene {max_pend} trabajos esperando. '
                                      'Corta o descarta algunos primero.'}
    ocupado = sum(t.get('bytes', 0) for t in d['trabajos'])
    if ocupado + len(datos) > max_fila:
        return {'ok': False, 'error': 'La fila de la estación está llena. Descarta trabajos viejos.'}
    m = _medidas(_trazos(hpgl))
    if not m:
        return {'ok': False, 'error': 'El diseño no tiene ningún trazo que cortar.'}
    nombre = re.sub(r'\s+', ' ', str(nombre or '')).strip()[:80] or 'Diseño sin nombre'
    ahora = time.time()
    t = {'id': uuid.uuid4().hex[:12], 'nombre': nombre, 'estado': 'pendiente', 'creado': ahora,
         'actualizado': ahora, 'lineas': hpgl.count('\n') + 1, 'bytes': len(datos), 'detalle': '',
         'ancho_mm': round((m[2] - m[0]) / 40, 1), 'alto_mm': round((m[3] - m[1]) / 40, 1)}
    _rutas()[1].mkdir(parents=True, exist_ok=True)
    _archivo(t['id']).write_bytes(datos)
    d['trabajos'].append(t)
    _guardar(d)
    return {'ok': True, 'id': t['id'], 'pendientes': len(pendientes) + 1}


def fila():
    d = _leer()
    return {'ok': True, 'trabajos': [_publico(t) for t in d['trabajos']], 'ahora': time.time()}


@_en_fila
def tomar(i):
    """La estación va a cortar: le da el HPGL y lo marca 'cortando'. Solo un trabajo
    PENDIENTE se toma: si dos estaciones tocaran 'Cortar' a la vez, una sola lo consigue."""
    d = _leer()
    t = _buscar(d, i)
    if not t:
        return {'ok': False, 'error': 'Ese trabajo ya no existe.'}
    if t['estado'] != 'pendiente':
        return {'ok': False, 'error': f'Ese trabajo no está esperando (está "{t["estado"]}").'}
    try:
        hpgl = _archivo(t['id']).read_text(encoding='utf-8')
    except OSError:
        return {'ok': False, 'error': 'Se perdió el archivo de ese trabajo: mándalo otra vez.'}
    t['estado'], t['actualizado'], t['detalle'] = 'cortando', time.time(), ''
    _guardar(d)
    return {'ok': True, 'hpgl': hpgl, 'trabajo': _publico(t)}


@_en_fila
def terminar(i, resultado, detalle=''):
    """resultado: hecho | error | cancelado, o 'pendiente' para devolverlo a la fila (p. ej. si
    la estación se reinició a media corte y no se sabe si terminó)."""
    if resultado not in TERMINALES + ('pendiente',):
        return {'ok': False, 'error': 'Resultado desconocido.'}
    d = _leer()
    t = _buscar(d, i)
    if not t:
        return {'ok': False, 'error': 'Ese trabajo ya no existe.'}
    if t['estado'] != 'cortando' and not (resultado == 'pendiente' and t['estado'] in TERMINALES):
        return {'ok': False, 'error': f'Ese trabajo no se estaba cortando (está "{t["estado"]}").'}
    if resultado == 'pendiente' and not _archivo(t['id']).exists():
        return {'ok': False, 'error': 'Se perdió el archivo de ese trabajo: mándalo otra vez.'}
    t['estado'], t['actualizado'] = resultado, time.time()
    t['detalle'] = str(detalle or '')[:300]
    _podar(d)
    _guardar(d)
    return {'ok': True, 'trabajo': _publico(t)}


@_en_fila
def quitar(i):
    d = _leer()
    t = _buscar(d, i)
    if not t:
        return {'ok': False, 'error': 'Ese trabajo ya no existe.'}
    if t['estado'] == 'cortando':
        return {'ok': False, 'error': 'Se está cortando: deténlo primero desde la estación.'}
    _archivo(t['id']).unlink(missing_ok=True)
    d['trabajos'] = [x for x in d['trabajos'] if x['id'] != t['id']]
    _guardar(d)
    return {'ok': True}
