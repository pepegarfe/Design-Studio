#!/usr/bin/env python3
"""
Entrada con contraseña para la versión web de Design Studio (fase 3).

La app de escritorio NO usa esto: solo studio_server.py.

- Las cuentas viven en `datos_web/usuarios.json` (fuera de git). La contraseña nunca se guarda:
  se guarda una "huella" (PBKDF2, 600 000 vueltas con sal propia). Con la huella se puede
  comprobar una contraseña, pero no recuperarla.
- Al entrar, el navegador recibe una cookie de sesión FIRMADA: usuario + vencimiento + firma
  HMAC con una llave secreta que solo tiene el servidor (`datos_web/secreto.key`). Si alguien
  cambia una letra de la cookie, la firma ya no cuadra y se rechaza.
- La PRIMERA cuenta solo se puede crear desde la misma computadora donde corre el servidor
  (localhost). Si no, el primero que llegara desde internet se quedaría con el servidor.
- Tras 8 contraseñas equivocadas desde la misma dirección, se bloquea 15 minutos (así no se
  puede probar contraseñas a lo bruto).
- La primera cuenta del archivo es la del DUEÑO: es la única que da de alta a las demás. Cada
  cuenta guarda sus datos en `datos_web/usuarios/<usuario>/` (fresas, área, autoguardado).
- Una cuenta nueva o con contraseña restablecida entra con una contraseña TEMPORAL y está
  obligada a cambiarla: así el dueño nunca conoce la contraseña definitiva de nadie.
- "Probar sin cuenta": cada visitante recibe una carpeta temporal propia, que se borra al salir,
  a las 2 horas o al reiniciar el servidor. Sin la carpeta, su cookie deja de valer.
"""
import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import shutil
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.environ.get('DS_DATOS') or os.path.join(AQUI, 'datos_web')
COOKIE = 'ds_sesion'
DURACION = 30 * 24 * 3600          # la sesión dura 30 días
VUELTAS = 600_000                  # PBKDF2-SHA256: lo que recomienda OWASP hoy
MAX_FALLOS, VENTANA = 8, 15 * 60   # 8 fallos → 15 minutos de bloqueo
MIN_CLAVE = 8
# ⚠️ El nombre se vuelve el de una CARPETA: no puede empezar con punto. Con un punto al inicio
# era válido ".." y esa cuenta habría guardado sus datos encima de los de todos.
NOMBRE_VALIDO = re.compile(r'[a-z0-9][a-z0-9._-]{1,31}')
# Prueba sin cuenta. El nombre lleva ":", que NOMBRE_VALIDO no admite: una cuenta real nunca
# puede llamarse igual. Es público y sin contraseña, por eso los topes.
INVITADOS_ACTIVOS = os.environ.get('DS_INVITADOS') != '0'   # DS_INVITADOS=0 quita el botón
DURACION_INVITADO = 2 * 3600
MAX_INVITADOS = 20                     # pruebas a la vez en todo el servidor
MAX_INVITADOS_DIRECCION = 10           # pruebas nuevas por dirección cada VENTANA
_RE_INVITADO = re.compile(r'invitado:(\d{10,12})-([0-9a-f]{16})')
# Detrás de un proxy (Railway, etc.) la dirección real del visitante viene en X-Forwarded-For.
# Solo se le cree si se avisa con DS_PROXY=1: si no, cualquiera podría inventarse una dirección.
DETRAS_DE_PROXY = os.environ.get('DS_PROXY') == '1'

_lock = threading.Lock()
_fallos = {}   # dirección → [horas de cada fallo reciente]
_pruebas = {}  # dirección → [horas de cada prueba sin cuenta abierta]


# ── archivos ──────────────────────────────────────────────────────────────────
def _ruta(nombre):
    os.makedirs(DATOS, exist_ok=True)
    return os.path.join(DATOS, nombre)


def _secreto():
    env = os.environ.get('DS_SECRETO')
    if env:
        return env.encode('utf-8')
    p = _ruta('secreto.key')
    with _lock:
        if not os.path.exists(p):
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)   # solo el dueño lo lee
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(secrets.token_hex(32))
        with open(p, encoding='utf-8') as f:
            return f.read().strip().encode('utf-8')


