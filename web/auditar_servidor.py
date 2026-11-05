"""Fase 1: ¿el servidor web hace lo mismo que la app de escritorio?

Corre studio_server.py sobre una COPIA del proyecto (para no tocar la config real: fresas,
área de trabajo, autoguardado) y llama a cada ruta como lo haría el navegador. Donde se puede,
compara contra el motor llamado directo (el mismo que usa el escritorio).

Uso (desde la carpeta del proyecto; la copia se hace sola en una carpeta temporal):
    /opt/homebrew/bin/python3 web/auditar_servidor.py
⚠️ NUNCA apuntarlo a la carpeta real del proyecto: escribe config (área, fresas, autoguardado)."""
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid

import shutil
import tempfile
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.argv[0] = os.path.abspath(__file__)   # pywebview busca la carpeta del script al importarse
COPIA = tempfile.mkdtemp(prefix='ds_auditoria_')
for _n in os.listdir(_REPO):
    if _n.endswith(('.py', '.json', '.html', '.js')) or _n in ('version.txt',):
        shutil.copy2(os.path.join(_REPO, _n), COPIA)
shutil.copytree(os.path.join(_REPO, 'vendor'), os.path.join(COPIA, 'vendor'))
# Puerto PROPIO y libre: si se usara el 8765 y Jose tiene su servidor abierto, las pruebas le
# pegarían al SUYO (con su configuración real) sin darse cuenta. Pasó el 2-nov-2026.
import socket
with socket.socket() as _s:
    _s.bind(('127.0.0.1', 0))
    PUERTO = _s.getsockname()[1]
BASE = f'http://127.0.0.1:{PUERTO}'
sys.path.insert(0, COPIA)
os.chdir(COPIA)

resultados = []


def ok(cond, nombre, detalle=''):
    resultados.append((bool(cond), nombre, detalle))
    print(('OK    ' if cond else 'FALLA ') + nombre + (f'  — {detalle}' if detalle else ''))


# La sesión de la prueba: como un navegador, guarda la cookie al entrar y la manda siempre.
import http.client
import http.cookiejar
import urllib.parse
JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(JAR))


def http_crudo(metodo, ruta, cuerpo=None, cabeceras=None, cookie=None):
    """Un pedido SIN seguir redirecciones ni guardar cookies: para ver qué contesta de verdad."""
    c = http.client.HTTPConnection('127.0.0.1', PUERTO, timeout=60)
    h = dict(cabeceras or {})
    if cookie:
        h['Cookie'] = cookie
    c.request(metodo, ruta, body=cuerpo, headers=h)
    r = c.getresponse()
    out = (r.status, dict(r.getheaders()), r.read())
    c.close()
    return out


def formulario(ruta, campos, cabeceras=None, cookie=None):
    h = {'Content-Type': 'application/x-www-form-urlencoded'}
    h.update(cabeceras or {})
    return http_crudo('POST', ruta, urllib.parse.urlencode(campos).encode(), h, cookie)


def pedir(ruta, datos=None, archivo=None, crudo=False):
    url = BASE + ruta
    if archivo:
        nombre, contenido = archivo
        b = uuid.uuid4().hex
        cuerpo = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{nombre}"\r\n'
                  'Content-Type: application/octet-stream\r\n\r\n').encode() + contenido + f'\r\n--{b}--\r\n'.encode()
        req = urllib.request.Request(url, cuerpo, {'Content-Type': f'multipart/form-data; boundary={b}'})
    elif datos is not None:
        req = urllib.request.Request(url, json.dumps(datos).encode(), {'Content-Type': 'application/json'})
    else:
        req = urllib.request.Request(url)
    try:
        with OPENER.open(req, timeout=60) as r:
            cuerpo = r.read()
            if crudo:
                return r.headers.get('Content-Type', ''), cuerpo
            return json.loads(cuerpo)
    except urllib.error.HTTPError as e:
        return {'ok': False, 'error': f'HTTP {e.code}: {e.read()[:200]!r}'}


