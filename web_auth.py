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
"""
import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.environ.get('DS_DATOS') or os.path.join(AQUI, 'datos_web')
COOKIE = 'ds_sesion'
DURACION = 30 * 24 * 3600          # la sesión dura 30 días
VUELTAS = 600_000                  # PBKDF2-SHA256: lo que recomienda OWASP hoy
MAX_FALLOS, VENTANA = 8, 15 * 60   # 8 fallos → 15 minutos de bloqueo
MIN_CLAVE = 8
# Detrás de un proxy (Railway, etc.) la dirección real del visitante viene en X-Forwarded-For.
# Solo se le cree si se avisa con DS_PROXY=1: si no, cualquiera podría inventarse una dirección.
DETRAS_DE_PROXY = os.environ.get('DS_PROXY') == '1'

_lock = threading.Lock()
_fallos = {}   # dirección → [horas de cada fallo reciente]


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


def crear_cuenta(usuario, clave):
    usuario = (usuario or '').strip().lower()
    if not re.fullmatch(r'[a-z0-9._-]{2,32}', usuario):
        return 'El usuario lleva de 2 a 32 letras sin acentos, números, punto, guion o guion bajo.'
    if len(clave or '') < MIN_CLAVE:
        return f'La contraseña necesita al menos {MIN_CLAVE} caracteres.'
    with _lock:
        u = _usuarios()
        if usuario in u:
            return 'Ese usuario ya existe.'
        sal = secrets.token_bytes(16)
        u[usuario] = {'sal': sal.hex(), 'huella': _huella(clave, sal), 'v': 1,
                      'creado': time.strftime('%Y-%m-%d %H:%M')}
        _guardar_usuarios(u)
    return None


def _clave_ok(usuario, clave):
    c = _usuarios().get((usuario or '').strip().lower())
    if not c:
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
        c = _usuarios().get(usuario)
        if not c or c.get('v', 1) != v or time.time() > vence:
            return None
        return usuario
    except Exception:
        return None


# ── dirección del visitante y bloqueo por fallos ──────────────────────────────
def direccion(environ):
    if DETRAS_DE_PROXY and environ.get('HTTP_X_FORWARDED_FOR'):
        return environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
    return environ.get('REMOTE_ADDR', '')


def es_esta_computadora(environ):
    # Si trae X-Forwarded-For pasó por un proxy: viene de fuera aunque REMOTE_ADDR diga 127.0.0.1.
    return (environ.get('REMOTE_ADDR') in ('127.0.0.1', '::1')
            and not environ.get('HTTP_X_FORWARDED_FOR'))


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
    form = f'<form method="post" action="{accion}">{campos}</form>' if campos else ''
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Design Studio · Entrar</title>
<style>
:root{{--bg:#f4f4f2;--card:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#dcdcd6;--acc:#e8590c;--bad:#c92a2a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151515;--card:#1f1f1f;--ink:#ececea;--muted:#9a9a94;--line:#333;--acc:#ff7a2e;--bad:#ff6b6b}}}}
*{{box-sizing:border-box}} body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);
font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:16px}}
.card{{width:100%;max-width:360px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:28px 24px}}
h1{{font-size:21px;margin:0 0 4px}} .sub{{color:var(--muted);margin:0 0 20px;font-size:13.5px}}
label{{display:block;font-size:13px;font-weight:600;margin-bottom:14px}}
input{{display:block;width:100%;margin-top:6px;height:40px;border:1px solid var(--line);border-radius:8px;padding:0 12px;
font:inherit;background:var(--bg);color:var(--ink)}} input:focus{{outline:2px solid var(--acc);border-color:transparent}}
button{{width:100%;height:42px;border:0;border-radius:8px;background:var(--acc);color:#fff;font:inherit;font-weight:700;cursor:pointer;margin-top:4px}}
.err{{color:var(--bad);font-size:13.5px;margin:0 0 14px}}
</style></head><body><div class="card"><h1>{e(titulo)}</h1><p class="sub">{e(sub)}</p>{aviso}{form}</div></body></html>'''