def _usuarios():
    try:
        with open(_ruta('usuarios.json'), encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _guardar_usuarios(u):
    p = _ruta('usuarios.json')
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(u, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)   # de un golpe: nunca queda un archivo a medio escribir


def hay_cuentas():
    return bool(_usuarios())


# ── contraseñas ───────────────────────────────────────────────────────────────
def _huella(clave, sal):
    return hashlib.pbkdf2_hmac('sha256', clave.encode('utf-8'), sal, VUELTAS).hex()


def crear_cuenta(usuario, clave, temporal=False):
    usuario = (usuario or '').strip().lower()
    if not NOMBRE_VALIDO.fullmatch(usuario):
        return ('El usuario lleva de 2 a 32 letras sin acentos, números, punto, guion o guion bajo, '
                'y empieza con letra o número.')
    if len(clave or '') < MIN_CLAVE:
        return f'La contraseña necesita al menos {MIN_CLAVE} caracteres.'
    # La huella tarda a propósito: se calcula FUERA del candado, que usan todos los pedidos.
    sal = secrets.token_bytes(16)
    huella = _huella(clave, sal)
    with _lock:
        u = _usuarios()
        if usuario in u:
            return 'Ese usuario ya existe.'
        u[usuario] = {'sal': sal.hex(), 'huella': huella, 'v': 1,
                      'creado': time.strftime('%Y-%m-%d %H:%M')}
        if temporal:
            u[usuario]['cambiar'] = True
        _guardar_usuarios(u)
    return None


def dueno():
    """La primera cuenta creada (el archivo conserva el orden). Las cuentas no se borran."""
    return next(iter(_usuarios()), None)


def es_dueno(usuario):
    return bool(usuario) and usuario == dueno()


def debe_cambiar_clave(usuario):
    return bool(_usuarios().get(usuario, {}).get('cambiar'))


def cuentas():
    """Para la pantalla del dueño: sin sal ni huella."""
    return [{'usuario': k, 'creado': v.get('creado', ''), 'activa': v.get('activa', True),
             'cambiar': bool(v.get('cambiar'))} for k, v in _usuarios().items()]


def _clave_temporal():
    return secrets.token_urlsafe(12)


def alta(usuario):
    """Crea una cuenta con contraseña temporal. Devuelve (clave, error)."""
    clave = _clave_temporal()
    err = crear_cuenta(usuario, clave, temporal=True)
    return (None, err) if err else (clave, None)


def restablecer_clave(usuario):
    """Contraseña temporal nueva para quien la olvidó; cierra todas sus sesiones. (clave, error)"""
    if es_dueno(usuario):
        return None, 'La cuenta del dueño cambia su contraseña desde "Cambiar contraseña".'
    clave = _clave_temporal()
    sal = secrets.token_bytes(16)
    huella = _huella(clave, sal)
    with _lock:
        u = _usuarios()
        if usuario not in u:
            return None, 'Esa cuenta no existe.'
        u[usuario].update(sal=sal.hex(), huella=huella, cambiar=True, v=u[usuario].get('v', 1) + 1)
        _guardar_usuarios(u)
    return clave, None


def poner_activa(usuario, activa):
    """Desactivar saca a la cuenta al instante, pero conserva sus datos. Devuelve un error o None."""
    if es_dueno(usuario):
        return 'La cuenta del dueño no se puede desactivar.'
    with _lock:
        u = _usuarios()
        if usuario not in u:
            return 'Esa cuenta no existe.'
        u[usuario]['activa'] = bool(activa)
        _guardar_usuarios(u)
    return None


def cambiar_clave(environ, usuario, actual, nueva):
    """El propio usuario. Pide la actual (con el mismo bloqueo por fallos que entrar) y cierra sus
    otras sesiones. Devuelve un error o None."""
    err = intentar_entrar(environ, usuario, actual)
    if err:
        return 'La contraseña actual no es correcta.' if 'incorrectos' in err else err
    if len(nueva or '') < MIN_CLAVE:
        return f'La contraseña nueva necesita al menos {MIN_CLAVE} caracteres.'
    if nueva == actual:
        return 'La contraseña nueva tiene que ser distinta de la actual.'
    sal = secrets.token_bytes(16)
    huella = _huella(nueva, sal)
    with _lock:
        u = _usuarios()
        u[usuario].update(sal=sal.hex(), huella=huella, v=u[usuario].get('v', 1) + 1)
        u[usuario].pop('cambiar', None)
        _guardar_usuarios(u)
    return None


# ── la carpeta de datos de cada cuenta ────────────────────────────────────────
def carpeta_de(usuario, heredar_de=None, archivos=()):
    """La carpeta de datos de la cuenta; la crea la primera vez.

    La del DUEÑO nace con una COPIA de `archivos` tomados de `heredar_de` (lo que usaba antes de
    que hubiera cuentas): si no, al estrenar esto se quedaría sin sus fresas. El original no se
    toca. Se arma aparte y se renombra al final: si la copia falla, el pedido da error y se
    reintenta, en vez de quedar para siempre una carpeta a medias con valores de fábrica."""
    if es_invitado(usuario):
        return _carpeta_invitado(usuario)   # ya existe: sin ella, usuario_de() no lo deja pasar
    if not NOMBRE_VALIDO.fullmatch(usuario or ''):
        raise ValueError('nombre de cuenta inválido')
    d = os.path.join(DATOS, 'usuarios', usuario)
    with _lock:   # si no, un 2.º pedido simultáneo vería la carpeta antes de tener las fresas
        if not os.path.isdir(d):
            armando = d + '.armando'
            os.makedirs(armando, mode=0o700, exist_ok=True)
            if heredar_de and usuario == next(iter(_usuarios()), None):
                for n in archivos:
                    origen = os.path.join(heredar_de, n)
                    if os.path.exists(origen):
                        shutil.copy2(origen, os.path.join(armando, n))
            os.rename(armando, d)
    return d


def _clave_ok(usuario, clave):
    c = _usuarios().get((usuario or '').strip().lower())
    if not c or not c.get('activa', True):
        _huella(clave or '', b'\0' * 16)   # tarda lo mismo: no delata qué usuarios existen
        return False
    return hmac.compare_digest(_huella(clave or '', bytes.fromhex(c['sal'])), c['huella'])


# ── sesiones (cookie firmada) ─────────────────────────────────────────────────
def _b64(b):
    return base64.urlsafe_b64encode(b).decode('ascii').rstrip('=')


def _firma(datos):
    return _b64(hmac.new(_secreto(), datos.encode('utf-8'), hashlib.sha256).digest())


def emitir_sesion(usuario):
    c = _usuarios()[usuario]
    datos = _b64(json.dumps([usuario, int(time.time()) + DURACION, c.get('v', 1)]).encode('utf-8'))
    return datos + '.' + _firma(datos)


def usuario_de(token):
    """El usuario de una cookie válida, o None (falsa, alterada, vencida o de una cuenta borrada)."""
    try:
        datos, firma = (token or '').split('.', 1)
        if not hmac.compare_digest(firma, _firma(datos)):
            return None
        usuario, vence, v = json.loads(base64.urlsafe_b64decode(datos + '=' * (-len(datos) % 4)))
        if v == 'inv':
            ok = es_invitado(usuario) and time.time() <= vence and os.path.isdir(_carpeta_invitado(usuario))
            return usuario if ok else None
        c = _usuarios().get(usuario)
        if not c or c.get('v', 1) != v or time.time() > vence or not c.get('activa', True):
            return None
        return usuario
    except Exception:
        return None


# ── prueba sin cuenta ─────────────────────────────────────────────────────────
def es_invitado(usuario):
    return bool(_RE_INVITADO.fullmatch(usuario or ''))


def _carpeta_invitado(usuario):
    return os.path.join(DATOS, 'invitados', usuario.split(':', 1)[1])


def abrir_invitado(environ):
    """(cookie, usuario, error). Crea la carpeta temporal de un visitante nuevo."""
    ahora = time.time()
    ip = direccion(environ)
    base = os.path.join(DATOS, 'invitados')
    with _lock:
        recientes = [t for t in _pruebas.get(ip, []) if ahora - t < VENTANA]
        if len(recientes) >= MAX_INVITADOS_DIRECCION:
            _pruebas[ip] = recientes
            return None, None, 'Demasiadas pruebas seguidas. Espera 15 minutos y vuelve a probar.'
        os.makedirs(base, mode=0o700, exist_ok=True)
        if len(os.listdir(base)) >= MAX_INVITADOS:
            return None, None, 'Ahora hay muchas pruebas en curso. Vuelve a intentarlo en un rato.'
        _pruebas[ip] = recientes + [ahora]
        vence = int(ahora) + DURACION_INVITADO
        usuario = f'invitado:{vence}-{secrets.token_hex(8)}'
        os.mkdir(_carpeta_invitado(usuario), 0o700)
    datos = _b64(json.dumps([usuario, vence, 'inv']).encode('utf-8'))
    return datos + '.' + _firma(datos), usuario, None


def cerrar_invitado(usuario):
    if es_invitado(usuario):
        shutil.rmtree(_carpeta_invitado(usuario), ignore_errors=True)


def purgar_invitados(todos=False):
    """Borra las pruebas vencidas (o todas, al arrancar). Devuelve los usuarios borrados."""
    base = os.path.join(DATOS, 'invitados')
    try:
        nombres = os.listdir(base)
    except FileNotFoundError:
        return []
    borrados = []
    for n in nombres:
        u = 'invitado:' + n
        m = _RE_INVITADO.fullmatch(u)
        if not m:
            continue   # no es nuestra: no se borra
        if todos or time.time() > int(m.group(1)):
            cerrar_invitado(u)
            borrados.append(u)
    return borrados


# ── dirección del visitante y bloqueo por fallos ──────────────────────────────
_LOCAL = ('127.0.0.1', '::1')


def direccion(environ):
    """La dirección REAL del visitante, para el bloqueo por fallos. Medido con el túnel de
    Cloudflare (5-nov-2026): todo llega desde 127.0.0.1 (cloudflared corre en esta Mac), con
    `CF-Connecting-IP` = la real y `X-Forwarded-For` = LO QUE MANDÓ EL VISITANTE + la real.
    ⚠️ El PRIMER valor de X-Forwarded-For lo escribe el visitante: tomarlo dejaba esquivar el
    bloqueo inventando una dirección por intento. Y sin esto, todos los del túnel serían
    '127.0.0.1': uno solo equivocándose 8 veces dejaba fuera a todos, también al dueño."""
    remota = environ.get('REMOTE_ADDR', '')
    cf = environ.get('HTTP_CF_CONNECTING_IP', '').strip()
    if cf and remota in _LOCAL:
        return cf        # túnel de Cloudflare: Cloudflare rechaza (403) a quien la inventa
    xff = environ.get('HTTP_X_FORWARDED_FOR')
    if DETRAS_DE_PROXY and xff:
        return xff.split(',')[-1].strip()   # el ÚLTIMO lo agrega el proxy de enfrente
    return remota


def es_esta_computadora(environ):
    # Si trae X-Forwarded-For o CF-Connecting-IP pasó por un proxy o el túnel: viene de fuera
    # aunque REMOTE_ADDR diga 127.0.0.1.
    return (environ.get('REMOTE_ADDR') in _LOCAL
            and not environ.get('HTTP_X_FORWARDED_FOR')
            and not environ.get('HTTP_CF_CONNECTING_IP'))


def _bloqueado(ip):
    ahora = time.time()
    with _lock:
        f = [t for t in _fallos.get(ip, []) if ahora - t < VENTANA]
        _fallos[ip] = f
        return len(f) >= MAX_FALLOS


def _anotar_fallo(ip):
    with _lock:
        _fallos.setdefault(ip, []).append(time.time())


def intentar_entrar(environ, usuario, clave):
    """None si entró; si no, el mensaje para la pantalla."""
    ip = direccion(environ)
    if _bloqueado(ip):
        return 'Demasiados intentos fallidos. Espera 15 minutos y vuelve a probar.'
    if _clave_ok(usuario, clave):
        with _lock:
            _fallos.pop(ip, None)
        return None
    _anotar_fallo(ip)
    return 'Usuario o contraseña incorrectos.'


# ── la pantalla de entrada ────────────────────────────────────────────────────
def pagina(modo, mensaje='', usuario=''):
    """modo: 'entrar' | 'crear' | 'cerrado' (aún no hay cuentas y no estás en el servidor)."""
    e = html.escape
    aviso = f'<p class="err">{e(mensaje)}</p>' if mensaje else ''
    prueba = ''
    if modo == 'crear':
        titulo, sub = 'Crea tu cuenta', 'Es la primera vez que se abre este servidor. Esta cuenta será la del dueño.'
        campos = ('<label>Usuario<input name="usuario" autocomplete="username" required value="' + e(usuario) + '"></label>'
                  '<label>Contraseña<input name="clave" type="password" autocomplete="new-password" required minlength="8"></label>'
                  '<label>Repite la contraseña<input name="clave2" type="password" autocomplete="new-password" required minlength="8"></label>'
                  '<button>Crear cuenta y entrar</button>')
        accion = '/crear'
    elif modo == 'cerrado':
        titulo, sub = 'Servidor sin cuentas', ('Todavía no hay ninguna cuenta. Por seguridad, la primera solo se crea '
                                               'desde la computadora donde corre el servidor (http://localhost).')
        campos, accion = '', ''
    else:
        titulo, sub = 'Entrar', 'Design Studio'
        campos = ('<label>Usuario<input name="usuario" autocomplete="username" required autofocus value="' + e(usuario) + '"></label>'
                  '<label>Contraseña<input name="clave" type="password" autocomplete="current-password" required></label>'
                  '<button>Entrar</button>')
        accion = '/entrar'
        if INVITADOS_ACTIVOS:
            prueba = ('<form method="post" action="/invitado" class="prueba"><button class="sec">Probar sin cuenta</button>'
                      '<p>No hace falta contraseña. Lo que cambies no se guarda.</p></form>')
    form = f'<form method="post" action="{accion}">{campos}</form>' if campos else ''
    return _marco('Entrar', titulo, sub, aviso + form + prueba)


def pagina_clave(mensaje='', obligada=False):
    aviso = f'<p class="err">{html.escape(mensaje)}</p>' if mensaje else ''
    sub = ('Tu contraseña es temporal: elige una que solo tú conozcas para seguir.' if obligada
           else 'Se cerrará tu sesión en los demás dispositivos.')
    volver = '<p class="pie"><a href="/salir">Salir</a></p>' if obligada else '<p class="pie"><a href="/">Volver a Design Studio</a></p>'
    form = ('<form method="post" action="/clave">'
            '<label>Contraseña actual<input name="actual" type="password" autocomplete="current-password" required autofocus></label>'
            '<label>Contraseña nueva<input name="nueva" type="password" autocomplete="new-password" required minlength="8"></label>'
            '<label>Repite la nueva<input name="nueva2" type="password" autocomplete="new-password" required minlength="8"></label>'
            '<button>Cambiar contraseña</button></form>')
    return _marco('Cambiar contraseña', 'Cambiar contraseña', sub, aviso + form + volver)


def pagina_cuentas(mensaje='', usuario_nuevo='', clave_nueva=''):
    """La pantalla del dueño. `clave_nueva` se muestra esta única vez: no queda guardada."""
    e = html.escape
    aviso = f'<p class="err">{e(mensaje)}</p>' if mensaje else ''
    if clave_nueva:
        aviso += (f'<div class="dato"><b>Contraseña temporal de {e(usuario_nuevo)}:</b><code>{e(clave_nueva)}</code>'
                  'Cópiala y pásasela ahora: no se vuelve a mostrar. Al entrar, tendrá que cambiarla.</div>')
    filas = []
    for c in cuentas():
        u = e(c['usuario'])
        def boton(accion, texto):
            return (f'<form method="post" action="/cuentas"><input type="hidden" name="accion" value="{accion}">'
                    f'<input type="hidden" name="usuario" value="{u}"><button class="chico">{texto}</button></form>')
        if es_dueno(c['usuario']):
            estado, botones = 'Dueño', ''
        elif not c['activa']:
            estado, botones = 'Desactivada', boton('activar', 'Activar')
        else:
            estado = 'Debe cambiar su contraseña' if c['cambiar'] else 'Activa'
            botones = boton('restablecer', 'Nueva contraseña') + boton('desactivar', 'Desactivar')
        filas.append(f'<li><div><b>{u}</b><span>{e(estado)} · desde {e(c["creado"])}</span></div><div class="acc">{botones}</div></li>')
    alta_form = ('<form method="post" action="/cuentas"><input type="hidden" name="accion" value="alta">'
                 '<label>Usuario de la cuenta nueva<input name="usuario" required autocomplete="off"></label>'
                 '<button>Crear cuenta</button></form>')
    cuerpo = (aviso + '<ul class="lista">' + ''.join(filas) + '</ul>' + alta_form +
              '<p class="pie"><a href="/">Volver a Design Studio</a></p>')
    return _marco('Cuentas', 'Cuentas', 'Cada cuenta tiene sus propias fresas, área de trabajo y autoguardado.', cuerpo, ancho=520)


def _marco(pestana, titulo, sub, cuerpo, ancho=360):
    e = html.escape
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Design Studio · {e(pestana)}</title>
<style>
:root{{--bg:#f4f4f2;--card:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#dcdcd6;--acc:#e8590c;--bad:#c92a2a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151515;--card:#1f1f1f;--ink:#ececea;--muted:#9a9a94;--line:#333;--acc:#ff7a2e;--bad:#ff6b6b}}}}
*{{box-sizing:border-box}} body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);
font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:16px}}
.card{{width:100%;max-width:{ancho}px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:28px 24px}}
h1{{font-size:21px;margin:0 0 4px}} .sub{{color:var(--muted);margin:0 0 20px;font-size:13.5px}}
label{{display:block;font-size:13px;font-weight:600;margin-bottom:14px}}
input{{display:block;width:100%;margin-top:6px;height:40px;border:1px solid var(--line);border-radius:8px;padding:0 12px;
font:inherit;background:var(--bg);color:var(--ink)}} input:focus{{outline:2px solid var(--acc);border-color:transparent}}
button{{width:100%;height:42px;border:0;border-radius:8px;background:var(--acc);color:#fff;font:inherit;font-weight:700;cursor:pointer;margin-top:4px}}
.err{{color:var(--bad);font-size:13.5px;margin:0 0 14px}}
button.sec{{background:transparent;color:var(--ink);border:1px solid var(--line)}}
.prueba{{margin-top:14px;padding-top:14px;border-top:1px solid var(--line)}} .prueba p{{margin:8px 0 0;font-size:12.5px;color:var(--muted);text-align:center}}
a{{color:var(--acc)}} .pie{{margin:16px 0 0;font-size:13.5px;text-align:center}}
.dato{{border:1px solid var(--acc);border-radius:8px;padding:12px;margin:0 0 16px;font-size:13.5px}}
.dato code{{display:block;margin:8px 0;font-size:16px;overflow-wrap:anywhere;user-select:all}}
.lista{{list-style:none;margin:0 0 20px;padding:0}} .lista li{{display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}}
.lista span{{display:block;color:var(--muted);font-size:12.5px}} .acc{{display:flex;gap:6px}}
button.chico{{width:auto;height:32px;padding:0 10px;margin:0;font-size:12.5px;font-weight:600;background:transparent;color:var(--ink);border:1px solid var(--line)}}
</style></head><body><div class="card"><h1>{e(titulo)}</h1><p class="sub">{e(sub)}</p>{cuerpo}</div></body></html>'''