# ── archivos de muestra ────────────────────────────────────────────────────────
SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm" viewBox="0 0 100 50">
<rect x="10" y="10" width="30" height="20" fill="none" stroke="black"/>
<circle cx="70" cy="25" r="12" fill="none" stroke="black"/></svg>'''

import ezdxf
dxf_doc = ezdxf.new()
dxf_doc.modelspace().add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True)
_s = io.StringIO(); dxf_doc.write(_s); DXF = _s.getvalue().encode()

import fitz
pdf = fitz.open(); pg = pdf.new_page(width=200, height=100)
pg.draw_rect(fitz.Rect(20, 20, 120, 80), color=(0, 0, 0), width=1)
AI = pdf.tobytes()
img = fitz.open(); ip = img.new_page(width=200, height=200)
ip.draw_circle((100, 100), 60, color=(0, 0, 0), fill=(0, 0, 0))
PNG = ip.get_pixmap(dpi=72).tobytes('png')

# ── arrancar el servidor sobre la copia ───────────────────────────────────────
# Sus temporales van a una carpeta propia: así se puede contar si deja basura en el disco.
TEMPS = os.path.join(COPIA, '_temporales')
os.makedirs(TEMPS)
srv = subprocess.Popen([sys.executable, 'studio_server.py'], cwd=COPIA,
                       env=dict(os.environ, TMPDIR=TEMPS, DS_PORT=str(PUERTO),
                                DS_DATOS=os.path.join(COPIA, '_datos_web')),   # cuentas de la prueba, no las tuyas
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
for _ in range(60):
    if srv.poll() is not None:
        break   # el servidor de la prueba murió: no seguir contra quién sabe qué
    try:
        urllib.request.urlopen(BASE + '/entrar', timeout=1); break
    except Exception:
        time.sleep(0.25)
if srv.poll() is not None:
    print('FALLA el servidor de la prueba no arrancó:\n' + srv.stdout.read().decode(errors='replace')[-1500:])
    shutil.rmtree(COPIA, ignore_errors=True)
    sys.exit(1)

try:
    import plotter_control as core
    import design_studio as ds          # el camino del ESCRITORIO, para comparar


    # 0. SEGURIDAD (fase 3) — antes de entrar, nada se abre
    st, h, _ = http_crudo('GET', '/')
    ok(st == 302 and h.get('Location', '').endswith('/entrar'), 'sin sesión: la página manda a /entrar', f'{st} → {h.get("Location")}')
    for ruta, metodo in [('/api/workarea', 'GET'), ('/api/hpgl', 'POST'), ('/api/autosave_load', 'GET'), ('/three.bundle.js', 'GET'), ('/api/fonts', 'GET')]:
        st, h, cuerpo = http_crudo(metodo, ruta, b'{}' if metodo == 'POST' else None, {'Content-Type': 'application/json'})
        ok(st in (401, 302), f'sin sesión: {metodo} {ruta} → rechazado', str(st))
    st, h, cuerpo = http_crudo('GET', '/entrar')
    ok(st == 200 and b'Crea tu cuenta' in cuerpo, 'servidor nuevo, desde esta computadora: ofrece crear la cuenta del dueño')
    ok(h.get('X-Frame-Options') == 'DENY' and h.get('X-Content-Type-Options') == 'nosniff', 'cabeceras de seguridad en las respuestas')
    st, h, cuerpo = http_crudo('GET', '/entrar', cabeceras={'X-Forwarded-For': '203.0.113.9'})
    ok(b'Crea tu cuenta' not in cuerpo and b'sin cuentas' in cuerpo, 'servidor nuevo, desde FUERA: NO deja crear cuenta')
    st, h, cuerpo = formulario('/crear', {'usuario': 'intruso', 'clave': 'x' * 12, 'clave2': 'x' * 12}, {'X-Forwarded-For': '203.0.113.9'})
    ok(st == 403 and not os.path.exists(os.path.join(COPIA, '_datos_web', 'usuarios.json')), 'crear la cuenta desde fuera → prohibido (403) y no se crea nada')
    st, h, cuerpo = formulario('/crear', {'usuario': 'jose', 'clave': 'corta', 'clave2': 'corta'})
    ok(st == 400 and 'al menos 8'.encode() in cuerpo, 'contraseña corta → la rechaza')
    st, h, cuerpo = formulario('/crear', {'usuario': 'jose', 'clave': 'una-clave-larga', 'clave2': 'otra-clave-larga'})
    ok(st == 400 and 'no son iguales'.encode() in cuerpo, 'las dos contraseñas distintas → lo dice')
    st, h, cuerpo = formulario('/invitado', {})
    ok(st == 403 and not h.get('Set-Cookie'), 'servidor sin dueño: la prueba sin cuenta no se abre')
    CLAVE = 'prueba-' + uuid.uuid4().hex[:10]
    st, h, cuerpo = formulario('/crear', {'usuario': 'Jose', 'clave': CLAVE, 'clave2': CLAVE})
    galleta = (h.get('Set-Cookie') or '').split(';')[0]
    ok(st in (302, 303) and galleta.startswith('ds_sesion=') and 'HttpOnly' in (h.get('Set-Cookie') or '') and 'SameSite=lax' in (h.get('Set-Cookie') or ''),
       'crear la cuenta del dueño → entra, con cookie HttpOnly y SameSite', h.get('Set-Cookie', '')[:80])
    usuarios = json.load(open(os.path.join(COPIA, '_datos_web', 'usuarios.json'), encoding='utf-8'))
    ok(list(usuarios) == ['jose'] and CLAVE not in json.dumps(usuarios), 'la contraseña NO está guardada en el archivo (solo su huella)')
    st, h, cuerpo = formulario('/crear', {'usuario': 'otro', 'clave': CLAVE, 'clave2': CLAVE})
    ok(st == 403 and list(json.load(open(os.path.join(COPIA, '_datos_web', 'usuarios.json'), encoding='utf-8'))) == ['jose'],
       'ya con dueño: nadie más crea cuentas por /crear (ni desde esta computadora)')
    st, h, cuerpo = http_crudo('GET', '/api/workarea', cookie=galleta)
    ok(st == 200 and b'work' in cuerpo, 'con la sesión: el servidor responde')
    datos, firma = galleta.split('=', 1)[1].split('.', 1)
    falsa = 'ds_sesion=' + datos[:-2] + ('A' if datos[-2] != 'A' else 'B') + datos[-1] + '.' + firma
    ok(http_crudo('GET', '/api/workarea', cookie=falsa)[0] == 401, 'cookie alterada (una letra) → rechazada')
    import base64 as _b64m, hmac as _hm, hashlib as _hl
    trucha = _b64m.urlsafe_b64encode(json.dumps(['jose', 9999999999, 1]).encode()).decode().rstrip('=')
    ok(http_crudo('GET', '/api/workarea', cookie=f'ds_sesion={trucha}.{_b64m.urlsafe_b64encode(_hm.new(b"adivinada", trucha.encode(), _hl.sha256).digest()).decode().rstrip("=")}')[0] == 401,
       'cookie fabricada con otra llave → rechazada')
    st, h, cuerpo = formulario('/entrar', {'usuario': 'jose', 'clave': 'equivocada'})
    ok(st == 401 and 'incorrectos'.encode() in cuerpo and not h.get('Set-Cookie'), 'contraseña equivocada → no entra')
    st, h, cuerpo = formulario('/entrar', {'usuario': 'nadie', 'clave': 'equivocada'})
    ok(st == 401 and 'Usuario o contraseña incorrectos'.encode() in cuerpo, 'usuario que no existe → el MISMO mensaje (no delata quién existe)')
    st, h, cuerpo = formulario('/entrar', {'usuario': 'JOSE', 'clave': CLAVE})
    ok(st in (302, 303) and (h.get('Set-Cookie') or '').startswith('ds_sesion='), 'entrar con la contraseña correcta (usuario sin importar mayúsculas)')
    st, h, cuerpo = http_crudo('GET', '/salir', cookie=galleta)
    sc = h.get('Set-Cookie') or ''
    ok(st in (302, 303) and sc.startswith('ds_sesion=""') and '1970' in sc,
       'salir borra la cookie', sc[:80])

    # la sesión con la que corre el resto de la auditoría
    OPENER.open(urllib.request.Request(BASE + '/entrar', urllib.parse.urlencode({'usuario': 'jose', 'clave': CLAVE}).encode()), timeout=30).read()
    ok(pedir('/api/workarea').get('work'), 'la auditoría entra con su cuenta de prueba')

    # huecos cerrados
    r = pedir('/api/text', {'text': 'Hola', 'path': '/etc/passwd', 'size': 20})
    ok(r.get('ok') is False and 'lista de fuentes' in (r.get('error') or ''), 'texto con un archivo cualquiera como "fuente" → rechazado sin leerlo', r.get('error'))
    r = pedir('/api/update_start', {'url': 'https://example.com/lo-que-sea.zip'})
    ok(r.get('ok') is False and 'versión web' in (r.get('error') or ''), 'descargar una actualización de cualquier dirección → rechazado', r.get('error'))
    ok(pedir('/api/update_apply', {'job': 'x'}).get('ok') is False, 'instalar una actualización (reemplazar el programa) → rechazado')
    r = pedir('/api/update_check')
    ok(r.get('web') and r.get('newer') is False, 'buscar actualizaciones → "versión web, siempre la más reciente"')
    r = pedir('/api/connect', {'port': '/dev/cu.usbserial-AO004NFH', 'baud': 9600})
    ok(r.get('ok') is False and 'Chrome o Edge' in (r.get('error') or ''), 'el servidor ya NO abre puertos serie (plotter solo por el navegador)', r.get('error'))
    s = pedir('/api/status')
    ok(s.get('has_serial') is False and 'Chrome o Edge' in (s.get('aviso') or ''), 'y el aviso dice qué hacer, no "pyserial no disponible"')
    ct, cuerpo = pedir('/api/export', {'format': 'svg', 'paths': [[[0, 0], [1, 1]]], 'name': 'mal"\r\nX-Inyectada: 1'}, crudo=True)
    st, h, _ = http_crudo('POST', '/api/export', json.dumps({'format': 'svg', 'paths': [[[0, 0], [1, 1]]], 'name': 'mal"\r\nX-Inyectada: 1'}).encode(),
                          {'Content-Type': 'application/json'}, cookie='; '.join(f'{c.name}={c.value}' for c in JAR))
    ok(st == 200 and 'X-Inyectada' not in h and '"' not in h.get('Content-Disposition', '').split('filename=')[1].strip('"'),
       'nombre de exportación con comillas y saltos de línea → limpiado', h.get('Content-Disposition'))
    st, h, cuerpo = http_crudo('POST', '/api/hpgl', b'x', {'Content-Type': 'application/json', 'Content-Length': str(65 * 1024 * 1024)},
                               cookie='; '.join(f'{c.name}={c.value}' for c in JAR))
    ok(st == 413, 'un pedido de más de 64 MB → rechazado antes de leerlo', str(st))

    # 1. la página y sus piezas
    ct, html = pedir('/', crudo=True)
    ok(b'<html' in html.lower()[:500] or b'<!doctype' in html.lower()[:200], 'la página principal carga', f'{len(html)//1024} KB')
    ct, three = pedir('/three.bundle.js', crudo=True)
    ok(len(three) > 100_000, 'la vista 3D (three.bundle.js) carga', f'{len(three)//1024} KB')

    # 2. abrir archivos: mismo resultado que el escritorio
    for nombre, contenido in [('m.svg', SVG), ('m.dxf', DXF), ('m.ai', AI)]:
        web = pedir('/api/parse', archivo=(nombre, contenido))
        p = os.path.join(COPIA, '_tmp_' + nombre); open(p, 'wb').write(contenido)
        esc = ds._load_vector(p); os.unlink(p)
        igual = web.get('ok') and web.get('paths') == esc.get('paths') and web.get('bbox') == esc.get('bbox')
        ok(igual, f'abrir {nombre[-3:].upper()}: idéntico al escritorio',
           f"{len(web.get('paths') or [])} trazados" if web.get('ok') else web.get('error'))
    r = pedir('/api/parse', archivo=('m.txt', b'hola'))
    ok(not r.get('ok') and 'no soportado' in (r.get('error') or ''), 'archivo no soportado → mensaje claro', r.get('error'))

    # 3. HPGL: mismo texto que el escritorio
    datos = {'paths': [[[0, 0], [40, 0], [40, 20], [0, 20], [0, 0]]], 'speed': 300, 'pressure': 120}
    web = pedir('/api/hpgl', datos)
    import studio_backend as be
    ok(web.get('ok') and web['hpgl'] == be.build_hpgl(datos), 'HPGL idéntico al que corta el escritorio', f"{web.get('bytes')} bytes")
    # Un diseño GRANDE (≈2 MB). Se revisa la RESPUESTA, no solo que conteste: el servidor
    # atrapa sus errores y responde 200 con el error adentro (así se escondió el 413).
    grande = {'paths': [[[i * 0.1, 0.0], [i * 0.1, 10.0], [i * 0.1 + 0.05, 10.0]] for i in range(35000)],
              'speed': 300, 'pressure': 120}
    tam = len(json.dumps(grande)) // 1024
    web = pedir('/api/hpgl', grande)
    ok(web.get('ok') and web['hpgl'] == be.build_hpgl(grande), f'HPGL de un diseño grande ({tam} KB) idéntico al escritorio', web.get('error') or f"{web.get('bytes')} bytes")
    ct, cuerpo = pedir('/api/export', {'format': 'svg', 'paths': grande['paths'], 'name': 'grande'}, crudo=True)
    ok(b'<svg' in cuerpo[:400], f'exportar un diseño grande ({tam} KB)', f'{len(cuerpo)} bytes' if b'<svg' in cuerpo[:400] else cuerpo[:150])
    gs = pedir('/api/autosave_save', {'objects': [{'pts': p} for p in grande['paths']]})
    ok(gs.get('ok') is not False, f'autoguardar un diseño grande ({tam} KB)', gs.get('error') or 'guardado')
    sq = pedir('/api/test_square')
    ok(sq.get('ok') and sq['hpgl'] == be.test_square_hpgl(10), 'cuadrado del test de corte idéntico al del escritorio', f"{sq.get('bytes')} bytes")

    # 4. área de trabajo y CNC (escriben config: por eso va sobre la copia)
    wa = pedir('/api/workarea')
    ok(wa.get('work') == list(ds._load_workarea()), 'leer área de trabajo', wa.get('work'))
    cnc = pedir('/api/cnc')
    ok(cnc.get('tools') and cnc.get('materials'), 'leer configuración CNC (fresas y materiales)', f"{len(cnc.get('tools') or [])} fresas")
    tx = pedir('/api/tools_export')
    ok(tx.get('ok') and tx.get('tools') == cnc.get('tools'), 'exportar biblioteca de fresas')

    # 5. fuentes y texto
    f = pedir('/api/fonts')
    fuentes = f.get('fonts') or []
    ok(len(fuentes) > 0, 'lista de fuentes', f'{len(fuentes)} fuentes (las de ESTA Mac)')
    if fuentes:
        f0 = next((x for x in fuentes if 'arial' in json.dumps(x).lower()), fuentes[0])
        t = pedir('/api/text', {'text': 'Hola', 'path': f0.get('path'), 'index': f0.get('index', 0), 'size': 20})
        ok(t.get('ok') and t.get('paths'), 'texto → trazados', f"{len(t.get('paths') or [])} trazados con {f0.get('name') or f0.get('family')}" if t.get('ok') else t.get('error'))

    # 6. geometría
    cuad = lambda x: [[x, 0], [x + 20, 0], [x + 20, 20], [x, 20], [x, 0]]
    b = pedir('/api/boolean', {'op': 'union', 'units': [[cuad(0)], [cuad(10)]]})
    ok(b.get('ok'), 'booleana Unir', b.get('error') or f"{len(b.get('paths') or b.get('rings') or [])} resultado(s)")

    # 7. exportar: los cuatro formatos devuelven archivo, no error
    for fmt, firma in [('svg', b'<svg'), ('pdf', b'%PDF'), ('png', b'\x89PNG'), ('dxf', b'SECTION')]:
        ct, cuerpo = pedir('/api/export', {'format': fmt, 'paths': [cuad(0)], 'name': 'prueba'}, crudo=True)
        ok(firma in cuerpo[:400], f'exportar {fmt.upper()}', f'{len(cuerpo)} bytes' if firma in cuerpo[:400] else cuerpo[:150])

    # 8. calco de imagen
    up = pedir('/api/trace_upload', archivo=('c.png', PNG))
    ok(up.get('ok'), 'subir imagen para calcar', up.get('error'))
    if up.get('ok'):
        tr = pedir('/api/trace', {'mode': 'bw', 'threshold': 128, 'smooth': 1, 'invert': False, 'colors': 2, 'speckle': 2})
        ok(tr.get('ok') and tr.get('paths'), 'calcar (potrace)', tr.get('error') or f"{len(tr.get('paths'))} trazados")
        tc = pedir('/api/trace', {'mode': 'color', 'colors': 4, 'speckle': 2})
        ok(tc.get('ok'), 'calcar a color (vtracer)', tc.get('error') or f"{len(tc.get('paths'))} trazados")
        for _ in range(3):
            pedir('/api/trace_upload', archivo=('c.png', PNG))
        pedir('/api/trace_upload', archivo=('rota.png', b'esto no es una imagen'))
        quedan = os.listdir(TEMPS)
        ok(len(quedan) == 1, '5 imágenes subidas (una rota) y 2 calcos → solo queda en disco la imagen que se está calcando', f'{len(quedan)} archivo(s): {sorted(quedan)}')
        tr = pedir('/api/trace', {'mode': 'bw', 'threshold': 128, 'smooth': 1, 'invert': False, 'colors': 2, 'speckle': 2})
        ok(tr.get('ok'), 'y el calco sigue funcionando con la última buena', tr.get('error'))

    # 9. autoguardado
    marca = {'prueba': uuid.uuid4().hex, 'objects': [{'pts': [[0, 0], [1, 1]]}]}
    pedir('/api/autosave_save', marca)
    ld = pedir('/api/autosave_load')
    ok(json.dumps(marca)[1:-1] in json.dumps(ld), 'autoguardar y recuperar', 'el dato vuelve' if json.dumps(marca)[1:-1] in json.dumps(ld) else str(ld)[:150])
    pedir('/api/autosave_clear', {})

    # ═══ FASE 4: varias cuentas, cada una con lo suyo ═══════════════════════════════════════
    import socket as _sk
    import threading as _th
    from concurrent.futures import ThreadPoolExecutor

    def galleta_de(cabeceras):
        return (cabeceras.get('Set-Cookie') or '').split(';')[0]

    def entrar(usuario, clave):
        st, h, _ = formulario('/entrar', {'usuario': usuario, 'clave': clave})
        return galleta_de(h) if st in (302, 303) else None

    def api(ruta, galleta, datos=None):
        """Un pedido a la API con la sesión indicada. (estado, respuesta ya leída)"""
        if datos is None:
            st, _, c = http_crudo('GET', ruta, cookie=galleta)
        else:
            st, _, c = http_crudo('POST', ruta, json.dumps(datos).encode(), {'Content-Type': 'application/json'}, galleta)
        try:
            return st, json.loads(c)
        except ValueError:
            return st, {'crudo': c}

    def subir(ruta, galleta, nombre, contenido):
        b = uuid.uuid4().hex
        cuerpo = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{nombre}"\r\n'
                  'Content-Type: application/octet-stream\r\n\r\n').encode() + contenido + f'\r\n--{b}--\r\n'.encode()
        st, _, c = http_crudo('POST', ruta, cuerpo, {'Content-Type': f'multipart/form-data; boundary={b}'}, galleta)
        return json.loads(c)

    def cuentas_post(galleta, **campos):
        return formulario('/cuentas', campos, cookie=galleta)

    def clave_temporal(html_):
        import re as _re
        m = _re.search(rb'<code>([^<]+)</code>', html_)
        return m.group(1).decode() if m else None

    YO = entrar('jose', CLAVE)

    # A. La cuenta del dueño hereda lo de antes; el original no se toca
    DATOS_WEB = os.path.join(COPIA, '_datos_web')
    with open(os.path.join(COPIA, 'cnc_config.json'), 'rb') as f:
        cnc_comun = f.read()
    with open(os.path.join(COPIA, 'plotter_config.json'), 'rb') as f:
        area_comun = f.read()
    herencia = json.loads(cnc_comun)
    _, cfg = api('/api/cnc', YO)
    ok([t.get('cut') for t in cfg['tools']] == [t.get('cut') for t in herencia['tools']] and
       os.path.exists(os.path.join(DATOS_WEB, 'usuarios', 'jose', 'cnc_config.json')),
       'el dueño conserva sus fresas: su carpeta nace con una copia')

    # B. Altas: solo el dueño, y con contraseña temporal
    st, h, c = cuentas_post(YO, accion='alta', usuario='Ana')
    TEMP_ANA = clave_temporal(c)
    ok(st == 200 and TEMP_ANA and len(TEMP_ANA) >= 12, 'el dueño crea una cuenta y ve su contraseña temporal')
    guardado = open(os.path.join(DATOS_WEB, 'usuarios.json'), encoding='utf-8').read()
    ok(TEMP_ANA not in guardado and 'ana' in json.loads(guardado), 'la temporal tampoco queda guardada')
    for malo in ('..', '.', '.oculto', 'a/b', '../../etc', 'a', 'ñandú', ''):
        st, h, c = cuentas_post(YO, accion='alta', usuario=malo)
        ok(st == 400 and clave_temporal(c) is None and malo not in json.load(open(os.path.join(DATOS_WEB, 'usuarios.json'), encoding='utf-8')),
           f'nombre de cuenta peligroso o inválido {malo!r} → rechazado')
    st, h, c = cuentas_post(YO, accion='alta', usuario='ana')
    ok(st == 400 and 'ya existe'.encode() in c, 'cuenta repetida → rechazada')

    # C. La temporal obliga a cambiarla antes de hacer nada
    ANA = entrar('ana', TEMP_ANA)
    ok(ANA, 'la cuenta nueva entra con su temporal')
    st, h, _ = http_crudo('GET', '/', cookie=ANA)
    ok(st == 302 and h.get('Location', '').endswith('/clave'), 'con temporal, la página manda a cambiarla', h.get('Location'))
    st, r = api('/api/cnc', ANA)
    ok(st == 401 and r.get('login'), 'con temporal, la API no responde')
    ok(not os.path.exists(os.path.join(DATOS_WEB, 'usuarios', 'ana')), 'con temporal, todavía no se le crea carpeta')
    CLAVE_ANA = 'ana-' + uuid.uuid4().hex[:12]
    st, h, c = formulario('/clave', {'actual': 'equivocada', 'nueva': CLAVE_ANA, 'nueva2': CLAVE_ANA}, cookie=ANA)
    ok(st == 400 and 'actual no es correcta'.encode() in c, 'cambiar sin saber la actual → rechazado')
    st, h, c = formulario('/clave', {'actual': TEMP_ANA, 'nueva': CLAVE_ANA, 'nueva2': 'otra-distinta'}, cookie=ANA)
    ok(st == 400 and 'no son iguales'.encode() in c, 'las dos nuevas distintas → lo dice')
    st, h, c = formulario('/clave', {'actual': TEMP_ANA, 'nueva': 'corta', 'nueva2': 'corta'}, cookie=ANA)
    ok(st == 400 and 'al menos 8'.encode() in c, 'contraseña nueva corta → la rechaza')
    st, h, c = formulario('/clave', {'actual': TEMP_ANA, 'nueva': TEMP_ANA, 'nueva2': TEMP_ANA}, cookie=ANA)
    ok(st == 400 and 'distinta'.encode() in c, 'no sirve "cambiarla" por la misma')
    st, h, c = formulario('/clave', {'actual': TEMP_ANA, 'nueva': CLAVE_ANA, 'nueva2': CLAVE_ANA}, cookie=ANA)
    ANA_VIEJA, ANA = ANA, galleta_de(h)
    ok(st in (302, 303) and ANA.startswith('ds_sesion='), 'cambio de contraseña hecho, sigue dentro')
    ok(api('/api/workarea', ANA)[0] == 200, 'con la definitiva, ya puede trabajar')
    ok(api('/api/workarea', ANA_VIEJA)[0] == 401, 'las sesiones de antes del cambio quedan muertas')
    ok(entrar('ana', TEMP_ANA) is None and entrar('ana', CLAVE_ANA), 'la temporal ya no sirve; la nueva sí')

    # D. Cada cuenta ve SOLO lo suyo
    st, h, c = http_crudo('GET', '/cuentas', cookie=ANA)
    ok(st == 403, 'una cuenta normal no ve la pantalla de cuentas')
    st, h, c = cuentas_post(ANA, accion='alta', usuario='colado')
    ok(st == 403 and 'colado' not in json.load(open(os.path.join(DATOS_WEB, 'usuarios.json'), encoding='utf-8')), 'una cuenta normal no crea cuentas')
    st, h, c = cuentas_post(ANA, accion='desactivar', usuario='jose')
    ok(st == 403, 'una cuenta normal no desactiva a nadie')
    ok(api('/api/update_check', YO)[1].get('dueno') is True and api('/api/update_check', ANA)[1].get('dueno') is False,
       'la interfaz sabe quién es dueño (para mostrar el enlace)')
    _, cfg_ana = api('/api/cnc', ANA)
    import studio_backend as _sb
    ok([t['cut'] for t in cfg_ana['tools']] == [t['cut'] for t in _sb.CNC_DEFAULTS['tools']],
       'la cuenta nueva arranca con fresas de fábrica, no con las del dueño')
    _, antes_yo = api('/api/cnc', YO)
    tools = json.loads(json.dumps(cfg_ana['tools']))
    tools[0]['name'] = 'FRESA DE ANA'
    api('/api/cnc', ANA, {'tools': tools, 'quote': {'margin': 77}, 'theme': 'dark'})
    _, ahora_yo = api('/api/cnc', YO)
    _, ahora_ana = api('/api/cnc', ANA)
    ok(ahora_ana['tools'][0]['name'] == 'FRESA DE ANA' and ahora_ana['quote']['margin'] == 77 and ahora_ana['theme'] == 'dark',
       'los cambios de una cuenta se guardan')
    ok(ahora_yo['tools'] == antes_yo['tools'] and ahora_yo['quote'] == antes_yo['quote'] and ahora_yo['theme'] == antes_yo['theme'],
       'fresas, tarifas y tema de una cuenta NO tocan a la otra')
    area_yo = api('/api/workarea', YO)[1]['work']
    api('/api/set_workarea', ANA, {'w': 1234, 'h': 567})
    ok(api('/api/workarea', ANA)[1]['work'] == [1234, 567] and api('/api/workarea', YO)[1]['work'] == area_yo, 'el área de trabajo es por cuenta')
    proyecto = {'marca': uuid.uuid4().hex, 'objects': [{'pts': [[0, 0], [1, 1]]}]}
    api('/api/autosave_save', ANA, proyecto)
    ok(api('/api/autosave_load', YO)[1].get('exists') is False, 'el autoguardado de una cuenta NO lo ve la otra')
    ok(api('/api/autosave_load', ANA)[1].get('project', {}).get('marca') == proyecto['marca'], 'y su dueña sí lo recupera')
    subir('/api/trace_upload', YO, 'yo.png', PNG)
    r = api('/api/trace', ANA, {'mode': 'bw'})[1]
    ok(r.get('ok') is False and 'No hay imagen' in (r.get('error') or ''), 'el calco de una cuenta NO usa la imagen subida por otra', r.get('error'))
    ok(subir('/api/trace_upload', ANA, 'ana.png', PNG).get('ok') and api('/api/trace', ANA, {'mode': 'bw'})[1].get('ok') and
       api('/api/trace', YO, {'mode': 'bw'})[1].get('ok'), 'cada cuenta calca su propia imagen a la vez')
    ok(len(os.listdir(TEMPS)) <= 2, 'el calco deja a lo sumo una imagen por cuenta en el disco', str(os.listdir(TEMPS)))
    pieza = {'rings': [[[0, 0], [40, 0], [40, 30], [0, 30]]]}
    trabajo = {'sheet': [200, 200], 'margin': 2, 'gap': 2, 'rots': [0], 'units': [pieza] * 6}
    jid = api('/api/nest_start', ANA, trabajo)[1].get('job')
    ok(jid and 'desconocido' in (api('/api/nest_status', YO, {'job': jid})[1].get('error') or ''),
       'el acomodo de una cuenta NO lo puede leer otra (aunque adivine el número)')
    for _ in range(100):
        r = api('/api/nest_status', ANA, {'job': jid})[1]
        if r.get('done'):
            break
        time.sleep(0.1)
    ok(r.get('done') and r.get('placed'), 'su dueña sí recibe el resultado del acomodo', f"{len(r.get('placed') or [])} piezas")
    for _ in range(6):
        api('/api/nest_start', YO, trabajo)
    ok(api('/api/nest_status', ANA, {'job': jid})[1].get('ok'), 'los acomodos de otra cuenta no le borran el suyo')

    # E. Desactivar y restablecer
    st, h, c = cuentas_post(YO, accion='desactivar', usuario='jose')
    ok(st == 400 and api('/api/workarea', YO)[0] == 200, 'el dueño no puede desactivarse a sí mismo')
    st, h, c = cuentas_post(YO, accion='desactivar', usuario='ana')
    ok(st == 200 and api('/api/workarea', ANA)[0] == 401, 'desactivar saca a la cuenta AL INSTANTE, con la sesión ya abierta')
    ok(entrar('ana', CLAVE_ANA) is None, 'desactivada, ya no puede entrar')
    ok(os.path.exists(os.path.join(DATOS_WEB, 'usuarios', 'ana', 'cnc_config.json')), 'desactivar NO borra sus datos')
    cuentas_post(YO, accion='activar', usuario='ana')
    ANA = entrar('ana', CLAVE_ANA)
    ok(ANA and api('/api/cnc', ANA)[1]['tools'][0]['name'] == 'FRESA DE ANA', 'al reactivarla vuelve con todo lo suyo')
    st, h, c = cuentas_post(YO, accion='restablecer', usuario='ana')
    TEMP2 = clave_temporal(c)
    ok(TEMP2 and api('/api/workarea', ANA)[0] == 401 and entrar('ana', CLAVE_ANA) is None,
       'restablecer: la contraseña olvidada deja de servir y se cierran sus sesiones')
    ANA = entrar('ana', TEMP2)
    st, h, _ = http_crudo('GET', '/api/workarea', cookie=ANA)
    ok(st == 401, 'y entra con temporal, obligada a cambiarla otra vez')
    st, h, _ = formulario('/clave', {'actual': TEMP2, 'nueva': CLAVE_ANA + 'x', 'nueva2': CLAVE_ANA + 'x'}, cookie=ANA)
    ANA = galleta_de(h)
    st, h, c = cuentas_post(YO, accion='restablecer', usuario='jose')
    ok(st == 400 and clave_temporal(c) is None and entrar('jose', CLAVE), 'la contraseña del dueño no se restablece por esa vía')

    # F. Varios a la vez
    # Un pedido que se queda a medias (alguien con mala conexión). Con el servidor de antes, que
    # atendía de a uno, esto congelaba a TODOS mientras durara.
    lento = _sk.create_connection(('127.0.0.1', PUERTO), timeout=10)
    lento.sendall((f'POST /api/autosave_save HTTP/1.1\r\nHost: x\r\nCookie: {YO}\r\n'
                   'Content-Type: application/json\r\nContent-Length: 1000\r\n\r\n{').encode())
    time.sleep(0.3)
    t0 = time.time()
    st, r = api('/api/workarea', ANA)
    ok(st == 200 and time.time() - t0 < 3, 'un pedido atascado de una cuenta NO congela a las demás', f'{time.time() - t0:.2f} s')
    lento.close()
    # Un acomodo pesado de verdad, y mientras tanto otra cuenta trabaja.
    pesado = {'sheet': [3000, 3000], 'margin': 2, 'gap': 2,
              'units': [{'rings': [[[0, 0], [30 + i % 40, 0], [30 + i % 40, 20 + i % 25], [10, 40], [0, 20 + i % 25]]]} for i in range(120)]}
    jid = api('/api/nest_start', YO, pesado)[1].get('job')
    tiempos = []
    for _ in range(8):
        t0 = time.time(); api('/api/workarea', ANA); tiempos.append(time.time() - t0)
    enmarcha = not api('/api/nest_status', YO, {'job': jid})[1].get('done')
    ok(enmarcha and max(tiempos) < 2, 'durante un acomodo largo, otra cuenta sigue trabajando', f'lo más lento: {max(tiempos):.2f} s (seguía en marcha: {enmarcha})')
    for _ in range(600):
        if api('/api/nest_status', YO, {'job': jid})[1].get('done'):
            break
        time.sleep(0.2)
    # Dos cambios simultáneos de la misma cuenta: los dos tienen que sobrevivir.
    perdidos = 0
    with ThreadPoolExecutor(2) as hilos:
        for _ in range(25):
            api('/api/cnc', ANA, {'theme': 'light', 'units': 'mm'})
            list(hilos.map(lambda p: api('/api/cnc', ANA, p), [{'theme': 'dark'}, {'units': 'in'}]))
            c = api('/api/cnc', ANA)[1]
            perdidos += not (c['theme'] == 'dark' and c['units'] == 'in')
    ok(perdidos == 0, 'dos cambios a la vez en la misma cuenta: no se pierde ninguno', f'{perdidos} de 25 rondas perdieron uno')
    # Mezcla pesada: cada resultado tiene que ser el correcto, y el de SU cuenta.
    EJEMPLO_SVG = {f: subir('/api/parse', YO, f'x.{f}', d).get('paths') for f, d in (('svg', SVG), ('dxf', DXF), ('ai', AI))}
    disenio = {'name': 'x', 'paths': [[[0, 0], [50, 0], [50, 50], [0, 50], [0, 0]]]}
    malos = []
    CUENTAS = {'jose': YO, 'ana': ANA}

    def trabajo_mixto(n):
        quien = 'jose' if n % 2 else 'ana'
        g = CUENTAS[quien]
        marca = f'{quien}-{n}-{uuid.uuid4().hex}'
        api('/api/autosave_save', g, {'marca': quien, 'n': marca, 'objects': [{'pts': [[0, 0], [1, 1]]}]})
        v = api('/api/autosave_load', g)[1].get('project', {})
        if v.get('marca') != quien:
            malos.append(f'autoguardado de {quien} devolvió {v.get("marca")!r}')
        for f, d in (('svg', SVG), ('dxf', DXF), ('ai', AI)):
            r = subir('/api/parse', g, f'x.{f}', d)
            if r.get('paths') != EJEMPLO_SVG[f]:
                malos.append(f'abrir {f} a la vez dio otro resultado: {str(r.get("error"))[:80]}')
        for fmt, inicio in (('pdf', b'%PDF'), ('png', b'\x89PNG')):
            st, _, c = http_crudo('POST', '/api/export', json.dumps({**disenio, 'format': fmt}).encode(), {'Content-Type': 'application/json'}, g)
            if st != 200 or not c.startswith(inicio):
                malos.append(f'exportar {fmt}: {st} {c[:60]!r}')
        tema = api('/api/cnc', g)[1]
        if quien == 'ana' and tema['tools'][0]['name'] != 'FRESA DE ANA':
            malos.append('ana recibió otras fresas: ' + tema['tools'][0]['name'])
        if quien == 'jose' and tema['tools'][0]['name'] == 'FRESA DE ANA':
            malos.append('jose recibió las fresas de ana')

    with ThreadPoolExecutor(12) as hilos:
        list(hilos.map(trabajo_mixto, range(60)))
    ok(not malos, '60 tandas simultáneas de 2 cuentas (autoguardar, abrir SVG/DXF/AI, PDF, PNG, fresas): todo correcto', '; '.join(malos[:3]))
    ok(srv.poll() is None, 'el servidor sobrevivió a la mezcla')

    # G. Nada fue a parar al archivo común, ni al revés
    ok(open(os.path.join(COPIA, 'cnc_config.json'), 'rb').read() == cnc_comun and
       open(os.path.join(COPIA, 'plotter_config.json'), 'rb').read() == area_comun and
       not os.path.exists(os.path.join(COPIA, 'autosave.dstudio')),
       'los archivos comunes quedaron idénticos: nada se escribió fuera de las carpetas de cuenta')
    sobras = [n for _r, _d, fs in os.walk(DATOS_WEB) for n in fs if n.endswith('.tmp')] + \
             [d for _r, ds_, _f in os.walk(DATOS_WEB) for d in ds_ if d.endswith('.armando')]
    ok(not sobras, 'no quedan archivos a medio escribir', str(sobras))

    # H. El escritorio sigue como siempre: sin cuenta, la config de la instalación
    ok(core._config_path() == core._config_compartida() == core.Path(core.__file__).parent / 'plotter_config.json',
       'escritorio: sigue usando su carpeta de siempre')

    # I. Catálogo de fuentes propio
    cat = os.path.join(COPIA, '_catalogo')
    os.makedirs(cat)
    shutil.copyfile('/System/Library/Fonts/Supplemental/Arial.ttf', os.path.join(cat, 'Arial.ttf'))
    salida = subprocess.run([sys.executable, '-c', 'import json,text_vector as t;r=t.list_fonts();print(json.dumps(sorted({f["path"] for f in r["fonts"]})))'],
                            cwd=COPIA, env=dict(os.environ, DS_FUENTES=cat), capture_output=True, text=True, timeout=120)
    try:
        rutas = json.loads(salida.stdout.strip().splitlines()[-1])
    except Exception:
        rutas = []
    ok(rutas == [os.path.join(cat, 'Arial.ttf')], 'con catálogo propio, solo se ofrecen esas fuentes (no las de la máquina)', str(rutas)[:120] or salida.stderr[-200:])

    # ═══ Prueba sin cuenta ══════════════════════════════════════════════════════════════════
    def abrir_prueba():
        st, h, c = formulario('/invitado', {})
        return st, h, c, galleta_de(h)

    st, h, c = http_crudo('GET', '/entrar')
    ok(b'Probar sin cuenta' in c, 'la pantalla de entrada ofrece probar sin cuenta')
    usuarios_antes = open(os.path.join(DATOS_WEB, 'usuarios.json'), 'rb').read()
    st, h, c, P1 = abrir_prueba()
    ok(st in (302, 303) and P1.startswith('ds_sesion=') and 'Max-Age' not in (h.get('Set-Cookie') or '') and 'HttpOnly' in (h.get('Set-Cookie') or ''),
       'un clic y entra: la cookie muere al cerrar el navegador', (h.get('Set-Cookie') or '')[:70])
    P2 = abrir_prueba()[3]
    ok(http_crudo('GET', '/', cookie=P1)[0] == 200, 'con la prueba se abre la aplicación')
    r = api('/api/update_check', P1)[1]
    ok(r.get('invitado') is True and r.get('dueno') is False, 'la interfaz sabe que es una prueba (para avisarlo)')
    ok(r.get('usuario') not in usuarios_antes.decode() and open(os.path.join(DATOS_WEB, 'usuarios.json'), 'rb').read() == usuarios_antes,
       'la prueba no crea ninguna cuenta')
    fresas_yo = api('/api/cnc', YO)[1]['tools']
    c1 = api('/api/cnc', P1)[1]
    ok([t['cut'] for t in c1['tools']] == [t['cut'] for t in _sb.CNC_DEFAULTS['tools']], 'arranca con valores de fábrica, no con los tuyos')
    tools = json.loads(json.dumps(c1['tools'])); tools[0]['name'] = 'FRESA DE PRUEBA'
    api('/api/cnc', P1, {'tools': tools})
    api('/api/set_workarea', P1, {'w': 111, 'h': 222})
    ok(api('/api/cnc', P1)[1]['tools'][0]['name'] == 'FRESA DE PRUEBA' and api('/api/workarea', P1)[1]['work'] == [111, 222],
       'mientras dura, los ajustes funcionan')
    ok(api('/api/cnc', P2)[1]['tools'][0]['name'] != 'FRESA DE PRUEBA' and api('/api/cnc', YO)[1]['tools'] == fresas_yo and api('/api/workarea', YO)[1]['work'] != [111, 222],
       'no tocan a otro visitante ni a las cuentas reales')
    api('/api/autosave_save', P1, {'objects': [{'pts': [[0, 0], [1, 1]]}]})
    ok(api('/api/autosave_load', P1)[1].get('exists') is False, 'el autoguardado no guarda nada')
    carpetas = os.listdir(os.path.join(DATOS_WEB, 'invitados'))
    ok(len(carpetas) == 2 and not any(os.path.exists(os.path.join(DATOS_WEB, 'invitados', n, 'autosave.dstudio')) for n in carpetas), 'ni deja el archivo en el disco')
    ok(http_crudo('GET', '/cuentas', cookie=P1)[0] == 403 and cuentas_post(P1, accion='alta', usuario='colada')[0] == 403 and
       cuentas_post(P1, accion='desactivar', usuario='ana')[0] == 403, 'una prueba no administra cuentas')
    st, h, _ = http_crudo('GET', '/clave', cookie=P1)
    ok(st in (302, 303) and formulario('/clave', {'actual': 'x', 'nueva': 'y' * 10, 'nueva2': 'y' * 10}, cookie=P1)[0] in (302, 303), 'una prueba no tiene contraseña que cambiar')
    st, h, c = cuentas_post(YO, accion='alta', usuario='invitado:1893456000-0123456789abcdef')
    ok(st == 400, 'una cuenta real no se puede llamar como una prueba')
    st, h, _ = formulario('/invitado', {}, cookie=YO)
    ok(st in (302, 303) and not h.get('Set-Cookie') and api('/api/update_check', YO)[1].get('usuario') == 'jose', 'con tu sesión abierta, el botón no te saca de tu cuenta')
    ok(subir('/api/trace_upload', P1, 'p.png', PNG).get('ok') and api('/api/trace', P1, {'mode': 'bw'})[1].get('ok'), 'una prueba puede calcar')
    imagenes = len(os.listdir(TEMPS))
    # Un acomodo a la vez
    largo = {'sheet': [3000, 3000], 'margin': 2, 'gap': 2, 'units': [{'rings': [[[0, 0], [30 + i % 40, 0], [30 + i % 40, 20 + i % 25], [10, 40], [0, 20 + i % 25]]]} for i in range(120)]}
    j1 = api('/api/nest_start', P1, largo)[1]
    j2 = api('/api/nest_start', P1, largo)[1]
    ok(j1.get('ok') and j2.get('ok') is False and 'a la vez' in (j2.get('error') or ''), 'una prueba corre un solo acomodo a la vez', j2.get('error'))
    ok(api('/api/nest', P1, largo)[1].get('ok') is False, 'y no puede saltarse el tope por el otro camino')
    # Salir borra todo
    st, h, _ = http_crudo('GET', '/salir', cookie=P1)
    ok(len(os.listdir(os.path.join(DATOS_WEB, 'invitados'))) == 1, 'al salir, su carpeta desaparece')
    ok(api('/api/workarea', P1)[0] == 401, 'y su cookie ya no sirve, aunque alguien la haya copiado')
    ok(len(os.listdir(TEMPS)) == imagenes - 1, 'y se borra la imagen que calcaba')
    P3 = abrir_prueba()[3]
    ok(api('/api/workarea', P3)[1]['work'] != [111, 222] and api('/api/cnc', P3)[1]['tools'][0]['name'] != 'FRESA DE PRUEBA', 'volver a probar empieza de cero')
    respuestas = [abrir_prueba()[0] for _ in range(8)]
    ok(respuestas[-1] == 429, 'muchas pruebas seguidas desde la misma dirección → frena', str(respuestas))
    ok(http_crudo('GET', '/api/workarea', cookie=YO)[0] == 200 and entrar('jose', CLAVE), 'ese freno no afecta a quien tiene cuenta')
    # Tope general, vencimiento y reinicio: sin esperar 2 horas, directo sobre el módulo
    ensayo = tempfile.mkdtemp(prefix='ds_prueba_', dir=COPIA)
    guion = '''
