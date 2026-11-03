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