import json, time, web_auth as a
a.crear_cuenta("dueno", "x" * 12)
s = [a.abrir_invitado({"REMOTE_ADDR": f"10.0.0.{i}"}) for i in range(a.MAX_INVITADOS + 1)]
r = {"tope": s[-1][2] or "", "pasaron": sum(1 for x in s if x[0])}
r["valida"] = a.usuario_de(s[0][0]) == s[0][1]
real = time.time
time.time = lambda: real() + a.DURACION_INVITADO + 5
r["vencida_rechazada"] = a.usuario_de(s[0][0]) is None
r["purgadas"] = len(a.purgar_invitados())
time.time = real
n = a.abrir_invitado({"REMOTE_ADDR": "10.0.1.1"})
r["todas"] = a.purgar_invitados(todos=True) == [n[1]] and a.usuario_de(n[0]) is None
r["cuentas"] = list(a._usuarios())
print(json.dumps(r))
'''
    sal = subprocess.run([sys.executable, '-c', guion], cwd=COPIA, env=dict(os.environ, DS_DATOS=ensayo), capture_output=True, text=True, timeout=120)
    try:
        r = json.loads(sal.stdout.strip().splitlines()[-1])
    except Exception:
        r = {}
    ok(r.get('pasaron') == 20 and 'muchas pruebas' in r.get('tope', ''), 'máximo 20 pruebas a la vez en todo el servidor', str(r)[:150] or sal.stderr[-200:])
    ok(r.get('valida') and r.get('vencida_rechazada') and r.get('purgadas') == 20, 'a las 2 horas la cookie deja de valer y la carpeta se borra', sal.stderr[-200:])
    ok(r.get('todas') and r.get('cuentas') == ['dueno'], 'reiniciar borra todas las pruebas y ninguna cuenta real')

    # Y. TÚNEL DE CLOUDFLARE — con las cabeceras MEDIDAS en un túnel real (5-nov-2026): todo
    # llega desde 127.0.0.1, CF-Connecting-IP = el visitante (Cloudflare da 403 si alguien la
    # inventa) y X-Forwarded-For = lo que el visitante quiera poner + su dirección real al final.
    def tunel(real, inventada=None):
        return {'CF-Connecting-IP': real, 'X-Forwarded-Proto': 'https',
                'X-Forwarded-For': (inventada + ',' if inventada else '') + real}
    for i in range(8):   # el atacante inventa una dirección distinta en CADA intento
        formulario('/entrar', {'usuario': 'jose', 'clave': 'adivinando'}, tunel('198.51.100.7', f'1.1.1.{i}'))
    st, h, cuerpo = formulario('/entrar', {'usuario': 'jose', 'clave': CLAVE}, tunel('198.51.100.7', '1.1.1.99'))
    ok(st == 401 and 'Demasiados intentos'.encode() in cuerpo,
       'por el túnel: inventar una dirección por intento NO esquiva el bloqueo de 8 fallos', str(st))
    st, h, cuerpo = formulario('/entrar', {'usuario': 'jose', 'clave': CLAVE}, tunel('203.0.113.50'))
    ok(st in (302, 303) and 'Secure' in (h.get('Set-Cookie') or ''),
       'el atacante bloqueado NO deja fuera a otro visitante del túnel, y su cookie va marcada solo-https',
       f'{st} · {h.get("Set-Cookie", "")[:80]}')
    st, h, cuerpo = formulario('/entrar', {'usuario': 'jose', 'clave': CLAVE})
    ok(st in (302, 303), 'ni al dueño en esta Mac (antes, todo el túnel era "127.0.0.1" y uno bloqueaba a todos)', str(st))
    guion_ip = r'''
import json, web_auth as a
L = {"REMOTE_ADDR": "127.0.0.1"}
casos = {
  "tunel": a.direccion(dict(L, HTTP_CF_CONNECTING_IP="198.51.100.7", HTTP_X_FORWARDED_FOR="6.6.6.6, 198.51.100.7")),
  "cf_desde_wifi": a.direccion({"REMOTE_ADDR": "192.168.1.5", "HTTP_CF_CONNECTING_IP": "6.6.6.6"}),
  "proxy_inventada": a.direccion({"REMOTE_ADDR": "10.0.0.2", "HTTP_X_FORWARDED_FOR": "6.6.6.6, 198.51.100.8"}),
  "local_tunel": a.es_esta_computadora(dict(L, HTTP_CF_CONNECTING_IP="198.51.100.7")),
  "local_de_verdad": a.es_esta_computadora(dict(L)),
}
print(json.dumps(casos))
'''
    for proxy in ('0', '1'):
        sal = subprocess.run([sys.executable, '-c', guion_ip], cwd=COPIA, env=dict(os.environ, DS_PROXY=proxy),
                             capture_output=True, text=True, timeout=60)
        try:
            c = json.loads(sal.stdout.strip().splitlines()[-1])
        except Exception:
            c = {}
        ok(c.get('tunel') == '198.51.100.7' and c.get('cf_desde_wifi') == '192.168.1.5'
           and c.get('local_tunel') is False and c.get('local_de_verdad') is True
           and c.get('proxy_inventada') == ('198.51.100.8' if proxy == '1' else '10.0.0.2'),
           f'DS_PROXY={proxy}: dirección real por túnel/proxy, CF inventada desde el WiFi ignorada, '
           'el túnel nunca es "esta computadora"', str(c) or sal.stderr[-200:])

    # Z. fuerza bruta (al final: deja bloqueada la dirección de la prueba)
    for _ in range(8):
        formulario('/entrar', {'usuario': 'jose', 'clave': 'adivinando'})
    st, h, cuerpo = formulario('/entrar', {'usuario': 'jose', 'clave': CLAVE})
    ok(st == 401 and 'Demasiados intentos'.encode() in cuerpo, 'tras 8 contraseñas equivocadas: bloqueado aunque la 9.ª sea la buena')

finally:
    srv.terminate()
    try:
        srv.wait(5)
    except Exception:
        srv.kill()

malos = [r for r in resultados if not r[0]]
shutil.rmtree(COPIA, ignore_errors=True)
print(f'\n{len(resultados) - len(malos)} de {len(resultados)} OK')
sys.exit(1 if malos else 0)
