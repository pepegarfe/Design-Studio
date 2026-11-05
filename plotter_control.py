#!/usr/bin/env python3
"""
Plotter Antike — Controlador de Plotter de Corte
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import contextvars
import math
import re
import os
import sys
import datetime
import json
from pathlib import Path


def _resource(filename):
    """Ruta a un recurso: funciona tanto como script como exe de PyInstaller."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / filename
    return Path(__file__).parent / filename


# Carpeta de config: <base del sistema>/<FABRICANTE>/<APP>. Convención Fabricante\Aplicación,
# la misma de `Google\Chrome`: así todos los programas de la casa viven juntos sin chocar con
# los de otros. Se renombró el 29-jul-2026 (antes `Antike/PlotterController`, heredado de la app
# vieja de tkinter y ya engañoso). Los nombres VIEJOS siguen aquí porque hay que migrar.
_FABRICANTE, _APP = 'BuiltByJose', 'DesignStudio'
_FABRICANTE_VIEJO, _APP_VIEJA = 'Antike', 'PlotterController'


def _config_base():
    """Carpeta del sistema donde va la config de cada usuario (sin fabricante ni app)."""
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support'
    if sys.platform == 'win32':
        # APPDATA (Roaming), no LOCALAPPDATA: los AJUSTES siguen al usuario entre máquinas.
        return Path(os.environ.get('APPDATA', str(Path.home())))
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))


def _migrar_config(base, nueva):
    """Copia de la carpeta vieja los archivos que TODAVÍA no estén en la nueva.

    ⚠️ COPIA, NO MUEVE, a propósito: ahí viven las fresas, materiales y presets del CNC.
    Si algo saliera mal, la carpeta vieja sigue intacta y se puede volver atrás a mano.

    ⚠️ Archivo por archivo, y NUNCA pisa uno que ya exista en la nueva. Antes esto era un
    `copytree` condicionado a que la carpeta nueva NO existiera, y era una trampa de un solo
    tiro: si la carpeta llegaba a crearse vacía (una copia a medias, un antivirus que bloquea
    un archivo), la migración no se reintentaba JAMÁS y el usuario se quedaba con los valores
    de fábrica creyendo que perdió su configuración. Así se reintenta hasta que sale."""
    try:
        minus = sys.platform not in ('darwin', 'win32')   # en Linux la costumbre es minúsculas
        vieja = base / (_FABRICANTE_VIEJO.lower() if minus else _FABRICANTE_VIEJO) \
                     / ('plotter-controller' if minus else _APP_VIEJA)
        if not vieja.is_dir():
            return
        import shutil
        nueva.mkdir(parents=True, exist_ok=True)
        for f in vieja.iterdir():
            destino = nueva / f.name
            if f.is_file() and not destino.exists():
                shutil.copy2(f, destino)
    except Exception:
        pass   # sin config previa, o sin permisos: se arranca con la de fábrica


# Versión web: la carpeta de la cuenta que hizo ESTE pedido (la pone studio_server.py). Es por
# pedido y no una variable común porque el servidor atiende a varios a la vez: con una variable
# común, un usuario leería la config del otro. En el escritorio siempre está vacía.
_CARPETA_USUARIO = contextvars.ContextVar('ds_carpeta_usuario', default=None)


def _config_path():
    """La config de la cuenta del pedido en curso (web) o la de la instalación (escritorio)."""
    d = _CARPETA_USUARIO.get()
    return Path(d) / 'plotter_config.json' if d else _config_compartida()


def _config_compartida():
    """Ruta persistente para la config: AppData/Library cuando es exe, dir del script si no."""
    if getattr(sys, 'frozen', False):
        base = _config_base()
        minus = sys.platform not in ('darwin', 'win32')
        d = base / (_FABRICANTE.lower() if minus else _FABRICANTE) / (_APP.lower() if minus else _APP)
        # ⚠️ La condición es "la carpeta nueva NO tiene config todavía", NO "la carpeta no
        # existe": esta misma función crea la carpeta dos líneas abajo, así que condicionar a
        # su existencia dejaba la migración muerta para siempre si alguna vez quedaba vacía.
        if not any((d / n).exists() for n in ('cnc_config.json', 'plotter_config.json')):
            _migrar_config(base, d)
        d.mkdir(parents=True, exist_ok=True)
        return d / 'plotter_config.json'
    return Path(__file__).parent / 'plotter_config.json'


def _get_version():
    try:
        # ⚠️ 'utf-8-sig', no 'utf-8': además de fijar el encoding, SE COME el BOM si lo hay.
        # `Out-File -Encoding utf8` de PowerShell 5.1 SIEMPRE mete BOM, y esos tres bytes
        # invisibles al inicio reventaban `--diagnostico` en Windows. Que el código aguante
        # el BOM es más fiable que confiar en que nadie escriba el archivo con la herramienta
        # equivocada.
        return _resource('version.txt').read_text(encoding='utf-8-sig').strip()
    except Exception:
        return "0.0.0"


VERSION = _get_version()
GITHUB_REPO = "pepegarfe/Design-Studio"


def _vkey(s):
    """Versión → tupla de números. Compararlas como TEXTO es un error: '2026.7.9'
    saldría mayor que '2026.7.10' porque '9' > '1' como letra."""
    return tuple(int(n) for n in re.findall(r'\d+', str(s or ''))[:4])

# ── Optional dependencies ──────────────────────────────────────────────────────

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

try:
    import svgpathtools
    HAS_SVG = True
except ImportError:
    HAS_SVG = False

try:
    import ezdxf
    HAS_DXF = True
except ImportError:
    HAS_DXF = False

try:
    import fitz  # pymupdf
    HAS_MUPDF = True
except ImportError:
    HAS_MUPDF = False


# ── Sistema de diseño (tokens) ──────────────────────────────────────────────────
# TODO el aspecto visual se decide aquí. Cambiar el look = cambiar estos valores,
# no cazar colores sueltos por todo el archivo.

# Fuentes nativas por plataforma (antes se pedían 'Segoe UI'/'Consolas', que sólo
# existen en Windows: en Mac caían en una fuente por defecto tosca).
if sys.platform == 'darwin':
    _UI_FAMILY, _MONO_FAMILY = 'Helvetica Neue', 'Menlo'
elif sys.platform == 'win32':
    _UI_FAMILY, _MONO_FAMILY = 'Segoe UI', 'Consolas'
else:
    _UI_FAMILY, _MONO_FAMILY = 'DejaVu Sans', 'DejaVu Sans Mono'


class UI:
    """Paleta y tipografía. Un solo neutro, un solo acento (magenta de corte)."""
    # Neutros (fondos y texto)
    BG        = '#f0f1ee'   # fondo general de la app
    SURFACE   = '#ffffff'   # campos, tarjetas
    SURFACE_2 = '#f6f7f4'   # superficie sutilmente hundida
    PANEL     = '#f2f3f0'   # barras laterales / paneles
    INK       = '#1b1e24'   # texto principal
    MUTED     = '#5c626d'   # texto secundario
    FAINT     = '#9299a3'   # texto tenue / etiquetas de sección
    LINE      = '#dfe1dc'   # separadores/bordes suaves
    LINE_2    = '#cdd0c9'   # bordes más marcados
    # Acento de marca — el magenta con que el software de corte marca las líneas
    ACCENT    = '#c81c68'
    ACCENT_DK = '#a5124f'   # hover / presionado
    ACCENT_FT = '#e2a6c1'   # acento deshabilitado
    ACCENT_SOFT = '#fbe7f0' # relleno de selección muy tenue
    # Estado (reservados: NO decorar con estos)
    GOOD      = '#2e7d57'
    BAD       = '#c0392b'
    WARN      = '#a9760f'
    # Lienzo
    CANVAS    = '#ffffff'
    GRID      = '#eaebe7'
    AXIS      = '#c9ccc5'
    ORIGIN    = '#c0392b'
    WORK_BG   = '#f4f6fb'   # relleno del área de trabajo (muy tenue)
    WORK_LINE = '#9bb0cc'   # borde del área de trabajo (azul calmado)
    SEL       = ACCENT      # trazado seleccionado (individual) → acento
    GROUP     = '#2f6fb0'   # selección de grupo / rectángulo de selección
    CUT       = '#0e8a7d'   # vectores de corte (teal, distinto de acento y grupo)


def _font(size, *style):
    return (_UI_FAMILY, size, *style)

def _mono(size, *style):
    return (_MONO_FAMILY, size, *style)

# Tipografía con una escala fija (antes: tamaños sueltos 8/9/10/13 sin criterio)
F_SECTION = _font(9)          # etiquetas de sección (mayúsculas)
F_SUB     = _font(9)          # sub-etiquetas ("paso", "mm")
F_LABEL   = _font(10)         # etiquetas de campo
F_BODY    = _font(11)         # cuerpo / controles
F_BTN     = _font(10)         # botones
F_SEND    = _font(11, 'bold') # botón principal
F_ICON    = _font(16)         # barra de iconos
F_MONO    = _mono(10)         # datos técnicos (versión, coordenadas)


# ── Color utilities ────────────────────────────────────────────────────────────

_SVG_NAMED = {
    'black':(0,0,0),'white':(1,1,1),'red':(1,0,0),'lime':(0,1,0),
    'blue':(0,0,1),'yellow':(1,1,0),'cyan':(0,1,1),'magenta':(1,0,1),
    'orange':(1,.647,0),'purple':(.502,0,.502),'green':(0,.502,0),
    'gray':(.502,.502,.502),'grey':(.502,.502,.502),'brown':(.647,.165,.165),
    'pink':(1,.753,.796),'navy':(0,0,.502),'teal':(0,.502,.502),
    'silver':(.753,.753,.753),'gold':(1,.843,0),
}

def _parse_svg_color(s):
    """SVG color string → (r,g,b) floats 0‥1, or None if transparent."""
    if not s:
        return (0, 0, 0)
    s = s.strip().lower()
    if s in ('none', 'transparent'):
        return None
    if s in _SVG_NAMED:
        return _SVG_NAMED[s]
    if s.startswith('#'):
        h = s[1:]
        if len(h) == 3:
            h = h[0]*2 + h[1]*2 + h[2]*2
        if len(h) >= 6:
            try:
                return (int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255)
            except ValueError:
                pass
    m = re.match(r'rgb\s*\(\s*([\d.]+%?)\s*,\s*([\d.]+%?)\s*,\s*([\d.]+%?)\s*\)', s)
    if m:
        def _v(t):
            if t.endswith('%'):
                return float(t[:-1]) / 100
            return float(t) / 255
        return tuple(_v(m.group(i)) for i in (1, 2, 3))
    return (0, 0, 0)

def _rgb_hex(rgb):
    """(r,g,b) floats 0‥1 → '#rrggbb'."""
    r, g, b = (max(0, min(255, int(c * 255))) for c in rgb)
    return f'#{r:02x}{g:02x}{b:02x}'

def _style_from_svg_attrs(attrs):
    """Extract (fill, stroke) from svgpathtools attribute dict."""
    fill_s  = attrs.get('fill',   'black')
    stroke_s = attrs.get('stroke', 'none')
    for decl in attrs.get('style', '').split(';'):
        if ':' in decl:
            p, v = decl.split(':', 1)
            p, v = p.strip().lower(), v.strip()
            if p == 'fill':   fill_s   = v
            elif p == 'stroke': stroke_s = v
    return _parse_svg_color(fill_s), _parse_svg_color(stroke_s)


# ── SVG transform helpers ─────────────────────────────────────────────────────

def _parse_svg_transform(s):
    """SVG transform attribute string → 6-tuple (a,b,c,d,e,f) affine matrix."""
    a, b, c, d, e, f = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0
    if not s:
        return (a, b, c, d, e, f)
    for m in re.finditer(r'(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)', s):
        func = m.group(1)
        nums = [float(x) for x in re.findall(
            r'[-+]?(?:[0-9]*\.)?[0-9]+(?:[eE][-+]?[0-9]+)?', m.group(2))]
        if func == 'translate':
            tx = nums[0] if nums else 0.0
            ty = nums[1] if len(nums) > 1 else 0.0
            e, f = a*tx + c*ty + e, b*tx + d*ty + f
        elif func == 'scale':
            sx = nums[0] if nums else 1.0
            sy = nums[1] if len(nums) > 1 else sx
            a *= sx; b *= sx; c *= sy; d *= sy
        elif func == 'rotate':
            ang = math.radians(nums[0]) if nums else 0.0
            ca, sa = math.cos(ang), math.sin(ang)
            if len(nums) >= 3:
                rcx, rcy = nums[1], nums[2]
                na = a*ca + c*sa;       nb = b*ca + d*sa
                nc = -a*sa + c*ca;      nd = -b*sa + d*ca
                ne = a*(rcx*(1-ca)+rcy*sa) + c*(rcy*(1-ca)-rcx*sa) + e
                nf = b*(rcx*(1-ca)+rcy*sa) + d*(rcy*(1-ca)-rcx*sa) + f
                a, b, c, d, e, f = na, nb, nc, nd, ne, nf
            else:
                na = a*ca + c*sa;  nc = -a*sa + c*ca
                nb = b*ca + d*sa;  nd = -b*sa + d*ca
                a, b, c, d = na, nb, nc, nd
        elif func == 'matrix' and len(nums) >= 6:
            ma, mb, mc, md, me, mf = nums[:6]
            na = a*ma + c*mb;  nc = a*mc + c*md;  ne = a*me + c*mf + e
            nb = b*ma + d*mb;  nd = b*mc + d*md;  nf = b*me + d*mf + f
            a, b, c, d, e, f = na, nb, nc, nd, ne, nf
    return (a, b, c, d, e, f)

def _compose_mtx(m1, m2):
    """Compose two affine matrices: result = m1 * m2 (m2 applied first)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (a1*a2 + c1*b2, b1*a2 + d1*b2,
            a1*c2 + c1*d2, b1*c2 + d1*d2,
            a1*e2 + c1*f2 + e1, b1*e2 + d1*f2 + f1)

def _apply_mtx(pts, mtx):
    """Apply affine matrix (a,b,c,d,e,f) to a list of (x,y) points."""
    a, b, c, d, e, f = mtx
    return [(a*x + c*y + e, b*x + d*y + f) for x, y in pts]


# ── HPGL Converter ─────────────────────────────────────────────────────────────

def _rdp_simplify(pts, tol):
    """Ramer-Douglas-Peucker path simplification. Returns subset of pts within tol."""
    if len(pts) <= 2:
        return list(pts)
    ax, ay = pts[0]
    bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    dlen = math.hypot(dx, dy)
    max_d, max_i = 0.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        if dlen > 1e-12:
            d = abs(dx * (ay - py) - (ax - px) * dy) / dlen
        else:
            d = math.hypot(px - ax, py - ay)
        if d > max_d:
            max_d, max_i = d, i
    if max_d > tol:
        left  = _rdp_simplify(pts[:max_i + 1], tol)
        right = _rdp_simplify(pts[max_i:], tol)
        return left[:-1] + right
    return [pts[0], pts[-1]]


class HPGLConverter:
    """Convierte paths vectoriales a comandos HPGL."""

    UNITS_PER_MM = 40  # 1 unidad HPGL = 0.025 mm

    def __init__(self, speed=100, pressure=100, overcut_mm=0.0, corner_angle_deg=0.0):
        self.speed            = max(10, min(800, speed))
        self.pressure         = max(10, min(500, pressure))
        self.overcut_mm       = max(0.0, overcut_mm)
        self.corner_angle_deg = max(0.0, min(175.0, corner_angle_deg))
        self.commands         = []

    def _u(self, mm):
        return int(round(mm * self.UNITS_PER_MM))

    def initialize(self):
        self.commands = []
        self.commands.append("IN;")
        self.commands.append("PA;")          # coordenadas absolutas (explícito)
        self.commands.append("SP1;")
        self.commands.append(f"VS{self.speed};")
        self.commands.append(f"FS{self.pressure};")

    def add_path(self, points):
        """Agrega un path como lista de (x, y) en mm.

        Todos los puntos de un segmento continuo se emiten en UN SOLO comando PD
        (PD x1,y1,x2,y2,...). Esto le da al plotter visibilidad completa del
        trazado y le permite planificar la velocidad correctamente en esquinas,
        igual que los programas de corte comerciales. Con PD separados el plotter
        no puede anticipar las esquinas y las redondea.

        Con forzado de esquinas activado, el trazado se corta en cada esquina
        detectada con PU; entre segmentos, obligando al plotter a detenerse.
        """
        if len(points) < 2:
            return

        # Simplify for HPGL transmission — 0.025 mm = 1 HPGL unit, invisible to cutter
        points = _rdp_simplify(list(points), 0.025)
        if len(points) < 2:
            return

        x0, y0 = points[0]
        self.commands.append(f"PU{self._u(x0)},{self._u(y0)};")

        # Detectar índices de esquinas para dividir el trazado
        cos_corner = (math.cos(math.radians(self.corner_angle_deg))
                      if self.corner_angle_deg > 0 else None)
        corner_indices = set()
        if cos_corner is not None:
            for idx in range(1, len(points) - 1):
                px, py = points[idx - 1]
                x,  y  = points[idx]
                nx, ny = points[idx + 1]
                dx1, dy1 = x - px, y - py
                dx2, dy2 = nx - x,  ny - y
                l1 = math.hypot(dx1, dy1)
                l2 = math.hypot(dx2, dy2)
                if l1 > 1e-9 and l2 > 1e-9:
                    c = max(-1.0, min(1.0, (dx1*dx2 + dy1*dy2) / (l1 * l2)))
                    if c < cos_corner:
                        corner_indices.add(idx)

        # Emitir segmentos como PD consolidados; PU; entre segmentos en esquinas
        seg = []
        for idx in range(1, len(points)):
            x, y = points[idx]
            seg.append(f"{self._u(x)},{self._u(y)}")
            if idx in corner_indices:
                self.commands.append(f"PD{','.join(seg)};")
                self.commands.append("PU;")
                seg = []
        if seg:
            self.commands.append(f"PD{','.join(seg)};")

        # Sobrecore: en trazados cerrados continúa cortando desde el inicio
        if self.overcut_mm > 0 and len(points) >= 3:
            is_closed = math.hypot(points[-1][0] - points[0][0],
                                   points[-1][1] - points[0][1]) < 0.1
            if is_closed:
                remaining = self.overcut_mm
                for i in range(1, len(points)):
                    xa, ya = points[i - 1]
                    xb, yb = points[i]
                    seg_len = math.hypot(xb - xa, yb - ya)
                    if seg_len < 1e-9:
                        continue
                    if seg_len >= remaining:
                        t = remaining / seg_len
                        self.commands.append(
                            f"PD{self._u(xa + t*(xb-xa))},{self._u(ya + t*(yb-ya))};")
                        break
                    self.commands.append(f"PD{self._u(xb)},{self._u(yb)};")
                    remaining -= seg_len
        self.commands.append("PU;")

    def finalize(self):
        self.commands.append("PU0,0;")
        self.commands.append("SP0;")

    def get_hpgl(self):
        return "\n".join(self.commands)

    def test_square(self, size_mm=10):
        self.initialize()
        pts = [(0, 0), (size_mm, 0), (size_mm, size_mm), (0, size_mm), (0, 0)]
        self.add_path(pts)
        self.finalize()
        return self.get_hpgl()


# ── SVG Parser ─────────────────────────────────────────────────────────────────
# Todos los parsers devuelven List[dict]:
#   {"pts": [(x,y)…], "fill": (r,g,b)|None, "stroke": (r,g,b)|None}

def _simplify_mm(pts, tol=0.001):
    """Douglas-Peucker iterativo en MILÍMETROS (post-matriz): quita los puntos que no
    aportan (desviación < tol). Es la pasada de limpieza estándar de los importadores CAM
    y atrapa TODAS las fuentes de sobre-muestreo (transforms anidados incluidos)."""
    n = len(pts)
    if n < 3:
        return pts
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        ax, ay = pts[i0]; bx, by = pts[i1]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        worst, wi = -1.0, -1
        for i in range(i0 + 1, i1):
            px, py = pts[i]
            if L < 1e-12:
                d = math.hypot(px - ax, py - ay)
            else:
                d = abs((px - ax) * dy - (py - ay) * dx) / L
            if d > worst:
                worst, wi = d, i
        if worst > tol:
            keep[wi] = True
            stack.append((i0, wi))
            stack.append((wi, i1))
    return [pts[i] for i in range(n) if keep[i]]


def _simplify_styled(styled, tol=0.001):
    for d in styled:
        p = d.get('pts')
        if p and len(p) > 3:
            d['pts'] = _simplify_mm(p, tol)
    return styled


def _curve_tol(pts, floor=0.0):
    """Tolerancia RELATIVA al tamaño de la curva (~0.015% de su diagonal), con un PISO
    absoluto (en unidades del archivo, ≈0.01mm reales vía la escala de la matriz raíz).
    Relativa: escalar el diseño después conserva la suavidad visual. El piso evita que los
    trazos hechos de CIENTOS de mini-curvas (potrace, tipografías) exijan precisión
    microscópica por tramo y exploten en puntos."""
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    return max(diag * 1e-5, floor, 1e-9)


def _flat_cubic(p0, p1, p2, p3, floor=0.0):
    """Aplana una Bézier cúbica por subdivisión adaptativa (De Casteljau), como los motores
    de los programas de diseño: puntos SOLO donde la curva lo pide, con desviación acotada.
    Devuelve los puntos SIN incluir p0."""
    tol = _curve_tol((p0, p1, p2, p3), floor)
    out = []

    def rec(a, b, c, d, depth):
        dx, dy = d[0] - a[0], d[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 1e-12:
            d1 = math.hypot(b[0] - a[0], b[1] - a[1])
            d2 = math.hypot(c[0] - a[0], c[1] - a[1])
        else:
            d1 = abs((b[0] - a[0]) * dy - (b[1] - a[1]) * dx) / L
            d2 = abs((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / L
        if depth >= 16 or (d1 + d2) <= tol:
            out.append(d)
            return
        ab  = ((a[0]+b[0])/2, (a[1]+b[1])/2); bc  = ((b[0]+c[0])/2, (b[1]+c[1])/2)
        cd  = ((c[0]+d[0])/2, (c[1]+d[1])/2)
        abc = ((ab[0]+bc[0])/2, (ab[1]+bc[1])/2); bcd = ((bc[0]+cd[0])/2, (bc[1]+cd[1])/2)
        mid = ((abc[0]+bcd[0])/2, (abc[1]+bcd[1])/2)
        rec(a, ab, abc, mid, depth + 1)
        rec(mid, bcd, cd, d, depth + 1)

    rec(p0, p1, p2, p3, 0)
    return out


def _flat_quad(p0, q, p1, floor=0.0):
    """Bézier cuadrática → cúbica equivalente → aplanado adaptativo."""
    c1 = (p0[0] + 2.0/3.0 * (q[0] - p0[0]), p0[1] + 2.0/3.0 * (q[1] - p0[1]))
    c2 = (p1[0] + 2.0/3.0 * (q[0] - p1[0]), p1[1] + 2.0/3.0 * (q[1] - p1[1]))
    return _flat_cubic(p0, c1, c2, p1, floor)


def _arc_steps(r, dtheta, floor=0.0):
    """Pasos para un arco con desviación (sagita) ≤ tolerancia relativa al radio."""
    tol = max(r * 1e-5, floor, 1e-9)
    arg = max(-1.0, min(1.0, 1.0 - tol / max(r, 1e-9)))
    step = 2 * math.acos(arg) or 0.05
    return max(8, min(720, int(math.ceil(abs(dtheta) / step))))


class SVGParser:
    PX_TO_MM = 0.264583  # 96 DPI
    _SKIP_TAGS = {'defs', 'clipPath', 'mask', 'symbol', 'pattern', 'marker'}

    def parse(self, filepath):
        return _simplify_styled(self._parse_basic(filepath))

    # ── deduplication ──────────────────────────────────────────────────────────

    @staticmethod
    def _fp(pts):
        n = len(pts)
        idx = sorted({0, n//4, n//2, 3*n//4, n-1})
        return tuple(round(pts[i][j] * 2) / 2 for i in idx for j in range(2))

    def _dedup(self, styled):
        seen, result = set(), []
        for d in styled:
            pts = d["pts"]
            if len(pts) < 2:
                continue
            fp = self._fp(pts)
            if fp not in seen:
                seen.add(fp)
                result.append(d)
        return result

    # ── svgpathtools path ──────────────────────────────────────────────────────

    def _parse_with_lib(self, filepath):
        paths, attrs = svgpathtools.svg2paths(filepath)
        result = []
        for path, attr in zip(paths, attrs):
            fill, stroke = _style_from_svg_attrs(attr)
            current = []
            for seg in path:
                try:
                    length = abs(seg.length())
                except Exception:
                    length = 10
                n = max(4, int(length))
                # Detect discontinuity (implicit M between subpaths)
                if current:
                    sx = seg.start.real * self.PX_TO_MM
                    sy = seg.start.imag * self.PX_TO_MM
                    if abs(sx - current[-1][0]) > 0.1 or abs(sy - current[-1][1]) > 0.1:
                        if len(current) >= 2:
                            result.append({"pts": current, "fill": fill, "stroke": stroke})
                        current = [(sx, sy)]
                if not current:
                    sp = seg.point(0)
                    current = [(sp.real * self.PX_TO_MM, sp.imag * self.PX_TO_MM)]
                for i in range(1, n + 1):
                    pt = seg.point(i / n)
                    current.append((pt.real * self.PX_TO_MM, pt.imag * self.PX_TO_MM))
            if len(current) >= 2:
                result.append({"pts": current, "fill": fill, "stroke": stroke})
        return self._dedup(result)

    # ── XML parser (primary) ──────────────────────────────────────────────────

    @staticmethod
    def _parse_length(s):
        """SVG length string with optional unit → pixels (96 dpi reference)."""
        if not s:
            return None
        s = s.strip()
        for unit, f in (('px', 1.0), ('pt', 96/72), ('pc', 16.0),
                        ('mm', 96/25.4), ('cm', 9600/25.4), ('in', 96.0)):
            if s.endswith(unit):
                try:
                    return float(s[:-len(unit)]) * f
                except ValueError:
                    return None
        try:
            return float(s)
        except ValueError:
            return None

    def _root_mtx(self, root):
        """Compute user-units → mm affine matrix from SVG root viewBox + width/height."""
        vb_str = root.get('viewBox') or root.get('viewbox')
        w_str  = root.get('width')
        h_str  = root.get('height')
        sx = self.PX_TO_MM
        sy = self.PX_TO_MM
        tx = ty = 0.0
        if vb_str:
            nums = [float(x) for x in re.findall(
                r'[-+]?(?:[0-9]*\.)?[0-9]+(?:[eE][-+]?[0-9]+)?', vb_str)]
            if len(nums) >= 4:
                vb_x, vb_y, vb_w, vb_h = nums[:4]
                vp_w = self._parse_length(w_str) if w_str else None
                vp_h = self._parse_length(h_str) if h_str else None
                if vp_w and vb_w:
                    sx = vp_w / vb_w * self.PX_TO_MM
                if vp_h and vb_h:
                    sy = vp_h / vb_h * self.PX_TO_MM
                else:
                    sy = sx
                tx = -vb_x * sx
                ty = -vb_y * sy
        return (sx, 0.0, 0.0, sy, tx, ty)

    def _parse_basic(self, filepath):
        import xml.etree.ElementTree as ET
        root = ET.parse(filepath).getroot()
        mtx = self._root_mtx(root)
        # piso de aplanado: 0.01 mm reales convertidos a user-units con la escala raíz
        self._flat_floor = 0.001 / max(abs(mtx[0]), abs(mtx[3]), 1e-9)
        result = []
        self._walk(root, result, (0, 0, 0), None, mtx)
        return self._dedup(result)

    def _elem_style(self, elem, parent_fill, parent_stroke):
        """Extrae fill/stroke del elemento, respetando herencia del padre."""
        fill_s  = elem.get('fill')
        stroke_s = elem.get('stroke')
        for decl in elem.get('style', '').split(';'):
            if ':' in decl:
                p, v = decl.split(':', 1)
                p, v = p.strip().lower(), v.strip()
                if p == 'fill':   fill_s   = v
                elif p == 'stroke': stroke_s = v
        fill   = _parse_svg_color(fill_s)   if fill_s   is not None else parent_fill
        stroke = _parse_svg_color(stroke_s) if stroke_s is not None else parent_stroke
        return fill, stroke

    def _walk(self, elem, result, parent_fill, parent_stroke, mtx):
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag in self._SKIP_TAGS:
            return
        fill, stroke = self._elem_style(elem, parent_fill, parent_stroke)
        # Compose this element's own transform with the inherited matrix
        tf_str = elem.get('transform', '')
        cur_mtx = _compose_mtx(mtx, _parse_svg_transform(tf_str)) if tf_str else mtx
        if tag == 'path':
            d = elem.get('d', '')
            if d:
                for pts_uu in self._parse_d(d):
                    if len(pts_uu) >= 2:
                        result.append({"pts": _apply_mtx(pts_uu, cur_mtx),
                                       "fill": fill, "stroke": stroke})
        else:
            pts_uu = None
            if tag == 'rect':
                pts_uu = self._parse_rect(elem)
            elif tag in ('circle', 'ellipse'):
                pts_uu = self._parse_circle(elem)
            elif tag == 'line':
                pts_uu = self._parse_line(elem)
            elif tag == 'polyline':
                pts_uu = self._parse_poly(elem, closed=False)
            elif tag == 'polygon':
                pts_uu = self._parse_poly(elem, closed=True)
            if pts_uu and len(pts_uu) >= 2:
                result.append({"pts": _apply_mtx(pts_uu, cur_mtx),
                               "fill": fill, "stroke": stroke})
        for child in elem:
            self._walk(child, result, fill, stroke, cur_mtx)

    def _arc_pts(self, x1, y1, rx, ry, phi_deg, large_arc, sweep, x2, y2):
        """SVG arc endpoint params → list of (x,y) sample points (excluding start, px units)."""
        if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
            return [(x2, y2)]
        phi = math.radians(phi_deg)
        cos_p, sin_p = math.cos(phi), math.sin(phi)
        rx, ry = abs(rx), abs(ry)
        dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
        x1p =  cos_p * dx + sin_p * dy
        y1p = -sin_p * dx + cos_p * dy
        lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
        if lam > 1:
            s = math.sqrt(lam)
            rx *= s; ry *= s
        num = max(0, (rx * ry) ** 2 - (rx * y1p) ** 2 - (ry * x1p) ** 2)
        den = (rx * y1p) ** 2 + (ry * x1p) ** 2
        sq = math.sqrt(num / den) if den else 0
        if large_arc == sweep:
            sq = -sq
        cxp =  sq * rx * y1p / ry
        cyp = -sq * ry * x1p / rx
        cx = cos_p * cxp - sin_p * cyp + (x1 + x2) / 2
        cy = sin_p * cxp + cos_p * cyp + (y1 + y2) / 2

        def _angle(ux, uy, vx, vy):
            d = math.hypot(ux, uy) * math.hypot(vx, vy)
            if d == 0:
                return 0.0
            a = math.acos(max(-1.0, min(1.0, (ux * vx + uy * vy) / d)))
            return -a if ux * vy - uy * vx < 0 else a

        theta1 = _angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
        dtheta = _angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                        (-x1p - cxp) / rx, (-y1p - cyp) / ry)
        if not sweep and dtheta > 0:
            dtheta -= 2 * math.pi
        elif sweep and dtheta < 0:
            dtheta += 2 * math.pi

        n = _arc_steps(max(rx, ry), dtheta, getattr(self, '_flat_floor', 0.0))
        result = []
        for k in range(1, n + 1):
            th = theta1 + dtheta * k / n
            xp = cos_p * rx * math.cos(th) - sin_p * ry * math.sin(th) + cx
            yp = sin_p * rx * math.cos(th) + cos_p * ry * math.sin(th) + cy
            result.append((xp, yp))
        return result

    def _parse_d(self, d):
        """Parse SVG path d attribute. Returns List[List[(x_uu, y_uu)]] in user units."""
        tokens = re.findall(
            r'[MLHVCSQTAZmlhvcsqtaz]|[-+]?(?:[0-9]*\.)?[0-9]+(?:[eE][-+]?[0-9]+)?', d)
        subpaths = []
        current  = []
        cx, cy   = 0.0, 0.0   # current point (px)
        sx, sy   = 0.0, 0.0   # subpath start (px)
        pcx, pcy = None, None  # prev cubic control point (for S/s)
        pqx, pqy = None, None  # prev quadratic control point (for T/t)
        cmd      = 'M'
        i        = 0

        def _flush():
            nonlocal current
            if len(current) >= 2:
                subpaths.append(current)
            current = []

        while i < len(tokens):
            tok = tokens[i]
            if tok.isalpha():
                cmd = tok
                i += 1
                if cmd in ('Z', 'z'):
                    if current:
                        if (cx, cy) != (sx, sy):
                            current.append((sx, sy))
                        _flush()
                    cx, cy = sx, sy
                    pcx = pcy = pqx = pqy = None
                continue

            try:
                if cmd in ('M', 'm'):
                    x, y = float(tokens[i]), float(tokens[i + 1])
                    if cmd == 'm':
                        x += cx; y += cy
                    _flush()
                    cx, cy = x, y
                    sx, sy = cx, cy
                    current = [(cx, cy)]
                    pcx = pcy = pqx = pqy = None
                    i += 2
                    cmd = 'L' if cmd == 'M' else 'l'

                elif cmd in ('L', 'l'):
                    x, y = float(tokens[i]), float(tokens[i + 1])
                    if cmd == 'l':
                        x += cx; y += cy
                    cx, cy = x, y
                    current.append((cx, cy))
                    pcx = pcy = pqx = pqy = None
                    i += 2

                elif cmd in ('H', 'h'):
                    x = float(tokens[i])
                    if cmd == 'h':
                        x += cx
                    cx = x
                    current.append((cx, cy))
                    pcx = pcy = pqx = pqy = None
                    i += 1

                elif cmd in ('V', 'v'):
                    y = float(tokens[i])
                    if cmd == 'v':
                        y += cy
                    cy = y
                    current.append((cx, cy))
                    pcx = pcy = pqx = pqy = None
                    i += 1

                elif cmd in ('C', 'c'):
                    x1, y1 = float(tokens[i]),     float(tokens[i + 1])
                    x2, y2 = float(tokens[i + 2]), float(tokens[i + 3])
                    x,  y  = float(tokens[i + 4]), float(tokens[i + 5])
                    if cmd == 'c':
                        x1 += cx; y1 += cy
                        x2 += cx; y2 += cy
                        x  += cx; y  += cy
                    current.extend(_flat_cubic((cx, cy), (x1, y1), (x2, y2), (x, y), self._flat_floor))
                    pcx, pcy = x2, y2
                    pqx = pqy = None
                    cx, cy = x, y
                    i += 6

                elif cmd in ('S', 's'):
                    x2, y2 = float(tokens[i]),     float(tokens[i + 1])
                    x,  y  = float(tokens[i + 2]), float(tokens[i + 3])
                    if cmd == 's':
                        x2 += cx; y2 += cy
                        x  += cx; y  += cy
                    x1 = 2 * cx - pcx if pcx is not None else cx
                    y1 = 2 * cy - pcy if pcy is not None else cy
                    current.extend(_flat_cubic((cx, cy), (x1, y1), (x2, y2), (x, y), self._flat_floor))
                    pcx, pcy = x2, y2
                    pqx = pqy = None
                    cx, cy = x, y
                    i += 4

                elif cmd in ('Q', 'q'):
                    x1, y1 = float(tokens[i]),     float(tokens[i + 1])
                    x,  y  = float(tokens[i + 2]), float(tokens[i + 3])
                    if cmd == 'q':
                        x1 += cx; y1 += cy
                        x  += cx; y  += cy
                    current.extend(_flat_quad((cx, cy), (x1, y1), (x, y), self._flat_floor))
                    pqx, pqy = x1, y1
                    pcx = pcy = None
                    cx, cy = x, y
                    i += 4

                elif cmd in ('T', 't'):
                    x, y = float(tokens[i]), float(tokens[i + 1])
                    if cmd == 't':
                        x += cx; y += cy
                    x1 = 2 * cx - pqx if pqx is not None else cx
                    y1 = 2 * cy - pqy if pqy is not None else cy
                    current.extend(_flat_quad((cx, cy), (x1, y1), (x, y), self._flat_floor))
                    pqx, pqy = x1, y1
                    pcx = pcy = None
                    cx, cy = x, y
                    i += 2

                elif cmd in ('A', 'a'):
                    rx_a = abs(float(tokens[i]))
                    ry_a = abs(float(tokens[i + 1]))
                    phi  =     float(tokens[i + 2])
                    la   = int(float(tokens[i + 3]))
                    sw   = int(float(tokens[i + 4]))
                    x, y = float(tokens[i + 5]), float(tokens[i + 6])
                    if cmd == 'a':
                        x += cx; y += cy
                    current.extend(self._arc_pts(cx, cy, rx_a, ry_a, phi, la, sw, x, y))
                    pcx = pcy = pqx = pqy = None
                    cx, cy = x, y
                    i += 7

                else:
                    i += 1

            except (IndexError, ValueError):
                i += 1

        _flush()
        return subpaths

    def _parse_rect(self, elem):
        try:
            x = float(elem.get('x', 0))
            y = float(elem.get('y', 0))
            w = float(elem.get('width', 0))
            h = float(elem.get('height', 0))
            return [(x, y), (x+w, y), (x+w, y+h), (x, y+h), (x, y)]
        except Exception:
            return []

    def _parse_circle(self, elem):
        try:
            cx = float(elem.get('cx', 0))
            cy = float(elem.get('cy', 0))
            rx = float(elem.get('r', elem.get('rx', 0)))
            ry = float(elem.get('ry', elem.get('r', 0)))
            n = _arc_steps(max(rx, ry), 2 * math.pi, getattr(self, '_flat_floor', 0.0))
            pts = []
            for i in range(n + 1):
                a = 2 * math.pi * i / n
                pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
            return pts
        except Exception:
            return []

    def _parse_line(self, elem):
        try:
            x1 = float(elem.get('x1', 0))
            y1 = float(elem.get('y1', 0))
            x2 = float(elem.get('x2', 0))
            y2 = float(elem.get('y2', 0))
            return [(x1, y1), (x2, y2)]
        except Exception:
            return []

    def _parse_poly(self, elem, closed=False):
        try:
            nums = list(map(float, re.findall(r'[-+]?[0-9]*\.?[0-9]+', elem.get('points', ''))))
            pts = [(nums[i], nums[i+1]) for i in range(0, len(nums)-1, 2)]
            if closed and pts:
                pts.append(pts[0])
            return pts
        except Exception:
            return []


# ── DXF Parser ─────────────────────────────────────────────────────────────────

# ACI color index → (r,g,b) 0..1  (basic subset)
_ACI = {1:(1,0,0),2:(1,1,0),3:(0,1,0),4:(0,1,1),5:(0,0,1),
        6:(1,0,1),7:(1,1,1),8:(.416,.416,.416),9:(.753,.753,.753)}

class DXFParser:
    # Tolerancia de aplanado en UNIDADES DEL DIBUJO. ⚠️ Se recalcula en parse() con la
    # escala $INSUNITS: un DXF declarado en metros o pulgadas escala DESPUÉS del muestreo,
    # y una tolerancia fija de 0.001 unidades se volvía 1 mm reales (curvas cuadriculadas).
    _TOL = 0.001
    # Endpoint-matching tolerance for path chaining (two points are "same" if closer than this)
    _CHAIN_TOL = 0.01

    def _color(self, entity):
        try:
            return _ACI.get(entity.dxf.color, (0, 0, 0))
        except Exception:
            return (0, 0, 0)

    def _wrap(self, pts, color):
        return {"pts": pts, "fill": None, "stroke": color}

    def _arc_pts(self, cx, cy, r, sa_deg, ea_deg):
        """Sample a DXF arc (degrees, CCW) → list of (x,y) with deviation ≤ _TOL."""
        if r <= 0:
            return []
        sa = math.radians(sa_deg)
        ea = math.radians(ea_deg)
        if ea <= sa:
            ea += 2 * math.pi
        span = ea - sa
        tol = max(getattr(self, '_tol', self._TOL), r * 1e-5)
        arg = max(-1.0, min(1.0, 1.0 - tol / r))
        n_full = max(48, math.ceil(math.pi / math.acos(arg)))
        n = max(12, math.ceil(n_full * span / (2 * math.pi)))
        return [(cx + r * math.cos(sa + span * k / n),
                 cy + r * math.sin(sa + span * k / n))
                for k in range(n + 1)]

    def _circle_pts(self, cx, cy, r):
        """Sample a full circle → closed point list with deviation ≤ _TOL."""
        if r <= 0:
            return []
        tol = max(getattr(self, '_tol', self._TOL), r * 1e-5)
        arg = max(-1.0, min(1.0, 1.0 - tol / r))
        n = max(48, math.ceil(math.pi / math.acos(arg)))
        pts = [(cx + r * math.cos(2 * math.pi * k / n),
                cy + r * math.sin(2 * math.pi * k / n))
               for k in range(n)]
        pts.append(pts[0])
        return pts

    def _collect(self, entity, result, color, depth=0):
        if depth > 12:
            return
        t = entity.dxftype()
        try:
            if t == 'LINE':
                s, e = entity.dxf.start, entity.dxf.end
                result.append(self._wrap([(s.x, s.y), (e.x, e.y)], color))

            elif t == 'LWPOLYLINE':
                pts = []
                for seg in entity.virtual_entities():
                    st = seg.dxftype()
                    if st == 'LINE':
                        s, e = seg.dxf.start, seg.dxf.end
                        if not pts:
                            pts.append((s.x, s.y))
                        pts.append((e.x, e.y))
                    elif st == 'ARC':
                        arc = self._arc_pts(
                            seg.dxf.center.x, seg.dxf.center.y, seg.dxf.radius,
                            seg.dxf.start_angle, seg.dxf.end_angle)
                        pts.extend(arc[1:] if pts else arc)
                if entity.closed and len(pts) >= 2:
                    if abs(pts[0][0]-pts[-1][0]) > 1e-9 or abs(pts[0][1]-pts[-1][1]) > 1e-9:
                        pts.append(pts[0])
                if len(pts) >= 2:
                    result.append(self._wrap(pts, color))

            elif t == 'POLYLINE':
                pts = []
                for seg in entity.virtual_entities():
                    st = seg.dxftype()
                    if st == 'LINE':
                        s, e = seg.dxf.start, seg.dxf.end
                        if not pts:
                            pts.append((s.x, s.y))
                        pts.append((e.x, e.y))
                    elif st == 'ARC':
                        arc = self._arc_pts(
                            seg.dxf.center.x, seg.dxf.center.y, seg.dxf.radius,
                            seg.dxf.start_angle, seg.dxf.end_angle)
                        pts.extend(arc[1:] if pts else arc)
                if not pts:  # fallback: read vertices directly
                    pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                if entity.is_closed and pts:
                    pts.append(pts[0])
                if len(pts) >= 2:
                    result.append(self._wrap(pts, color))

            elif t == 'CIRCLE':
                c, r = entity.dxf.center, entity.dxf.radius
                pts = self._circle_pts(c.x, c.y, r)
                if pts:
                    result.append(self._wrap(pts, color))

            elif t == 'ARC':
                c, r = entity.dxf.center, entity.dxf.radius
                pts = self._arc_pts(c.x, c.y, r,
                                    entity.dxf.start_angle, entity.dxf.end_angle)
                if len(pts) >= 2:
                    result.append(self._wrap(pts, color))

            elif t in ('ELLIPSE', 'SPLINE'):
                # tolerancia = piso absoluto (0.01mm reales) + componente RELATIVA al tamaño
                # de la entidad (a prueba de que el usuario escale el diseño después)
                try:
                    _cps = [(float(p[0]), float(p[1])) for p in entity.control_points]
                    _dg = math.hypot(max(c[0] for c in _cps) - min(c[0] for c in _cps),
                                     max(c[1] for c in _cps) - min(c[1] for c in _cps))
                except Exception:
                    _dg = 0.0
                _t = max(getattr(self, '_tol', self._TOL), _dg * 1e-5)
                pts = [(p[0], p[1]) for p in entity.flattening(_t)]
                if len(pts) >= 2:
                    result.append(self._wrap(pts, color))

            elif t == 'INSERT':
                col = self._color(entity)
                for e in entity.virtual_entities():
                    self._collect(e, result, col, depth + 1)

        except Exception:
            pass

    def _chain_paths(self, paths):
        """Merge end-to-end connected segments into single continuous paths.

        Eliminates the visual 'cut' artifact that appears where two separate
        create_line calls share an endpoint (each draws its own round cap).
        """
        if not paths:
            return paths
        t = self._CHAIN_TOL

        def key(pt):
            return (round(pt[0] / t), round(pt[1] / t))

        # Build endpoint index: rounded_key → [(path_idx, is_start), ...]
        from collections import defaultdict
        ep = defaultdict(list)
        for i, d in enumerate(paths):
            pts = d['pts']
            if len(pts) < 2:
                continue
            ep[key(pts[0])].append((i, True))
            ep[key(pts[-1])].append((i, False))

        used = [False] * len(paths)
        result = []

        for seed in range(len(paths)):
            if used[seed] or len(paths[seed]['pts']) < 2:
                continue
            used[seed] = True
            chain = list(paths[seed]['pts'])
            color = paths[seed]['stroke']

            # Extend backward from chain head
            while True:
                sk = key(chain[0])
                grew = False
                for j, is_start in ep.get(sk, []):
                    if used[j]:
                        continue
                    next_pts = paths[j]['pts']
                    if is_start:
                        next_pts = list(reversed(next_pts))
                    chain[0:0] = next_pts[:-1]   # prepend, drop duplicate junction
                    used[j] = True
                    grew = True
                    break
                if not grew:
                    break

            # Extend forward from chain tail
            while True:
                ek = key(chain[-1])
                grew = False
                for j, is_start in ep.get(ek, []):
                    if used[j]:
                        continue
                    next_pts = paths[j]['pts']
                    if not is_start:
                        next_pts = list(reversed(next_pts))
                    chain.extend(next_pts[1:])    # append, drop duplicate junction
                    used[j] = True
                    grew = True
                    break
                if not grew:
                    break

            result.append({'pts': chain, 'fill': None, 'stroke': color})

        return result

    # $INSUNITS value → mm conversion factor (DXF spec Table 1)
    _INSUNITS_TO_MM = {
        0: 1.0,      # Unitless — asumir mm
        1: 25.4,     # Pulgadas
        2: 304.8,    # Pies
        3: 1609344.0,# Millas
        4: 1.0,      # Milímetros
        5: 10.0,     # Centímetros
        6: 1000.0,   # Metros
        7: 1e6,      # Kilómetros
        8: 2.54e-5,  # Micropulgadas
        9: 0.0254,   # Milésimas de pulgada (thou)
        10: 914.4,   # Yardas
        13: 0.001,   # Micrones
        14: 100.0,   # Decímetros
        15: 10000.0, # Decámetros
        16: 100000.0,# Hectómetros
        17: 1e9,     # Gigámetros
    }

    def parse(self, filepath):
        if not HAS_DXF:
            raise ImportError("ezdxf no instalado. Ejecuta: pip install ezdxf")
        doc = ezdxf.readfile(filepath)

        # Determinar factor de escala unidades DXF → mm
        insunits = doc.header.get('$INSUNITS', 4)
        scale = self._INSUNITS_TO_MM.get(insunits, 1.0)
        # tolerancia de muestreo = 0.01 mm REALES expresados en unidades del dibujo
        self._tol = 0.001 / max(scale, 1e-9)

        result = []
        for entity in doc.modelspace():
            self._collect(entity, result, self._color(entity))
        chained = self._chain_paths(result)

        # Aplicar conversión de unidades si el archivo no está en mm
        if scale != 1.0:
            for d in chained:
                d['pts'] = [(x * scale, y * scale) for x, y in d['pts']]

        return _simplify_styled(chained)


# ── AI Parser (pymupdf) ────────────────────────────────────────────────────────

class AIParser:
    """
    Lee archivos .AI (CS4+) usando pymupdf/fitz.
    pymupdf devuelve coordenadas en screen-space (Y↓ desde top-left del PDF).
    Se invierten a math-space (Y↑) usando page_h: y_mm = (page_h - y_pt) * sc.
    """
    PT_TO_MM = 0.352778  # 1 PDF point = 0.352778 mm

    @staticmethod
    def _to_rgb(c):
        """Normaliza color pymupdf (None / gray float / RGB tuple / CMYK tuple) a (r,g,b) o None."""
        if c is None:
            return None
        if isinstance(c, (int, float)):          # escala de grises
            v = float(c)
            return (v, v, v)
        if len(c) == 4:                          # CMYK
            k = c[3]
            return (max(0.0, 1-(c[0]+k)), max(0.0, 1-(c[1]+k)), max(0.0, 1-(c[2]+k)))
        return tuple(float(x) for x in c[:3])

    @staticmethod
    def _fp(pts):
        """Huella de path: todos los puntos redondeados a 0.5 mm."""
        return tuple(round(v * 2) / 2 for pt in pts for v in pt)

    def parse(self, filepath):
        if not HAS_MUPDF:
            raise ImportError("pymupdf no instalado. Ejecuta: pip install pymupdf")
        doc = fitz.open(filepath)
        all_paths = []
        seen = set()
        try:
            for page in doc:
                self._extract_page(page, all_paths, seen)
        except Exception as e:
            raise ValueError(f"Error al leer AI: {e}")
        finally:
            doc.close()
        return _simplify_styled(all_paths)

    def _extract_page(self, page, all_paths, seen):
        page_h = page.rect.height          # altura en puntos PDF para invertir Y
        sc     = self.PT_TO_MM

        for drawing in page.get_drawings():
            raw_stroke = drawing.get("color")
            raw_fill   = drawing.get("fill")

            if raw_stroke is None and raw_fill is None:
                continue

            stroke    = self._to_rgb(raw_stroke)
            fill      = self._to_rgb(raw_fill)
            close_drw = drawing.get("closePath", False)
            has_fill  = fill is not None

            subpaths = self._items_to_subpaths(
                drawing.get("items", []),
                close_drw or has_fill,
                page_h, sc,
            )

            for pts in subpaths:
                if len(pts) < 2:
                    continue
                fp = self._fp(pts)
                if fp not in seen:
                    seen.add(fp)
                    all_paths.append({
                        "pts":    pts,
                        "fill":   fill,
                        "stroke": stroke,
                    })

    def _items_to_subpaths(self, items, close_path, page_h, sc):
        """Items de pymupdf → subpaths en mm.

        Formato REAL de get_drawings(): cada item trae TODOS sus puntos —
        ('l', inicio, fin) y ('c', inicio, ctrl1, ctrl2, fin). NO existen items
        'm'/'h': cada segmento carga su propio inicio, y un subpath nuevo se
        detecta porque el inicio NO empalma con el punto anterior. El cierre
        viene en el flag 'closePath' del drawing. ⚠️ Asumir formato estilo SVG
        aquí (item 'm' + segmentos que continúan del punto previo) fue el bug
        que tragaba EN SILENCIO todo path que empezara con curva.
        """
        def pt(p):
            return (p.x * sc, (page_h - p.y) * sc)

        subpaths = []
        current  = []
        first_pt = None

        def flush():
            nonlocal current, first_pt
            if len(current) >= 2:
                if close_path and first_pt is not None:
                    lx, ly = current[-1]
                    fx, fy = first_pt
                    if abs(lx - fx) > 1e-9 or abs(ly - fy) > 1e-9:
                        current.append(first_pt)
                subpaths.append(list(current))
            current  = []
            first_pt = None

        def begin(p0):
            nonlocal current, first_pt
            if not current:
                current  = [p0]
                first_pt = p0
            elif abs(current[-1][0] - p0[0]) > 1e-6 or abs(current[-1][1] - p0[1]) > 1e-6:
                flush()
                current  = [p0]
                first_pt = p0

        for item in items:
            kind = item[0]

            if kind == "l":                          # ('l', inicio, fin)
                begin(pt(item[1]))
                current.append(pt(item[2]))

            elif kind == "c":                        # ('c', inicio, ctrl1, ctrl2, fin)
                p0 = pt(item[1])
                begin(p0)
                current.extend(_flat_cubic(p0, pt(item[2]), pt(item[3]), pt(item[4]), 0.001))

            elif kind == "re":                       # rectángulo inline
                flush()
                r     = item[1]
                x0    = r.x0 * sc
                x1    = r.x1 * sc
                # r.y0 = screen-top → math-top; r.y1 = screen-bottom → math-bottom
                y_top = (page_h - r.y0) * sc
                y_bot = (page_h - r.y1) * sc
                subpaths.append([
                    (x0, y_bot), (x1, y_bot), (x1, y_top), (x0, y_top), (x0, y_bot)
                ])

            elif kind == "qu":                       # cuadrilátero
                flush()
                q     = item[1]
                pts_q = [pt(q.ul), pt(q.ur), pt(q.lr), pt(q.ll)]
                pts_q.append(pts_q[0])
                subpaths.append(pts_q)

        flush()
        return subpaths


# ── Plotter Controller ─────────────────────────────────────────────────────────

class PlotterController:
    def __init__(self):
        self.ser = None
        self.connected = False

    def get_ports(self):
        if not HAS_SERIAL:
            return []
        return [p.device for p in serial.tools.list_ports.comports()]

    def connect(self, port, baudrate=9600):
        if not HAS_SERIAL:
            raise ImportError("pyserial no instalado. Ejecuta: pip install pyserial")
        self.ser = serial.Serial(
            port=port, baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=5, xonxoff=True
        )
        self.connected = True

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.connected = False
        self.ser = None

    def send(self, cmd):
        if not self.connected:
            raise ConnectionError("Plotter no conectado")
        if not cmd.endswith('\n'):
            cmd += '\n'
        self.ser.write(cmd.encode('ascii'))
        self.ser.flush()

    def send_hpgl(self, hpgl, progress_cb=None):
        import time
        lines = [l.strip() for l in hpgl.split('\n') if l.strip()]
        total = len(lines)
        for i, line in enumerate(lines):
            self.send(line)
            time.sleep(0.01)
            if progress_cb:
                progress_cb(i + 1, total)

    def move_relative(self, direction, dist_mm):
        u = int(dist_mm * HPGLConverter.UNITS_PER_MM)
        cmds = {
            'up':    f"PR0,{u};",
            'down':  f"PR0,-{u};",
            'left':  f"PR-{u},0;",
            'right': f"PR{u},0;",
        }
        self.send(cmds[direction])

    def abort(self):
        if self.ser and self.ser.is_open:
            self.ser.write(b'\x1b')
            self.ser.write(b'IN;\n')
            self.ser.flush()


def _pinch_corners(pts, threshold_deg=25.0):
    """Prepara puntos para smooth=True en tkinter: duplica esquinas agudas.

    En el B-spline de Tk, un punto duplicado crea un punto interpolante (la
    curva pasa exactamente por él). Así las esquinas con ángulo > threshold
    quedan nítidas mientras las transiciones suaves (arcos densos) siguen
    viéndose como curvas.
    """
    if len(pts) < 3:
        return [pts[0], pts[0], pts[-1], pts[-1]] if len(pts) == 2 else list(pts)
    cos_t = math.cos(math.radians(threshold_deg))
    result = [pts[0], pts[0]]   # duplicar inicio → curva arranca exactamente aquí
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        dx1, dy1 = p1[0] - p0[0], p1[1] - p0[1]
        dx2, dy2 = p2[0] - p1[0], p2[1] - p1[1]
        l1, l2 = math.hypot(dx1, dy1), math.hypot(dx2, dy2)
        if l1 > 1e-9 and l2 > 1e-9:
            c = max(-1.0, min(1.0, (dx1 * dx2 + dy1 * dy2) / (l1 * l2)))
            if c < cos_t:                # ángulo > threshold → esquina aguda
                result.append(p1)        # duplicado: el spline pasa exactamente aquí
        result.append(p1)
    result.extend([pts[-1], pts[-1]])   # duplicar fin
    return result


# ── Canvas base ────────────────────────────────────────────────────────────────

class _BaseCanvas:
    """Infraestructura compartida de zoom/pan/grilla."""
    MARGIN = 30

    def __init__(self, parent):
        self.canvas = tk.Canvas(parent, bg=UI.CANVAS, cursor='crosshair',
                                highlightthickness=1, highlightbackground=UI.LINE_2)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.zoom    = 1.0
        self.off_x   = self.MARGIN
        self.off_y   = self.MARGIN
        self._drag     = None
        self._mid_drag = None
        self._work_w = 0.0   # mm, 0 = no work area
        self._work_h = 0.0
        self.canvas.bind('<Configure>', lambda _e: self._auto_fit())
        self.canvas.bind('<MouseWheel>', self._on_wheel)
        self.canvas.bind('<ButtonPress-1>',   self._drag_start)
        self.canvas.bind('<B1-Motion>',       self._drag_move)
        self.canvas.bind('<ButtonPress-2>',   self._mid_drag_start)
        self.canvas.bind('<B2-Motion>',       self._mid_drag_move)
        self.canvas.bind('<ButtonRelease-2>', self._mid_drag_end)

    def _all_points(self):
        return []   # override en subclases

    def _auto_fit(self):
        pts = self._all_points()
        if not pts:
            if self._work_w > 0 and self._work_h > 0:
                pts = [(0, 0), (self._work_w, self._work_h)]
            else:
                self.redraw()
                return
        all_x = [p[0] for p in pts]
        all_y = [p[1] for p in pts]
        mn_x, mn_y = min(all_x), min(all_y)
        mx_x, mx_y = max(all_x), max(all_y)
        dw = mx_x - mn_x or 1
        dh = mx_y - mn_y or 1
        w = self.canvas.winfo_width()  or 500
        h = self.canvas.winfo_height() or 400
        self.zoom  = min((w - 2*self.MARGIN) / dw, (h - 2*self.MARGIN) / dh)
        self.off_x = self.MARGIN - mn_x * self.zoom
        self.off_y = self.MARGIN + (dh + mn_y) * self.zoom
        self.redraw()

    def _to_canvas(self, x, y):
        return x * self.zoom + self.off_x, self.off_y - y * self.zoom

    def _draw_grid(self, w, h):
        # Espaciado adaptativo: al menos 30px entre líneas de grilla
        for step in (1, 2, 5, 10, 20, 50, 100, 200):
            if self.zoom * step >= 30:
                spacing = step
                break
        else:
            spacing = 200
        for mm in range(-500, 2000, spacing):
            cx, _ = self._to_canvas(mm, 0)
            if 0 <= cx <= w:
                self.canvas.create_line(cx, 0, cx, h, fill=UI.GRID)
            _, cy = self._to_canvas(0, mm)
            if 0 <= cy <= h:
                self.canvas.create_line(0, cy, w, cy, fill=UI.GRID)
        ox, oy = self._to_canvas(0, 0)
        self.canvas.create_line(0, oy, w, oy, fill=UI.LINE_2, width=1)
        self.canvas.create_line(ox, 0, ox, h, fill=UI.LINE_2, width=1)

    def _draw_origin(self):
        ox, oy = self._to_canvas(0, 0)
        self.canvas.create_line(ox-8, oy, ox+8, oy, fill=UI.ORIGIN, width=2)
        self.canvas.create_line(ox, oy-8, ox, oy+8, fill=UI.ORIGIN, width=2)
        self.canvas.create_oval(ox-3, oy-3, ox+3, oy+3, fill=UI.ORIGIN, outline='')

    def redraw(self):
        pass  # override

    def _on_wheel(self, event):
        f = 1.15 if event.delta > 0 else 0.87
        self.off_x = event.x + (self.off_x - event.x) * f
        self.off_y = event.y + (self.off_y - event.y) * f
        self.zoom *= f
        self.redraw()

    def _drag_start(self, event):
        self._drag = (event.x, event.y, self.off_x, self.off_y)

    def _drag_move(self, event):
        if self._drag:
            self.off_x = self._drag[2] + event.x - self._drag[0]
            self.off_y = self._drag[3] + event.y - self._drag[1]
            self.redraw()

    def _mid_drag_start(self, event):
        self._mid_drag = (event.x, event.y, self.off_x, self.off_y)
        self.canvas.config(cursor='fleur')

    def _mid_drag_move(self, event):
        if self._mid_drag:
            self.off_x = self._mid_drag[2] + event.x - self._mid_drag[0]
            self.off_y = self._mid_drag[3] + event.y - self._mid_drag[1]
            self.redraw()

    def _mid_drag_end(self, _event):
        self._mid_drag = None
        self.canvas.config(cursor='crosshair')

    def set_work_area(self, w_mm, h_mm):
        self._work_w = w_mm
        self._work_h = h_mm
        if self._all_points():
            self.redraw()
        else:
            self._auto_fit()

    def _draw_work_area_bg(self):
        if self._work_w > 0 and self._work_h > 0:
            cx0, cy0 = self._to_canvas(0, 0)
            cx1, cy1 = self._to_canvas(self._work_w, self._work_h)
            x0, y0 = min(cx0, cx1), min(cy0, cy1)
            x1, y1 = max(cx0, cx1), max(cy0, cy1)
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=UI.WORK_BG, outline='')

    def _draw_work_area_border(self):
        if self._work_w > 0 and self._work_h > 0:
            cx0, cy0 = self._to_canvas(0, 0)
            cx1, cy1 = self._to_canvas(self._work_w, self._work_h)
            x0, y0 = min(cx0, cx1), min(cy0, cy1)
            x1, y1 = max(cx0, cx1), max(cy0, cy1)
            self.canvas.create_rectangle(x0, y0, x1, y1,
                                         fill='', outline=UI.WORK_LINE, width=2, dash=(8, 4))
            self.canvas.create_text((x0+x1)/2, y0-8,
                                    text=f"{self._work_w:.0f} x {self._work_h:.0f} mm",
                                    fill=UI.WORK_LINE, font=F_SUB)


# ── Design Canvas ── muestra el diseño con colores y rellenos ──────────────────

class DesignCanvas(_BaseCanvas):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas.config(bg=UI.CANVAS)
        self.styled      = []    # List[{"pts", "fill", "stroke"}]
        self._selected   = -1   # highlighted single path index, -1 = none
        self._select_cb  = None  # callback(idx) on single-path click
        self.pan_mode    = False  # True = left-drag pans; False = left-drag rubber-band
        self._sel_set    = set()  # indices of group-selected paths (drawn in blue)
        self._sel_set_cb = None   # callback(set_of_indices) after rubber-band release
        self._rect_start = None   # canvas pixel (x,y) where drag started
        self._rect_id    = None   # canvas item id for the rubber-band rect
        self.cut_paths   = []    # List[pts] overlay de vectores de corte
        self.show_cut    = False
        self._move_drag  = None  # (prev_x, prev_y) durante drag-move, None si no activo
        self._move_cb    = None  # callback(dx_mm, dy_mm) durante drag
        self._move_end_cb = None # callback() al soltar tras drag-move
        self.canvas.bind('<ButtonPress-1>',   self._sel_press,   add='+')
        self.canvas.bind('<ButtonRelease-1>', self._sel_release, add='+')

    # ── helpers ───────────────────────────────────────────────────────────────

    def _hit_selection(self, cx, cy, threshold=20):
        """True si (cx,cy) está a ≤threshold px de algún punto de la selección activa."""
        if self._selected >= 0 and self._selected < len(self.styled):
            indices = [self._selected]
        elif self._sel_set:
            indices = [i for i in self._sel_set if i < len(self.styled)]
        else:
            return False
        for i in indices:
            for pt in self.styled[i]['pts']:
                px, py = self._to_canvas(*pt)
                if math.hypot(cx - px, cy - py) <= threshold:
                    return True
        return False

    # ── drag: pan / move / rubber-band ────────────────────────────────────────

    def _drag_start(self, event):
        if self.pan_mode:
            self._drag      = (event.x, event.y, self.off_x, self.off_y)
            self._rect_start = None
            self._move_drag  = None
        elif self._hit_selection(event.x, event.y):
            self._move_drag  = (event.x, event.y)
            self._rect_start = None
            self._drag       = None
        else:
            self._rect_start = (event.x, event.y)
            self._drag       = None
            self._move_drag  = None

    def _drag_move(self, event):
        if self.pan_mode:
            if self._drag:
                self.off_x = self._drag[2] + event.x - self._drag[0]
                self.off_y = self._drag[3] + event.y - self._drag[1]
                self.redraw()
        elif self._move_drag is not None:
            dx_px = event.x - self._move_drag[0]
            dy_px = event.y - self._move_drag[1]
            self._move_drag = (event.x, event.y)
            dx_mm =  dx_px / self.zoom
            dy_mm = -dy_px / self.zoom   # Y canvas invertido respecto a mm
            if self._move_cb:
                self._move_cb(dx_mm, dy_mm)
        elif self._rect_start:
            if self._rect_id:
                self.canvas.delete(self._rect_id)
            x0, y0 = self._rect_start
            self._rect_id = self.canvas.create_rectangle(
                x0, y0, event.x, event.y,
                outline=UI.GROUP, width=1.5, dash=(5, 3))

    # ── click / rubber-band release ───────────────────────────────────────────

    def _sel_press(self, event):
        pass   # drag_start already records state

    def _sel_release(self, event):
        if self.pan_mode:
            self._drag = None
            return
        if self._move_drag is not None:
            self._move_drag = None
            if self._move_end_cb:
                self._move_end_cb()
            return
        if self._rect_id:
            self.canvas.delete(self._rect_id)
            self._rect_id = None
        if self._rect_start is None:
            return
        x0, y0 = self._rect_start
        self._rect_start = None
        dx = abs(event.x - x0)
        dy = abs(event.y - y0)
        if dx > 5 or dy > 5:
            rx0, rx1 = min(x0, event.x), max(x0, event.x)
            ry0, ry1 = min(y0, event.y), max(y0, event.y)
            selected = set()
            for i, d in enumerate(self.styled):
                for pt in d['pts']:
                    px, py = self._to_canvas(*pt)
                    if rx0 <= px <= rx1 and ry0 <= py <= ry1:
                        selected.add(i)
                        break
            if self._sel_set_cb:
                self._sel_set_cb(selected)
        else:
            self._do_select(event.x, event.y)

    def set_paths(self, styled, selected=-1):
        self.styled    = styled or []
        self._selected = selected
        self._auto_fit()

    def _all_points(self):
        return [pt for d in self.styled for pt in d["pts"]]

    def set_selected(self, idx):
        self._selected = idx
        self.redraw()

    def _do_select(self, cx, cy):
        best_idx  = -1
        best_dist = float('inf')
        for i, d in enumerate(self.styled):
            for pt in d['pts']:
                px, py = self._to_canvas(*pt)
                dist = math.hypot(cx - px, cy - py)
                if dist < best_dist:
                    best_dist = dist
                    best_idx  = i
        if best_dist <= 20:
            self._selected = best_idx
            if self._select_cb:
                self._select_cb(best_idx)
            self.redraw()
        elif self._selected != -1 or self._sel_set:
            self._selected = -1
            self._sel_set  = set()
            if self._select_cb:
                self._select_cb(-1)
            self.redraw()

    def redraw(self):
        self.canvas.delete('all')
        w = self.canvas.winfo_width()  or 500
        h = self.canvas.winfo_height() or 400
        self._draw_work_area_bg()
        self._draw_grid(w, h)
        self._draw_work_area_border()
        if not self.styled:
            self.canvas.create_text(w//2, h//2,
                text="Diseño original\n(abre un archivo para ver)",
                fill=UI.FAINT, font=F_BODY, justify=tk.CENTER)
            self._draw_origin()
            return

        zoom, off_x, off_y = self.zoom, self.off_x, self.off_y

        for i, d in enumerate(self.styled):
            pts, fill, stroke = d["pts"], d.get("fill"), d.get("stroke")
            if len(pts) < 2:
                continue
            is_sel   = (self._selected == i)
            is_group = (i in self._sel_set)

            if fill is not None:
                coords = []
                for pt in pts:
                    coords.append(pt[0] * zoom + off_x)
                    coords.append(off_y - pt[1] * zoom)
                if len(coords) >= 6:
                    if is_sel:
                        outline, ow = UI.SEL, 2.5
                    elif is_group:
                        outline, ow = UI.SEL, 2.0
                    else:
                        outline, ow = (_rgb_hex(stroke) if stroke else ''), 1
                    self.canvas.create_polygon(coords, fill=_rgb_hex(fill),
                                               outline=outline, width=ow)
            elif stroke is not None:
                coords = []
                for pt in pts:
                    coords.append(pt[0] * zoom + off_x)
                    coords.append(off_y - pt[1] * zoom)
                if len(coords) >= 4:
                    if is_sel:
                        clr, ow = UI.SEL, 2.5
                    elif is_group:
                        clr, ow = UI.SEL, 2.0
                    else:
                        clr, ow = _rgb_hex(stroke), 1.5
                    self.canvas.create_line(coords, fill=clr, width=ow,
                                            smooth=False, joinstyle=tk.MITER, capstyle=tk.BUTT)

        if self.show_cut:
            for path in self.cut_paths:
                if len(path) < 2:
                    continue
                coords = []
                for pt in path:
                    coords.append(pt[0] * zoom + off_x)
                    coords.append(off_y - pt[1] * zoom)
                if len(coords) >= 4:
                    self.canvas.create_line(coords, fill=UI.CUT, width=1.5,
                                            smooth=False, joinstyle=tk.MITER, capstyle=tk.BUTT)
        self._draw_origin()


# ── Main Application ───────────────────────────────────────────────────────────

class PlotterApp:
    def __init__(self):
        self.root = tk.Tk()
        self._setup_theme()
        self.root.configure(bg=UI.BG)
        self.root.title("Plotter Antike — Controlador de Plotter de Corte")
        self.root.geometry("1380x780")
        self.root.minsize(1100, 640)
        try:
            self.root.iconbitmap(str(_resource('icon.ico')))
        except Exception:
            pass

        # State
        self.plotter = PlotterController()
        self.current_styled = []
        self.current_hpgl   = ""
        self.current_file   = ""
        self._pen_down      = False
        self._send_thread   = None
        # Layout / position state
        self.path_offsets   = []   # [[dx, dy], …] one per path, in mm
        self.path_scales    = []   # [scale, …]    1.0 = original size
        self.path_rotations = []   # [degrees, …]  0.0 = no rotation
        self._sel_idx       = -1   # selected path index, -1 = all
        self._sel_set       = set() # indices selected by rubber-band (group)
        self._undo_stack    = []   # historial de estados para Ctrl+Z
        self._redo_stack    = []   # estados revertidos para Ctrl+Shift+Z
        self.log            = None
        self._log_buffer    = []   # mensajes previos a que se abra la ventana Log COM
        self._clipboard     = []   # trazados copiados con Ctrl+C
        self._port_scan_busy = False  # evita solapar hilos de escaneo

        # Tkinter variables
        self.var_port      = tk.StringVar()
        self.var_baud      = tk.StringVar(value="9600")
        self.var_speed        = tk.IntVar(value=100)
        self.var_pressure     = tk.IntVar(value=100)
        self.var_overcut      = tk.DoubleVar(value=1.0)
        self.var_corner_angle = tk.DoubleVar(value=0.0)
        self.var_step      = tk.DoubleVar(value=10.0)
        self.var_status        = tk.StringVar(value="Desconectado")
        self.var_design_status = tk.StringVar(value="Sin diseño")
        self.var_file          = tk.StringVar(value="Ningún archivo cargado")
        self.var_progress  = tk.DoubleVar(value=0)
        self.var_work_w    = tk.DoubleVar(value=300.0)
        self.var_work_h    = tk.DoubleVar(value=200.0)
        self.var_pos_x     = tk.DoubleVar(value=0.0)
        self.var_pos_y     = tk.DoubleVar(value=0.0)
        self.var_pos_step   = tk.DoubleVar(value=1.0)
        self.var_obj_sel    = tk.StringVar(value="Todos")
        self.var_scale      = tk.DoubleVar(value=100.0)
        self.var_rotate     = tk.DoubleVar(value=0.0)
        self.var_scale_step = tk.DoubleVar(value=10.0)
        self.var_rot_step   = tk.DoubleVar(value=45.0)
        self.var_size_w     = tk.DoubleVar(value=0.0)
        self.var_size_h     = tk.DoubleVar(value=0.0)

        self._load_config()
        self._build_ui()
        self._update_work_area()
        self._schedule_port_refresh()   # primer escaneo en hilo de fondo, no bloquea
        self.root.bind('<Control-o>', lambda _: self.open_file())
        self.root.bind('<Control-z>', lambda _: self._undo())
        self.root.bind('<Control-Z>', lambda _: self._redo())
        self.root.bind('<Control-c>', lambda _: self._copy_selected())
        self.root.bind('<Control-v>', lambda _: self._paste())
        self.root.bind('<Control-equal>', lambda _: self._zoom(1.25))
        self.root.bind('<Control-plus>', lambda _: self._zoom(1.25))
        self.root.bind('<Control-minus>', lambda _: self._zoom(0.8))
        # El diálogo de área de trabajo solo la PRIMERA vez (cuando aún no hay config guardada).
        # Después se recuerda; se puede cambiar cuando sea desde Archivo → Área de trabajo…
        if not self._has_config:
            self.root.after(120, self._ask_work_area_startup)
        if getattr(sys, 'frozen', False):
            self.root.after(5000, lambda: self._check_for_updates(silent=True))

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_theme(self):
        """Tema de diseño para todos los widgets ttk (pestañas, botones, listas,
        spinboxes, barra de progreso…). Se basa en 'clam' porque dibuja sus propios
        colores y no obedece al modo oscuro del sistema (necesario en macOS y coherente
        en Windows/Linux). Los colores salen de la paleta UNA sola vez."""
        s = ttk.Style()
        try:
            s.theme_use('clam')
        except tk.TclError:
            return
        # Base
        s.configure('.', background=UI.PANEL, foreground=UI.INK,
                    fieldbackground=UI.SURFACE, bordercolor=UI.LINE,
                    lightcolor=UI.LINE, darkcolor=UI.LINE,
                    font=F_BODY, focuscolor=UI.ACCENT)
        s.map('.', foreground=[('disabled', UI.FAINT)])
        s.configure('TFrame', background=UI.PANEL)
        s.configure('TLabel', background=UI.PANEL, foreground=UI.INK)
        # Botones neutros
        s.configure('TButton', background=UI.SURFACE, foreground=UI.INK,
                    bordercolor=UI.LINE_2, relief='flat', padding=(9, 5), font=F_BTN)
        s.map('TButton',
              background=[('pressed', UI.LINE), ('active', UI.SURFACE_2)],
              bordercolor=[('active', UI.LINE_2)])
        # Botón de acento (acciones primarias)
        s.configure('Accent.TButton', background=UI.ACCENT, foreground='#ffffff',
                    bordercolor=UI.ACCENT, font=F_SEND, padding=(10, 7))
        s.map('Accent.TButton',
              background=[('pressed', UI.ACCENT_DK), ('active', UI.ACCENT_DK)],
              foreground=[('disabled', UI.ACCENT_FT)])
        # Barra de iconos: botones planos con hover; los toggles marcan estado en acento.
        # (ttk en vez de tk.Button/Checkbutton: en macOS los clásicos ignoran el estilo.)
        s.configure('Icon.TButton', background=UI.PANEL, foreground=UI.INK,
                    borderwidth=0, relief='flat', padding=6, font=F_ICON, anchor='center')
        s.map('Icon.TButton', background=[('pressed', UI.LINE_2), ('active', UI.LINE)])
        s.configure('Icon.Toolbutton', background=UI.PANEL, foreground=UI.MUTED,
                    borderwidth=0, relief='flat', padding=6, font=F_ICON, anchor='center')
        s.map('Icon.Toolbutton',
              background=[('selected', UI.ACCENT_SOFT), ('active', UI.LINE)],
              foreground=[('selected', UI.ACCENT)])
        # Contenedores
        s.configure('TLabelframe', background=UI.PANEL, bordercolor=UI.LINE, relief='solid')
        s.configure('TLabelframe.Label', background=UI.PANEL, foreground=UI.FAINT, font=F_SECTION)
        # Pestañas
        s.configure('TNotebook', background=UI.PANEL, borderwidth=0, tabmargins=(2, 4, 2, 0))
        s.configure('TNotebook.Tab', background=UI.PANEL, foreground=UI.MUTED,
                    padding=(14, 7), font=F_BTN, borderwidth=0)
        s.map('TNotebook.Tab',
              background=[('selected', UI.SURFACE)],
              foreground=[('selected', UI.ACCENT)])
        # Campos
        s.configure('TCombobox', fieldbackground=UI.SURFACE, background=UI.SURFACE,
                    arrowcolor=UI.MUTED, bordercolor=UI.LINE_2, padding=3)
        s.map('TCombobox', fieldbackground=[('readonly', UI.SURFACE)],
              bordercolor=[('focus', UI.ACCENT)])
        s.configure('TSpinbox', fieldbackground=UI.SURFACE, background=UI.SURFACE,
                    arrowcolor=UI.MUTED, bordercolor=UI.LINE_2, padding=3)
        s.map('TSpinbox', bordercolor=[('focus', UI.ACCENT)])
        s.configure('TEntry', fieldbackground=UI.SURFACE, bordercolor=UI.LINE_2, padding=3)
        s.map('TEntry', bordercolor=[('focus', UI.ACCENT)])
        # Indicadores
        s.configure('TProgressbar', background=UI.ACCENT, troughcolor=UI.LINE, bordercolor=UI.LINE)
        s.configure('Horizontal.TScale', background=UI.PANEL, troughcolor=UI.LINE)
        s.configure('TSeparator', background=UI.LINE)
        s.configure('TScrollbar', background=UI.PANEL, troughcolor=UI.SURFACE_2,
                    arrowcolor=UI.MUTED, bordercolor=UI.LINE)
        # Barra de estado
        s.configure('Status.TFrame', background=UI.SURFACE_2)
        s.configure('Status.TLabel', background=UI.SURFACE_2, foreground=UI.MUTED)

    def _build_ui(self):
        self._build_menu()
        main = ttk.Frame(self.root, padding=5)
        main.pack(fill=tk.BOTH, expand=True)
        self._build_right(main)
        self._build_statusbar()

    def _build_menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Abrir archivo…", command=self.open_file, accelerator="Ctrl+O")
        f.add_separator()
        f.add_command(label="Guardar como HPGL…", command=self.save_hpgl)
        f.add_separator()
        f.add_command(label="Área de trabajo…", command=self._open_work_area_dialog)
        f.add_separator()
        f.add_command(label="Salir", command=self.root.quit)
        m.add_cascade(label="Archivo", menu=f)

        pl = tk.Menu(m, tearoff=0)
        pl.add_command(label="Panel de Plotter…", command=self._open_plotter_window)
        m.add_cascade(label="Plotter", menu=pl)

        p = tk.Menu(m, tearoff=0)
        p.add_command(label="Actualizar puertos", command=self._refresh_ports)
        p.add_separator()
        p.add_command(label="Log COM…", command=self._open_log_window)
        m.add_cascade(label="Puerto", menu=p)

        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Dependencias", command=self._show_deps)
        h.add_command(label="Acerca de…", command=self._show_about)
        h.add_separator()
        h.add_command(label="Buscar actualizaciones…", command=lambda: self._check_for_updates(silent=False))
        m.add_cascade(label="Ayuda", menu=h)
        self.root.config(menu=m)


    def _build_plotter_tab(self, parent):
        inner = ttk.Frame(parent, padding=12)
        inner.pack(anchor=tk.NW, fill=tk.X)

        # ── Connection ────────────────────────────────────────────────────────
        cf = ttk.LabelFrame(inner, text=" Conexión ", padding=8)
        cf.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(cf, text="Puerto COM:").pack(anchor=tk.W)
        row = ttk.Frame(cf)
        row.pack(fill=tk.X, pady=2)
        self.cb_port = ttk.Combobox(row, textvariable=self.var_port, width=14)
        self.cb_port.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="↺", width=3, command=self._refresh_ports).pack(side=tk.LEFT, padx=(3, 0))

        ttk.Label(cf, text="Baudrate:").pack(anchor=tk.W)
        ttk.Combobox(cf, textvariable=self.var_baud, width=14,
                     values=["1200","2400","4800","9600","19200","38400","115200"]
                     ).pack(fill=tk.X, pady=2)

        brow = ttk.Frame(cf)
        brow.pack(fill=tk.X, pady=(6, 0))
        self.btn_connect = ttk.Button(brow, text="Conectar", command=self._toggle_connection)
        self.btn_connect.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.led = tk.Canvas(brow, width=18, height=18, highlightthickness=0)
        self.led.pack(side=tk.LEFT, padx=(6, 0))
        self._set_led(False)

        # ── Manual control ────────────────────────────────────────────────────
        mf = ttk.LabelFrame(inner, text=" Control Manual ", padding=8)
        mf.pack(fill=tk.X)

        step_row = ttk.Frame(mf)
        step_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(step_row, text="Paso (mm):").pack(side=tk.LEFT)
        ttk.Combobox(step_row, textvariable=self.var_step, width=8,
                     values=["0.1","0.5","1","5","10","20","50","100"]
                     ).pack(side=tk.LEFT, padx=4)

        pad = ttk.Frame(mf)
        pad.pack()
        btn = {'width': 5}
        ttk.Button(pad, text="▲", **btn, command=lambda: self._move('up')
                   ).grid(row=0, column=1, padx=3, pady=3)
        ttk.Button(pad, text="◀", **btn, command=lambda: self._move('left')
                   ).grid(row=1, column=0, padx=3, pady=3)
        self.btn_pen = ttk.Button(pad, text="▼▲", **btn, command=self._toggle_pen)
        self.btn_pen.grid(row=1, column=1, padx=3, pady=3)
        ttk.Button(pad, text="▶", **btn, command=lambda: self._move('right')
                   ).grid(row=1, column=2, padx=3, pady=3)
        ttk.Button(pad, text="▼", **btn, command=lambda: self._move('down')
                   ).grid(row=2, column=1, padx=3, pady=3)

        or_row = ttk.Frame(mf)
        or_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(or_row, text="Fijar Origen", command=self._set_origin
                   ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(or_row, text="Ir a (0,0)", command=self._go_home
                   ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Cutting parameters ────────────────────────────────────────────────
        pf = ttk.LabelFrame(inner, text=" Parámetros de Corte ", padding=8)
        pf.pack(fill=tk.X, pady=(12, 0))

        sr = ttk.Frame(pf)
        sr.pack(fill=tk.X)
        ttk.Label(sr, text="Velocidad (mm/s):").pack(side=tk.LEFT)
        self.lbl_speed = ttk.Label(sr, text="100", width=5, anchor=tk.E)
        self.lbl_speed.pack(side=tk.RIGHT)
        ttk.Scale(pf, from_=10, to=800, variable=self.var_speed, orient=tk.HORIZONTAL,
                  command=lambda v: self.lbl_speed.config(text=str(int(float(v))))
                  ).pack(fill=tk.X)
        srow2 = ttk.Frame(pf)
        srow2.pack(fill=tk.X, pady=(2, 6))
        ttk.Label(srow2, text="Exacto:").pack(side=tk.LEFT)
        sb_speed = ttk.Spinbox(srow2, from_=10, to=800, textvariable=self.var_speed, width=7)
        sb_speed.pack(side=tk.LEFT, padx=4)
        sb_speed.bind('<Return>', lambda _: self.lbl_speed.config(text=str(self.var_speed.get())))

        ttk.Separator(pf).pack(fill=tk.X, pady=4)

        pr = ttk.Frame(pf)
        pr.pack(fill=tk.X)
        ttk.Label(pr, text="Presión (gramos):").pack(side=tk.LEFT)
        self.lbl_pressure = ttk.Label(pr, text="100", width=5, anchor=tk.E)
        self.lbl_pressure.pack(side=tk.RIGHT)
        ttk.Scale(pf, from_=10, to=500, variable=self.var_pressure, orient=tk.HORIZONTAL,
                  command=lambda v: self.lbl_pressure.config(text=str(int(float(v))))
                  ).pack(fill=tk.X)
        prow2 = ttk.Frame(pf)
        prow2.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(prow2, text="Exacto:").pack(side=tk.LEFT)
        sb_pressure = ttk.Spinbox(prow2, from_=10, to=500, textvariable=self.var_pressure, width=7)
        sb_pressure.pack(side=tk.LEFT, padx=4)
        sb_pressure.bind('<Return>', lambda _: self.lbl_pressure.config(text=str(self.var_pressure.get())))

        ttk.Separator(pf).pack(fill=tk.X, pady=4)

        oc_row = ttk.Frame(pf)
        oc_row.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(oc_row, text="Sobrecore (mm):").pack(side=tk.LEFT)
        ttk.Spinbox(oc_row, from_=0.0, to=10.0, increment=0.5,
                    textvariable=self.var_overcut, width=7,
                    format="%.1f").pack(side=tk.LEFT, padx=4)
        ttk.Label(oc_row, text="(0 = desactivado)", foreground=UI.FAINT).pack(side=tk.LEFT)

        ca_row = ttk.Frame(pf)
        ca_row.pack(fill=tk.X, pady=(4, 2))
        ttk.Label(ca_row, text="Forzar esquinas (°):").pack(side=tk.LEFT)
        ttk.Spinbox(ca_row, from_=0.0, to=175.0, increment=5.0,
                    textvariable=self.var_corner_angle, width=7,
                    format="%.0f").pack(side=tk.LEFT, padx=4)
        ttk.Label(ca_row, text="(0 = desactivado)", foreground=UI.FAINT).pack(side=tk.LEFT)

    def _build_right(self, parent):
        preview_tab = ttk.Frame(parent)
        preview_tab.pack(fill=tk.BOTH, expand=True)

        self._var_pan_mode    = tk.BooleanVar(value=False)
        self._var_cut_overlay = tk.BooleanVar(value=False)

        # ── Área principal: barra iconos + canvas + sidebar ───────────────────
        content = ttk.Frame(preview_tab)
        content.pack(fill=tk.BOTH, expand=True)

        # ── Barra de iconos izquierda ─────────────────────────────────────────
        def _tooltip(widget, text):
            tip = [None]
            def _show(e):
                tip[0] = tk.Toplevel(widget, bg=UI.INK)
                tip[0].wm_overrideredirect(True)
                x = widget.winfo_rootx() + widget.winfo_width() + 6
                y = widget.winfo_rooty() + widget.winfo_height() // 2 - 10
                tip[0].wm_geometry(f"+{x}+{y}")
                tk.Label(tip[0], text=text, bg=UI.INK, fg='#ffffff',
                         font=F_SUB, relief=tk.FLAT, bd=0,
                         padx=8, pady=4).pack()
            def _hide(e):
                if tip[0]:
                    tip[0].destroy()
                    tip[0] = None
            widget.bind('<Enter>', _show)
            widget.bind('<Leave>', _hide)

        def _ibtn(icon, tip, cmd, side=tk.TOP):
            b = ttk.Button(icon_bar, text=icon, command=cmd,
                           style='Icon.TButton', takefocus=False)
            b.pack(fill=tk.X, side=side, padx=3, pady=1)
            _tooltip(b, tip)
            return b

        def _itoggle(icon, tip, var, cmd):
            b = ttk.Checkbutton(icon_bar, text=icon, variable=var, command=cmd,
                                style='Icon.Toolbutton', takefocus=False)
            b.pack(fill=tk.X, padx=3, pady=1)
            _tooltip(b, tip)
            return b

        icon_bar = tk.Frame(content, bg=UI.PANEL, width=48)
        icon_bar.pack(side=tk.LEFT, fill=tk.Y)
        icon_bar.pack_propagate(False)

        _ibtn("⤢", "Ajustar vista", self._fit_view)
        _ibtn("⊕", "Zoom +", lambda: self._zoom(1.25))
        _ibtn("⊖", "Zoom −", lambda: self._zoom(0.8))
        tk.Frame(icon_bar, height=1, bg=UI.LINE_2).pack(fill=tk.X, pady=4)
        self._btn_pan = _itoggle("↔", "Mover", self._var_pan_mode, self._on_pan_mode_toggle)
        self._btn_cut = _itoggle("✂", "Vectores de corte", self._var_cut_overlay, self._toggle_cut_overlay)

        tk.Frame(icon_bar, height=1, bg=UI.LINE_2).pack(fill=tk.X, side=tk.BOTTOM, pady=4)
        _ibtn("□", "Test de corte 10×10 mm", self._cut_test, side=tk.BOTTOM)

        ttk.Separator(content, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y)

        # Canvas
        canvas_wrap = ttk.Frame(content)
        canvas_wrap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.design_canvas = DesignCanvas(canvas_wrap)
        self.design_canvas._sel_set_cb  = self._on_canvas_sel_rect
        self.design_canvas._move_cb     = self._on_canvas_drag_move
        self.design_canvas._move_end_cb = self._on_canvas_drag_end
        self._drag_undo_pushed = False
        self.design_canvas.canvas.config(takefocus=True)
        self.design_canvas.canvas.bind('<ButtonPress-1>',
                                       lambda e: self.design_canvas.canvas.focus_set(), add='+')
        self.design_canvas.canvas.bind('<Delete>', lambda e: self._delete_selected())
        self.design_canvas.canvas.bind('<Left>',  lambda e: self._arrow_nudge('x', -1))
        self.design_canvas.canvas.bind('<Right>', lambda e: self._arrow_nudge('x', +1))
        self.design_canvas.canvas.bind('<Up>',    lambda e: self._arrow_nudge('y', +1))
        self.design_canvas.canvas.bind('<Down>',  lambda e: self._arrow_nudge('y', -1))

        # ── Sidebar derecha ───────────────────────────────────────────────────
        sb_sep = ttk.Separator(content, orient=tk.VERTICAL)
        sb_sep.pack(side=tk.LEFT, fill=tk.Y)

        self._sidebar = tk.Frame(content, bg=UI.PANEL, width=216)
        self._sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self._sidebar.pack_propagate(False)

        # Acción primaria de entrada: abrir un diseño. Antes solo estaba en el menú/Ctrl+O.
        sb_top = tk.Frame(self._sidebar, bg=UI.PANEL)
        sb_top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(8, 2))
        self.btn_open = ttk.Button(sb_top, text="Abrir diseño…", command=self.open_file,
                                   cursor='hand2')
        self.btn_open.pack(fill=tk.X, ipady=2)

        # Botones de acción al fondo (se empaquetan antes que sb_nb para reservar espacio)
        sb_bot = tk.Frame(self._sidebar, bg=UI.PANEL)
        sb_bot.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(4, 6))

        # ttk (no tk.Button): en macOS los botones clásicos ignoran el color de fondo;
        # el estilo Accent.TButton del tema sí lo respeta en las tres plataformas.
        self.btn_send = ttk.Button(
            sb_bot, text="Enviar Diseño  ▶", command=self._send_design,
            style='Accent.TButton', cursor='hand2')
        self.btn_send.pack(fill=tk.X, ipady=3)

        sb_nb = ttk.Notebook(self._sidebar)
        sb_nb.pack(fill=tk.BOTH, expand=True)

        props_tab  = tk.Frame(sb_nb, bg=UI.PANEL)
        layers_tab = tk.Frame(sb_nb, bg=UI.PANEL)
        sb_nb.add(props_tab,  text=" Props ")
        sb_nb.add(layers_tab, text=" Capas ")

        def _sec(title):
            tk.Label(props_tab, text=title, bg=UI.PANEL,
                     fg=UI.FAINT, font=F_SUB).pack(anchor=tk.W, padx=10, pady=(10, 1))
            ttk.Separator(props_tab).pack(fill=tk.X, padx=6)
            f = tk.Frame(props_tab, bg=UI.PANEL)
            f.pack(fill=tk.X, padx=8, pady=(4, 2))
            return f

        def _lbl(parent, text):
            return tk.Label(parent, text=text, bg=UI.PANEL, fg=UI.INK, font=F_LABEL)

        def _sublbl(parent, text):
            return tk.Label(parent, text=text, bg=UI.PANEL, fg=UI.FAINT, font=F_SUB)

        # ── Objeto ──
        f = _sec("OBJETO")
        self.cb_obj = ttk.Combobox(f, textvariable=self.var_obj_sel, state='readonly', width=16)
        self.cb_obj['values'] = ["Todos"]
        self.cb_obj.pack(fill=tk.X, pady=(0, 2))
        self.cb_obj.bind('<<ComboboxSelected>>', self._on_obj_select)

        # ── Posición ──
        f = _sec("POSICIÓN")
        row = tk.Frame(f, bg=UI.PANEL)
        row.pack(fill=tk.X, pady=1)
        _lbl(row, "X").pack(side=tk.LEFT)
        sb_px = ttk.Spinbox(row, from_=-9999, to=9999, increment=0.5,
                             textvariable=self.var_pos_x, width=6,
                             command=self._apply_obj_position)
        sb_px.pack(side=tk.LEFT, padx=(4, 2))
        sb_px.bind('<Return>', self._apply_obj_position)
        ttk.Button(row, text="◂", width=3,
                   command=lambda: self._nudge_pos('x', -1)).pack(side=tk.LEFT)
        ttk.Button(row, text="▸", width=3,
                   command=lambda: self._nudge_pos('x', +1)).pack(side=tk.LEFT, padx=(1, 0))

        row = tk.Frame(f, bg=UI.PANEL)
        row.pack(fill=tk.X, pady=1)
        _lbl(row, "Y").pack(side=tk.LEFT)
        sb_py = ttk.Spinbox(row, from_=-9999, to=9999, increment=0.5,
                             textvariable=self.var_pos_y, width=6,
                             command=self._apply_obj_position)
        sb_py.pack(side=tk.LEFT, padx=(4, 2))
        sb_py.bind('<Return>', self._apply_obj_position)
        ttk.Button(row, text="▾", width=3,
                   command=lambda: self._nudge_pos('y', -1)).pack(side=tk.LEFT)
        ttk.Button(row, text="▴", width=3,
                   command=lambda: self._nudge_pos('y', +1)).pack(side=tk.LEFT, padx=(1, 0))

        row = tk.Frame(f, bg=UI.PANEL)
        row.pack(fill=tk.X, pady=(3, 1))
        _sublbl(row, "paso").pack(side=tk.LEFT)
        ttk.Combobox(row, textvariable=self.var_pos_step, width=4,
                     values=["0.1", "0.5", "1", "5", "10", "50"]).pack(side=tk.LEFT, padx=(4, 2))
        _sublbl(row, "mm").pack(side=tk.LEFT)

        row = tk.Frame(f, bg=UI.PANEL)
        row.pack(fill=tk.X, pady=(4, 2))
        ttk.Button(row, text="Centrar",
                   command=self._center_design).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(row, text="Resetear",
                   command=self._reset_positions).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Tamaño ──
        f = _sec("TAMAÑO")
        row = tk.Frame(f, bg=UI.PANEL)
        row.pack(fill=tk.X, pady=1)
        _lbl(row, "W").pack(side=tk.LEFT)
        w_sb = ttk.Spinbox(row, from_=0.01, to=99999, increment=1.0,
                            textvariable=self.var_size_w, width=6,
                            command=self._apply_size_w)
        w_sb.pack(side=tk.LEFT, padx=(4, 2))
        w_sb.bind('<Return>', self._apply_size_w)
        _sublbl(row, "mm").pack(side=tk.LEFT)

        row = tk.Frame(f, bg=UI.PANEL)
        row.pack(fill=tk.X, pady=1)
        _lbl(row, "H").pack(side=tk.LEFT)
        h_sb = ttk.Spinbox(row, from_=0.01, to=99999, increment=1.0,
                            textvariable=self.var_size_h, width=6,
                            command=self._apply_size_h)
        h_sb.pack(side=tk.LEFT, padx=(4, 2))
        h_sb.bind('<Return>', self._apply_size_h)
        _sublbl(row, "mm").pack(side=tk.LEFT)

        # ── Rotación ──
        f = _sec("ROTACIÓN")
        row = tk.Frame(f, bg=UI.PANEL)
        row.pack(fill=tk.X, pady=1)
        rot_sb = ttk.Spinbox(row, from_=0, to=359.9, increment=45,
                              textvariable=self.var_rotate, width=6,
                              command=self._apply_rotation)
        rot_sb.pack(side=tk.LEFT)
        rot_sb.bind('<Return>', self._apply_rotation)
        _sublbl(row, "°").pack(side=tk.LEFT, padx=(2, 6))
        ttk.Button(row, text="↺", width=3,
                   command=lambda: self._nudge_rotate(-1)).pack(side=tk.LEFT)
        ttk.Button(row, text="↻", width=3,
                   command=lambda: self._nudge_rotate(+1)).pack(side=tk.LEFT, padx=(2, 0))

        row = tk.Frame(f, bg=UI.PANEL)
        row.pack(fill=tk.X, pady=(3, 1))
        _sublbl(row, "paso").pack(side=tk.LEFT)
        ttk.Combobox(row, textvariable=self.var_rot_step, width=4,
                     values=["1", "5", "15", "30", "45", "90"]).pack(side=tk.LEFT, padx=(4, 2))
        _sublbl(row, "°").pack(side=tk.LEFT)

        # ── Espejo ──
        f = _sec("ESPEJO")
        row = tk.Frame(f, bg=UI.PANEL)
        row.pack(fill=tk.X, pady=(2, 2))
        ttk.Button(row, text="↔ Horizontal",
                   command=lambda: self._apply_mirror('h')).pack(side=tk.LEFT, fill=tk.X,
                                                                  expand=True, padx=(0, 2))
        ttk.Button(row, text="↕ Vertical",
                   command=lambda: self._apply_mirror('v')).pack(side=tk.LEFT, fill=tk.X,
                                                                  expand=True)

        # ── Capas panel ───────────────────────────────────────────────────────
        layers_outer = tk.Frame(layers_tab, bg=UI.PANEL)
        layers_outer.pack(fill=tk.BOTH, expand=True)

        layers_scroll = tk.Scrollbar(layers_outer, orient=tk.VERTICAL)
        layers_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._layers_canvas = tk.Canvas(layers_outer, bg=UI.PANEL,
                                        yscrollcommand=layers_scroll.set,
                                        highlightthickness=0)
        self._layers_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        layers_scroll.config(command=self._layers_canvas.yview)

        self._layers_inner = tk.Frame(self._layers_canvas, bg=UI.PANEL)
        _lwin = self._layers_canvas.create_window((0, 0), window=self._layers_inner, anchor='nw')

        self._layers_inner.bind('<Configure>',
            lambda e: self._layers_canvas.configure(
                scrollregion=self._layers_canvas.bbox('all')))
        self._layers_canvas.bind('<Configure>',
            lambda e: self._layers_canvas.itemconfig(_lwin, width=e.width))
        def _layers_scroll(e):
            self._layers_canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units')
        self._layers_scroll = _layers_scroll
        self._layers_canvas.bind('<MouseWheel>', _layers_scroll)
        self._layers_inner.bind('<MouseWheel>', _layers_scroll)

        self._plotter_win = None
        self._log_win = None

    def _build_statusbar(self):
        sb = ttk.Frame(self.root, style='Status.TFrame', padding=(8, 3))
        sb.pack(side=tk.BOTTOM, fill=tk.X)

        # Izquierda: estado del diseño + info paths
        ttk.Label(sb, textvariable=self.var_design_status,
                  foreground=UI.MUTED).pack(side=tk.LEFT, padx=(2, 0))
        self.lbl_info = ttk.Label(sb, text="", foreground=UI.FAINT)
        self.lbl_info.pack(side=tk.LEFT, padx=(10, 0))

        # Derecha: versión + barra de progreso + estado del plotter (clic → tab Plotter)
        ttk.Label(sb, text=f"v {VERSION}", style='Status.TLabel').pack(side=tk.RIGHT, padx=(0, 8))

        self.progressbar = ttk.Progressbar(sb, variable=self.var_progress,
                                           maximum=100, length=220, mode='determinate')
        self.progressbar.pack(side=tk.RIGHT, padx=4)

        plotter_btn = tk.Frame(sb, cursor='hand2')
        plotter_btn.pack(side=tk.RIGHT, padx=(0, 8))

        self.sb_led = tk.Canvas(plotter_btn, width=14, height=14, highlightthickness=0,
                                cursor='hand2')
        self.sb_led.pack(side=tk.LEFT, padx=(0, 4))
        self._set_sb_led(False)

        sb_status_lbl = ttk.Label(plotter_btn, textvariable=self.var_status,
                                  cursor='hand2')
        sb_status_lbl.pack(side=tk.LEFT)

        for w in (plotter_btn, self.sb_led, sb_status_lbl):
            w.bind('<Button-1>', lambda _e=None: self._open_plotter_window())

    def _open_plotter_window(self):
        if self._plotter_win and self._plotter_win.winfo_exists():
            self._plotter_win.lift()
            self._plotter_win.focus_force()
            return
        win = tk.Toplevel(self.root, bg=UI.PANEL)
        win.title("Plotter")
        win.resizable(False, False)
        win.transient(self.root)
        self._plotter_win = win
        self._build_plotter_tab(win)

    def _open_log_window(self):
        if self._log_win and self._log_win.winfo_exists():
            self._log_win.lift()
            self._log_win.focus_force()
            return
        win = tk.Toplevel(self.root, bg=UI.PANEL)
        win.title("Log COM")
        win.geometry("640x400")
        win.transient(self.root)
        self._log_win = win

        lb = ttk.Frame(win)
        lb.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(lb, text="Limpiar", command=self._clear_log).pack(side=tk.LEFT)

        self.log = scrolledtext.ScrolledText(win, font=F_MONO,
                                             bg='#1e1e1e', fg='#d4d4d4',
                                             insertbackground='white', state=tk.DISABLED)
        self.log.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        if self._log_buffer:
            self.log.config(state=tk.NORMAL)
            self.log.insert(tk.END, "".join(self._log_buffer))
            self.log.see(tk.END)
            self.log.config(state=tk.DISABLED)

    # ── Connection ─────────────────────────────────────────────────────────────

    def _make_layer_thumb(self, parent, pts, fill, stroke, bg, size=28):
        border = '#cc4400' if bg == UI.SEL else UI.LINE_2
        c = tk.Canvas(parent, width=size, height=size, bg=bg,
                      highlightthickness=1, highlightbackground=border,
                      cursor='hand2')
        if not pts or len(pts) < 2:
            return c
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        pw = (max(xs) - min(xs)) or 1.0
        ph = (max(ys) - min(ys)) or 1.0
        pad = 3
        avail = size - 2 * pad
        s = avail / max(pw, ph)
        ox = pad + (avail - pw * s) / 2 - min(xs) * s
        # Y-inverted: canvas y = oy - pt[1]*s
        oy = pad + (avail - ph * s) / 2 + max(ys) * s
        coords = []
        for pt in pts:
            coords.append(pt[0] * s + ox)
            coords.append(oy - pt[1] * s)
        if fill is not None and len(coords) >= 6:
            c.create_polygon(coords, fill=_rgb_hex(fill),
                             outline=_rgb_hex(stroke) if stroke else _rgb_hex(fill),
                             width=0.5)
        elif stroke is not None and len(coords) >= 4:
            c.create_line(coords, fill=_rgb_hex(stroke), width=1.0,
                          smooth=False, joinstyle='miter', capstyle='butt')
        return c

    def _refresh_layers(self):
        if not hasattr(self, '_layers_inner'):
            return
        for w in self._layers_inner.winfo_children():
            w.destroy()
        if not self.current_styled:
            tk.Label(self._layers_inner, text="Sin trazados", bg=UI.PANEL,
                     fg=UI.FAINT, font=F_LABEL).pack(padx=8, pady=14)
            self._layers_canvas.configure(scrollregion=self._layers_canvas.bbox('all'))
            return
        for i, d in enumerate(self.current_styled):
            is_sel   = (self._sel_idx == i)
            is_group = (i in self._sel_set)
            active   = is_sel or is_group
            bg = UI.SEL if active else (UI.PANEL if i % 2 == 0 else UI.SURFACE_2)
            fg = '#ffffff' if active else UI.INK

            item = tk.Frame(self._layers_inner, bg=bg, cursor='hand2')
            item.pack(fill=tk.X)

            thumb = self._make_layer_thumb(item, d['pts'], d.get('fill'), d.get('stroke'), bg)
            thumb.pack(side=tk.LEFT, padx=(4, 3), pady=3)

            lbl = tk.Label(item, text=f"Objeto {i+1}", bg=bg, fg=fg,
                           font=F_LABEL, cursor='hand2', anchor='w')
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

            def _click(_e, idx=i):
                new_idx = -1 if self._sel_idx == idx else idx
                self._on_canvas_select(new_idx)

            for w in (item, thumb, lbl):
                w.bind('<Button-1>', _click)
                w.bind('<MouseWheel>', self._layers_scroll)

        self._layers_inner.update_idletasks()
        self._layers_canvas.configure(scrollregion=self._layers_canvas.bbox('all'))

    def _refresh_ports(self):
        """Actualiza el combobox de puertos desde el hilo principal (llamar solo con root.after)."""
        ports = getattr(self, '_last_ports', [])
        if hasattr(self, 'cb_port'):
            self.cb_port['values'] = ports
        if ports and not self.var_port.get():
            self.var_port.set(ports[0])

    def _schedule_port_refresh(self):
        """Lanza un hilo de escaneo cada 3 s si no hay conexión activa."""
        if not self.plotter.connected and not self._port_scan_busy:
            self._port_scan_busy = True
            threading.Thread(target=self._bg_port_scan, daemon=True).start()
        self.root.after(3000, self._schedule_port_refresh)

    def _bg_port_scan(self):
        """Escanea puertos y autoconecta en un hilo de fondo (no bloquea la UI)."""
        try:
            ports = self.plotter.get_ports()
        except Exception:
            ports = []

        prev = getattr(self, '_last_ports', None)
        self._last_ports = ports

        # Actualizar UI en el hilo principal
        self.root.after(0, self._refresh_ports)
        if ports != prev:
            self.root.after(0, self._log,
                            f"Puertos detectados: {', '.join(ports) or 'ninguno'}")

        # Intentar autoconexión si procede
        port = self.var_port.get()
        if port and not self.plotter.connected and port in ports:
            try:
                baud = int(self.var_baud.get() or 9600)
                self.plotter.connect(port, baud)
                self.plotter.send("IN;")
                self.root.after(0, self._on_auto_connected, port, baud)
            except Exception as e:
                self.root.after(0, self._log,
                                f"Autoconexión fallida en {port}: {e}")

        self._port_scan_busy = False

    def _on_auto_connected(self, port, baud):
        """Actualiza la UI tras una autoconexión exitosa (se llama desde root.after)."""
        if hasattr(self, 'btn_connect'):
            self.btn_connect.config(text="Desconectar")
        self._set_led(True)
        self.var_status.set(f"Conectado — {port} @ {baud}")
        self._log(f"Autoconectado a {port} @ {baud} baudios")
        self._save_config()

    def _auto_connect(self):
        """Compatibilidad: redirige al mecanismo de hilo de fondo."""
        if not self._port_scan_busy and not self.plotter.connected:
            self._port_scan_busy = True
            threading.Thread(target=self._bg_port_scan, daemon=True).start()

    def _toggle_connection(self):
        if self.plotter.connected:
            self.plotter.disconnect()
            self.btn_connect.config(text="Conectar")
            self._set_led(False)
            self.var_status.set("Desconectado")
            self._log("Desconectado")
        else:
            port = self.var_port.get()
            baud = int(self.var_baud.get() or 9600)
            if not port:
                messagebox.showwarning("Sin puerto", "Selecciona un puerto COM")
                return
            try:
                self.plotter.connect(port, baud)
                self.btn_connect.config(text="Desconectar")
                self._set_led(True)
                self.var_status.set(f"Conectado — {port} @ {baud}")
                self._log(f"Conectado a {port} @ {baud} baudios")
                self.plotter.send("IN;")
                self._save_config()
            except Exception as e:
                messagebox.showerror("Error de conexión", str(e))
                self._log(f"ERROR conexión: {e}")

    def _set_led(self, on):
        if hasattr(self, 'led') and self.led.winfo_exists():
            self.led.delete('all')
            color = UI.GOOD if on else UI.BAD
            self.led.create_oval(2, 2, 16, 16, fill=color, outline='')
        self._set_sb_led(on)

    def _set_sb_led(self, on):
        if not hasattr(self, 'sb_led'):
            return
        self.sb_led.delete('all')
        color = UI.GOOD if on else UI.BAD
        self.sb_led.create_oval(1, 1, 13, 13, fill=color, outline='')

    # ── File ───────────────────────────────────────────────────────────────────

    def open_file(self):
        path = filedialog.askopenfilename(
            title="Abrir diseño vectorial",
            filetypes=[
                ("Vectorial", "*.svg *.ai *.dxf"),
                ("SVG",  "*.svg"),
                ("AI",   "*.ai"),
                ("DXF",  "*.dxf"),
                ("Todo", "*.*"),
            ]
        )
        if not path:
            return
        ext = Path(path).suffix.lower()
        self._log(f"Abriendo: {path}")
        try:
            self.root.config(cursor='wait')
            self.root.update()
            if ext == '.svg':
                paths = SVGParser().parse(path)
            elif ext == '.dxf':
                paths = DXFParser().parse(path)
            elif ext == '.ai':
                paths = AIParser().parse(path)
            else:
                messagebox.showwarning("Formato no soportado",
                                       f"Extensión '{ext}' no reconocida.\nUsa .svg, .ai o .dxf")
                return

            if not paths:
                messagebox.showinfo("Sin paths", "No se encontraron paths vectoriales en el archivo.")
                return

            self.current_styled = paths
            self.current_file   = path
            self._undo_stack    = []   # nuevo archivo → historial limpio
            self._redo_stack    = []
            # Reset position / transform state
            self.path_offsets   = [[0.0, 0.0] for _ in paths]
            self.path_scales    = [1.0        for _ in paths]
            self.path_rotations = [0.0        for _ in paths]
            self._sel_idx       = -1
            self._sel_set       = set()
            self.design_canvas._sel_set = set()
            # Normalize to positive quadrant: shift so min_x ≥ 0, min_y ≥ 0
            all_pts = [pt for d in paths for pt in d['pts']]
            if all_pts:
                min_x = min(p[0] for p in all_pts)
                min_y = min(p[1] for p in all_pts)
                sx = -min_x if min_x < 0 else 0.0
                sy = -min_y if min_y < 0 else 0.0
                if sx or sy:
                    for off in self.path_offsets:
                        off[0] += sx
                        off[1] += sy
            self.var_obj_sel.set("Todos")
            self.var_scale.set(100.0)
            self.var_rotate.set(0.0)
            self.cb_obj['values'] = ["Todos"] + [f"Objeto {i+1}" for i in range(len(paths))]
            # Apply work area and connect canvas select callback
            w, h = self.var_work_w.get(), self.var_work_h.get()
            self.design_canvas.set_work_area(w, h)
            self.design_canvas._select_cb = self._on_canvas_select
            self.var_file.set(Path(path).name)
            self._generate_hpgl()
            effective = self._effective_styled()
            self.design_canvas.cut_paths = [d['pts'] for d in effective]
            self.design_canvas.set_paths(effective, selected=-1)
            self._update_pos_display()
            total_pts = sum(len(d["pts"]) for d in paths)
            self._update_sel_info()
            self._log(f"Cargado: {len(paths)} paths, {total_pts} puntos")
            self.var_design_status.set(f"{Path(path).name}  ·  {len(paths)} paths | {total_pts} pts")
            self._refresh_layers()

        except ImportError as e:
            messagebox.showerror("Librería faltante", str(e))
            self._log(f"ERROR: {e}")
        except Exception as e:
            messagebox.showerror("Error al abrir archivo", str(e))
            self._log(f"ERROR: {e}")
        finally:
            self.root.config(cursor='')

    def _generate_hpgl(self):
        conv = HPGLConverter(speed=self.var_speed.get(), pressure=self.var_pressure.get(),
                             overcut_mm=self.var_overcut.get(),
                             corner_angle_deg=self.var_corner_angle.get())
        conv.initialize()
        for d in self._effective_styled():
            if len(d['pts']) >= 2:
                conv.add_path(d['pts'])
        conv.finalize()
        self.current_hpgl = conv.get_hpgl()

    def save_hpgl(self):
        if not self.current_hpgl:
            messagebox.showinfo("Sin HPGL", "Abre un archivo primero.")
            return
        out = filedialog.asksaveasfilename(
            defaultextension=".hpgl",
            filetypes=[("HPGL / PLT", "*.hpgl *.plt"), ("Todo", "*.*")]
        )
        if out:
            with open(out, 'w', encoding='ascii') as f:
                f.write(self.current_hpgl)
            self._log(f"HPGL guardado: {out}")
            messagebox.showinfo("Guardado", f"Archivo guardado:\n{out}")

    # ── Layout & position helpers ──────────────────────────────────────────────

    def _effective_styled(self):
        """Return current_styled with per-path offset, scale, and rotation applied."""
        if not self.current_styled:
            return self.current_styled
        result = []
        for i, d in enumerate(self.current_styled):
            dx, dy  = self.path_offsets[i]    if i < len(self.path_offsets)    else (0.0, 0.0)
            scale   = self.path_scales[i]      if i < len(self.path_scales)      else 1.0
            angle_d = self.path_rotations[i]  if i < len(self.path_rotations)  else 0.0

            pts = d['pts']
            if scale != 1.0 or angle_d != 0.0:
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                ocx = (min(xs) + max(xs)) / 2
                ocy = (min(ys) + max(ys)) / 2
                ca  = math.cos(math.radians(angle_d))
                sa  = math.sin(math.radians(angle_d))
                new_pts = []
                for x, y in pts:
                    rx = (x - ocx) * scale
                    ry = (y - ocy) * scale
                    new_pts.append((ocx + rx*ca - ry*sa + dx,
                                    ocy + rx*sa + ry*ca + dy))
                pts = new_pts
            elif dx != 0.0 or dy != 0.0:
                pts = [(x + dx, y + dy) for x, y in pts]

            if pts is d['pts']:
                result.append(d)
            else:
                result.append({'pts': pts, 'fill': d['fill'], 'stroke': d['stroke']})
        return result

    def _refresh_preview(self):
        """Redraw canvases and regenerate HPGL without resetting zoom."""
        styled = self._effective_styled()
        self.design_canvas.styled    = styled
        self.design_canvas._selected = self._sel_idx
        self.design_canvas.cut_paths = [d['pts'] for d in styled]
        self.design_canvas.redraw()
        self._generate_hpgl()
        self._update_size_display()
        self._update_scale_display()

    def _update_work_area(self, *_):
        try:
            w, h = self.var_work_w.get(), self.var_work_h.get()
        except tk.TclError:
            return
        self.design_canvas.set_work_area(w, h)

    def _on_obj_select(self, event=None):
        sel = self.var_obj_sel.get()
        if sel == "Selección":
            self._sel_idx = -1          # keep current _sel_set
        elif sel == "Todos":
            self._clear_sel_set()
            self._sel_idx = -1
        else:
            self._clear_sel_set()
            self._sel_idx = int(sel.split()[-1]) - 1
        self.design_canvas.set_selected(self._sel_idx)
        self._update_pos_display()
        self._update_size_display()
        self._update_scale_display()

    def _on_canvas_select(self, idx):
        self._clear_sel_set()
        self._sel_idx = idx
        self.var_obj_sel.set("Todos" if idx == -1 else f"Objeto {idx+1}")
        self.design_canvas.set_selected(idx)
        self._update_pos_display()
        self._update_size_display()
        self._update_scale_display()
        self._update_sel_info()
        self._refresh_layers()

    def _update_sel_info(self):
        """Actualiza lbl_info con los paths y puntos de la selección activa."""
        if self._sel_idx >= 0 and self._sel_idx < len(self.current_styled):
            pts = len(self.current_styled[self._sel_idx]['pts'])
            self.lbl_info.config(text=f"Sel: 1 path · {pts} pts")
        elif self._sel_set:
            valid = [i for i in self._sel_set if i < len(self.current_styled)]
            n_pts = sum(len(self.current_styled[i]['pts']) for i in valid)
            self.lbl_info.config(text=f"Sel: {len(valid)} paths · {n_pts} pts")
        else:
            self.lbl_info.config(text="")

    def _update_pos_display(self):
        eff = self._effective_styled()
        if not eff:
            return
        if self._sel_idx >= 0:
            if self._sel_idx < len(eff):
                pts = eff[self._sel_idx]['pts']
            else:
                return
        elif self._sel_set:
            pts = [pt for i, d in enumerate(eff) if i in self._sel_set for pt in d['pts']]
        else:
            pts = [pt for d in eff for pt in d['pts']]
        if pts:
            self.var_pos_x.set(round(min(p[0] for p in pts), 2))
            self.var_pos_y.set(round(min(p[1] for p in pts), 2))
        self._update_size_display()
        self._update_scale_display()

    def _apply_obj_position(self, *_):
        if not self.current_styled or not self.path_offsets:
            return
        self._push_undo()
        try:
            tx, ty = self.var_pos_x.get(), self.var_pos_y.get()
        except tk.TclError:
            return
        eff = self._effective_styled()
        if self._sel_idx >= 0:
            idx = self._sel_idx
            if idx >= len(self.path_offsets) or idx >= len(eff):
                return
            pts = eff[idx]['pts']
            if not pts:
                return
            self.path_offsets[idx][0] += tx - min(p[0] for p in pts)
            self.path_offsets[idx][1] += ty - min(p[1] for p in pts)
        elif self._sel_set:
            idxs = [i for i in self._sel_set if i < len(eff)]
            pts  = [pt for i in idxs for pt in eff[i]['pts']]
            if not pts:
                return
            dx = tx - min(p[0] for p in pts)
            dy = ty - min(p[1] for p in pts)
            for i in idxs:
                if i < len(self.path_offsets):
                    self.path_offsets[i][0] += dx
                    self.path_offsets[i][1] += dy
        else:
            pts = [pt for d in eff for pt in d['pts']]
            if not pts:
                return
            dx = tx - min(p[0] for p in pts)
            dy = ty - min(p[1] for p in pts)
            for off in self.path_offsets:
                off[0] += dx; off[1] += dy
        self._refresh_preview()

    def _nudge_pos(self, axis, direction):
        try:
            step = float(self.var_pos_step.get()) * direction
            if axis == 'x':
                self.var_pos_x.set(round(self.var_pos_x.get() + step, 3))
            else:
                self.var_pos_y.set(round(self.var_pos_y.get() + step, 3))
            self._apply_obj_position()
        except (tk.TclError, ValueError):
            pass

    def _arrow_nudge(self, axis, direction):
        if not self.current_styled:
            return
        if self._sel_idx < 0 and not self._sel_set:
            return
        self._nudge_pos(axis, direction)

    def _center_design(self):
        if not self.current_styled:
            return
        w, h = self.var_work_w.get(), self.var_work_h.get()
        eff = self._effective_styled()
        if self._sel_idx >= 0:
            pts = eff[self._sel_idx]['pts'] if self._sel_idx < len(eff) else []
        elif self._sel_set:
            pts = [pt for i, d in enumerate(eff) if i in self._sel_set for pt in d['pts']]
        else:
            pts = [pt for d in eff for pt in d['pts']]
        if not pts:
            return
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.var_pos_x.set(round((w - (max(xs) - min(xs))) / 2, 2))
        self.var_pos_y.set(round((h - (max(ys) - min(ys))) / 2, 2))
        self._apply_obj_position()

    def _reset_positions(self):
        self._push_undo()
        self.path_offsets   = [[0.0, 0.0] for _ in self.current_styled]
        self.path_scales    = [1.0        for _ in self.current_styled]
        self.path_rotations = [0.0        for _ in self.current_styled]
        # Re-apply positive-quadrant normalization (mirrors open_file logic)
        all_pts = [pt for d in self.current_styled for pt in d['pts']]
        if all_pts:
            min_x = min(p[0] for p in all_pts)
            min_y = min(p[1] for p in all_pts)
            sx = -min_x if min_x < 0 else 0.0
            sy = -min_y if min_y < 0 else 0.0
            if sx or sy:
                for off in self.path_offsets:
                    off[0] += sx
                    off[1] += sy
        self._sel_idx = -1
        self._clear_sel_set()
        self.var_scale.set(100.0)
        self.var_rotate.set(0.0)
        self.design_canvas._selected = -1
        self._refresh_preview()
        self._update_pos_display()

    def _update_size_display(self):
        eff = self._effective_styled()
        if not eff:
            self.var_size_w.set(0.0)
            self.var_size_h.set(0.0)
            return
        if self._sel_idx >= 0:
            if self._sel_idx < len(eff):
                pts = eff[self._sel_idx]['pts']
            else:
                return
        elif self._sel_set:
            pts = [pt for i, d in enumerate(eff) if i in self._sel_set for pt in d['pts']]
        else:
            pts = [pt for d in eff for pt in d['pts']]
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            self.var_size_w.set(round(max(xs) - min(xs), 2))
            self.var_size_h.set(round(max(ys) - min(ys), 2))

    def _update_scale_display(self):
        if not self.path_scales:
            self.var_scale.set(100.0)
            self.var_rotate.set(0.0)
            return
        if self._sel_idx >= 0 and self._sel_idx < len(self.path_scales):
            self.var_scale.set(round(self.path_scales[self._sel_idx] * 100, 1))
            self.var_rotate.set(round(self.path_rotations[self._sel_idx], 1))
        else:
            self.var_scale.set(100.0)
            self.var_rotate.set(0.0)

    def _apply_scale(self, *_):
        if not self.current_styled or not self.path_scales:
            return
        try:
            pct = float(self.var_scale.get())
        except (tk.TclError, ValueError):
            return
        self._push_undo()

        if self._sel_idx >= 0:
            # ── INDIVIDUAL mode: absolute %, anchor top-left ─────────────────
            idx = self._sel_idx
            if idx >= len(self.path_scales):
                return
            new_scale = max(0.0001, pct / 100.0)
            eff_before = self._effective_styled()
            anchor = None
            if idx < len(eff_before):
                pts = eff_before[idx]['pts']
                if pts:
                    anchor = (min(p[0] for p in pts), min(p[1] for p in pts))
            self.path_scales[idx] = new_scale
            if anchor is not None:
                eff_after = self._effective_styled()
                if idx < len(eff_after):
                    pts = eff_after[idx]['pts']
                    if pts:
                        self.path_offsets[idx][0] += anchor[0] - min(p[0] for p in pts)
                        self.path_offsets[idx][1] += anchor[1] - min(p[1] for p in pts)

        elif self._sel_set:
            # ── SELECTION GROUP mode: relative scale, anchor bottom-left ─────
            s = max(0.0001, pct / 100.0)
            eff = self._effective_styled()
            idxs = [i for i in self._sel_set if i < len(eff)]
            sel_pts = [pt for i in idxs for pt in eff[i]['pts']]
            if not sel_pts:
                return
            ax = min(p[0] for p in sel_pts)   # anchor bottom-left
            ay = min(p[1] for p in sel_pts)
            for i in idxs:
                d = self.current_styled[i]
                orig_xs = [p[0] for p in d['pts']]
                orig_ys = [p[1] for p in d['pts']]
                ocx = (min(orig_xs) + max(orig_xs)) / 2
                ocy = (min(orig_ys) + max(orig_ys)) / 2
                dx_old, dy_old = self.path_offsets[i]
                self.path_scales[i] = max(0.0001, self.path_scales[i] * s)
                self.path_offsets[i] = [
                    (ax - ocx) * (1 - s) + s * dx_old,
                    (ay - ocy) * (1 - s) + s * dy_old,
                ]
            self.var_scale.set(100.0)

        else:
            # ── ALL mode: relative scale, anchor bottom-left ──────────────────
            s = max(0.0001, pct / 100.0)
            eff = self._effective_styled()
            all_pts = [pt for d in eff for pt in d['pts']]
            if not all_pts:
                return
            ax = min(p[0] for p in all_pts)   # anchor bottom-left
            ay = min(p[1] for p in all_pts)
            for i, d in enumerate(self.current_styled):
                orig_xs = [p[0] for p in d['pts']]
                orig_ys = [p[1] for p in d['pts']]
                ocx = (min(orig_xs) + max(orig_xs)) / 2
                ocy = (min(orig_ys) + max(orig_ys)) / 2
                dx_old, dy_old = self.path_offsets[i]
                self.path_scales[i] = max(0.0001, self.path_scales[i] * s)
                self.path_offsets[i] = [
                    (ax - ocx) * (1 - s) + s * dx_old,
                    (ay - ocy) * (1 - s) + s * dy_old,
                ]
            self.var_scale.set(100.0)

        self._refresh_preview()
        self._update_pos_display()

    def _apply_rotation(self, *_):
        if not self.current_styled or not self.path_rotations:
            return
        try:
            val = float(self.var_rotate.get())
        except (tk.TclError, ValueError):
            return
        self._push_undo()

        if self._sel_idx >= 0:
            # ── INDIVIDUAL mode: absolute rotation ───────────────────────────
            idx = self._sel_idx
            if idx >= len(self.path_rotations):
                return
            self.path_rotations[idx] = val % 360
            self.var_rotate.set(round(val % 360, 1))

        elif self._sel_set:
            # ── SELECTION GROUP mode: rotate selection around its center ──────
            theta = math.radians(val)
            ca, sa = math.cos(theta), math.sin(theta)
            eff = self._effective_styled()
            idxs = [i for i in self._sel_set if i < len(eff)]
            sel_pts = [pt for i in idxs for pt in eff[i]['pts']]
            if not sel_pts:
                return
            gcx = (min(p[0] for p in sel_pts) + max(p[0] for p in sel_pts)) / 2
            gcy = (min(p[1] for p in sel_pts) + max(p[1] for p in sel_pts)) / 2
            for i in idxs:
                d = self.current_styled[i]
                orig_xs = [p[0] for p in d['pts']]; orig_ys = [p[1] for p in d['pts']]
                ocx = (min(orig_xs) + max(orig_xs)) / 2
                ocy = (min(orig_ys) + max(orig_ys)) / 2
                dx_old, dy_old = self.path_offsets[i]
                eff_cx = ocx + dx_old
                eff_cy = ocy + dy_old
                rx = eff_cx - gcx; ry = eff_cy - gcy
                self.path_offsets[i] = [
                    rx * ca - ry * sa + gcx - ocx,
                    rx * sa + ry * ca + gcy - ocy,
                ]
                self.path_rotations[i] = (self.path_rotations[i] + val) % 360
            self.var_rotate.set(0.0)

        else:
            # ── ALL mode: rotate everything around design center ──────────────
            theta = math.radians(val)
            ca, sa = math.cos(theta), math.sin(theta)
            eff = self._effective_styled()
            all_pts = [pt for d in eff for pt in d['pts']]
            if not all_pts:
                return
            gcx = (min(p[0] for p in all_pts) + max(p[0] for p in all_pts)) / 2
            gcy = (min(p[1] for p in all_pts) + max(p[1] for p in all_pts)) / 2
            for i, d in enumerate(self.current_styled):
                orig_xs = [p[0] for p in d['pts']]; orig_ys = [p[1] for p in d['pts']]
                ocx = (min(orig_xs) + max(orig_xs)) / 2
                ocy = (min(orig_ys) + max(orig_ys)) / 2
                dx_old, dy_old = self.path_offsets[i]
                eff_cx = ocx + dx_old; eff_cy = ocy + dy_old
                rx = eff_cx - gcx; ry = eff_cy - gcy
                self.path_offsets[i] = [
                    rx * ca - ry * sa + gcx - ocx,
                    rx * sa + ry * ca + gcy - ocy,
                ]
                self.path_rotations[i] = (self.path_rotations[i] + val) % 360
            self.var_rotate.set(0.0)

        self._refresh_preview()
        self._update_pos_display()

    def _nudge_scale(self, direction):
        try:
            step = float(self.var_scale_step.get()) * direction
            self.var_scale.set(round(max(1.0, self.var_scale.get() + step), 1))
            self._apply_scale()
        except (tk.TclError, ValueError):
            pass

    def _nudge_rotate(self, direction):
        try:
            step = float(self.var_rot_step.get()) * direction
            self.var_rotate.set(round((self.var_rotate.get() + step) % 360, 1))
            self._apply_rotation()
        except (tk.TclError, ValueError):
            pass

    def _apply_mirror(self, axis):
        """Flip selected path(s) around the group bounding-box center.

        Bakes effective transform + flip into the raw pts so scale/rotation/offset
        reset to identity — the visual position in the workspace is preserved.
        axis: 'h' = left↔right (negate X), 'v' = top↔bottom (negate Y).
        """
        if not self.current_styled:
            return
        self._push_undo()
        eff = self._effective_styled()

        if self._sel_idx >= 0:
            indices = [self._sel_idx]
        elif self._sel_set:
            indices = sorted(self._sel_set)
        else:
            indices = list(range(len(self.current_styled)))

        all_pts = [pt for i in indices for pt in eff[i]['pts']]
        if not all_pts:
            return

        if axis == 'h':
            center = (min(p[0] for p in all_pts) + max(p[0] for p in all_pts)) / 2
            for i in indices:
                self.current_styled[i]['pts'] = [(2*center - x, y) for x, y in eff[i]['pts']]
                self.current_styled[i]['_pinched'] = None
                self.path_offsets[i]   = [0.0, 0.0]
                self.path_scales[i]    = 1.0
                self.path_rotations[i] = 0.0
        else:
            center = (min(p[1] for p in all_pts) + max(p[1] for p in all_pts)) / 2
            for i in indices:
                self.current_styled[i]['pts'] = [(x, 2*center - y) for x, y in eff[i]['pts']]
                self.current_styled[i]['_pinched'] = None
                self.path_offsets[i]   = [0.0, 0.0]
                self.path_scales[i]    = 1.0
                self.path_rotations[i] = 0.0

        self._refresh_preview()
        self._update_pos_display()

    def _orig_size(self, idx):
        """Return (w_mm, h_mm) of path(s) at scale=1, no rotation/offset."""
        if idx >= 0:
            if idx < len(self.current_styled):
                pts = self.current_styled[idx]['pts']
            else:
                return (0.0, 0.0)
        elif self._sel_set:
            pts = [pt for i, d in enumerate(self.current_styled)
                   if i in self._sel_set for pt in d['pts']]
        else:
            pts = [pt for d in self.current_styled for pt in d['pts']]
        if len(pts) < 2:
            return (0.0, 0.0)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        return max(xs) - min(xs), max(ys) - min(ys)

    def _apply_size_w(self, *_):
        if not self.current_styled or not self.path_scales:
            return
        try:
            target_w = float(self.var_size_w.get())
        except (tk.TclError, ValueError):
            return
        if self._sel_idx >= 0:
            orig_w, _ = self._orig_size(self._sel_idx)
            if orig_w <= 0:
                return
            self.var_scale.set(round(target_w / orig_w * 100.0, 2))
        else:
            eff = self._effective_styled()
            if self._sel_set:
                xs = [p[0] for i, d in enumerate(eff) if i in self._sel_set for p in d['pts']]
            else:
                xs = [p[0] for d in eff for p in d['pts']]
            if not xs:
                return
            cur_w = max(xs) - min(xs)
            if cur_w <= 0:
                return
            self.var_scale.set(round(target_w / cur_w * 100.0, 2))
        self._apply_scale()

    def _apply_size_h(self, *_):
        if not self.current_styled or not self.path_scales:
            return
        try:
            target_h = float(self.var_size_h.get())
        except (tk.TclError, ValueError):
            return
        if self._sel_idx >= 0:
            _, orig_h = self._orig_size(self._sel_idx)
            if orig_h <= 0:
                return
            self.var_scale.set(round(target_h / orig_h * 100.0, 2))
        else:
            eff = self._effective_styled()
            if self._sel_set:
                ys = [p[1] for i, d in enumerate(eff) if i in self._sel_set for p in d['pts']]
            else:
                ys = [p[1] for d in eff for p in d['pts']]
            if not ys:
                return
            cur_h = max(ys) - min(ys)
            if cur_h <= 0:
                return
            self.var_scale.set(round(target_h / cur_h * 100.0, 2))
        self._apply_scale()

    # ── Manual control ─────────────────────────────────────────────────────────

    def _require_connection(self):
        if not self.plotter.connected:
            messagebox.showwarning("Sin conexión", "Conecta el plotter primero.")
            return False
        return True

    def _ensure_connection(self):
        """Verifica conexión; si no está conectado intenta reconectar con el puerto guardado."""
        if self.plotter.connected:
            return True
        port = self.var_port.get()
        baud_str = self.var_baud.get() or '9600'
        if not port:
            messagebox.showwarning("Sin puerto",
                "No hay puerto COM configurado.\n"
                "Ve a la pestaña Plotter y selecciona el puerto.")
            return False
        if not messagebox.askyesno("Reconectar al plotter",
                f"El plotter no está conectado.\n\n"
                f"¿Conectar a  {port}  @  {baud_str} baudios?"):
            return False
        try:
            baud = int(baud_str)
            self.plotter.connect(port, baud)
            if hasattr(self, 'btn_connect'):
                self.btn_connect.config(text="Desconectar")
            self._set_led(True)
            self.var_status.set(f"Conectado — {port} @ {baud}")
            self._log(f"Reconectado a {port} @ {baud} baudios")
            self.plotter.send("IN;")
            self._save_config()
            return True
        except Exception as e:
            messagebox.showerror("Error de conexión", str(e))
            self._log(f"ERROR reconexión: {e}")
            return False

    def _move(self, direction):
        if not self._require_connection():
            return
        try:
            dist = float(self.var_step.get())
            self.plotter.move_relative(direction, dist)
            self._log(f"Mover {direction} {dist} mm")
        except Exception as e:
            self._log(f"ERROR mover: {e}")

    def _toggle_pen(self):
        if not self._require_connection():
            return
        try:
            if self._pen_down:
                self.plotter.send("PU;")
                self.btn_pen.config(text="▼▲")
                self._log("Cuchilla: arriba (PU)")
                self._pen_down = False
            else:
                self.plotter.send("PD;")
                self.btn_pen.config(text="▲▼")
                self._log("Cuchilla: abajo (PD)")
                self._pen_down = True
        except Exception as e:
            self._log(f"ERROR cuchilla: {e}")

    def _set_origin(self):
        if not self._require_connection():
            return
        try:
            self.plotter.send("PS;")
            self._log("Origen fijado en posición actual")
        except Exception as e:
            self._log(f"ERROR fijar origen: {e}")

    def _go_home(self):
        if not self._require_connection():
            return
        try:
            self.plotter.send("PU0,0;")
            self._log("Moviendo a origen (0, 0)")
        except Exception as e:
            self._log(f"ERROR ir a origen: {e}")

    # ── Cut / Send ─────────────────────────────────────────────────────────────

    def _cut_test(self):
        if not self._require_connection():
            return
        if not messagebox.askyesno("Test de corte",
                "Se cortará un cuadrado de 10×10 mm en la posición actual.\n¿Continuar?"):
            return
        conv = HPGLConverter(speed=self.var_speed.get(), pressure=self.var_pressure.get())
        hpgl = conv.test_square(10)
        self._log("Test de corte 10×10 mm")
        self._run_send(hpgl)

    def _send_design(self):
        if not self._ensure_connection():
            return
        if not self.current_hpgl:
            messagebox.showwarning("Sin diseño", "Abre un archivo primero.")
            return
        if not messagebox.askyesno("Confirmar envío",
                f"Enviar diseño al plotter?\n\n"
                f"  Velocidad : {self.var_speed.get()} mm/s\n"
                f"  Presión   : {self.var_pressure.get()} g\n"
                f"  Archivo   : {Path(self.current_file).name}"):
            return
        self._generate_hpgl()
        self._log("Enviando diseño…")
        self._run_send(self.current_hpgl)

    def _run_send(self, hpgl):
        self.btn_send.config(state=tk.DISABLED)
        self.var_progress.set(0)

        def progress(cur, total):
            pct = cur / total * 100
            self.root.after(0, lambda: self.var_progress.set(pct))

        def worker():
            try:
                self.plotter.send_hpgl(hpgl, progress_cb=progress)
                self.root.after(0, lambda: self._log("Envío completado"))
                self.root.after(0, lambda: self.var_status.set("Envío completado"))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"ERROR envío: {e}"))
                self.root.after(0, lambda: messagebox.showerror("Error al enviar", str(e)))
            finally:
                self.root.after(0, lambda: self.btn_send.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.var_progress.set(0))

        self._send_thread = threading.Thread(target=worker, daemon=True)
        self._send_thread.start()

    def _cancel(self):
        if not self.plotter.connected:
            return
        try:
            self.plotter.abort()
            self._log("Trabajo cancelado (ESC + IN)")
        except Exception as e:
            self._log(f"ERROR cancelar: {e}")

    # ── Selection mode helpers ─────────────────────────────────────────────────

    def _on_canvas_sel_rect(self, indices):
        """Called by DesignCanvas after rubber-band release with set of indices."""
        self._sel_set = indices
        self.design_canvas._sel_set = indices
        vals = list(self.cb_obj['values'])
        if indices:
            if "Selección" not in vals:
                vals.insert(1, "Selección")
                self.cb_obj['values'] = vals
            self.var_obj_sel.set("Selección")
            self._sel_idx = -1
            self.design_canvas._selected = -1
        else:
            if "Selección" in vals:
                vals.remove("Selección")
                self.cb_obj['values'] = vals
            if self.var_obj_sel.get() == "Selección":
                self.var_obj_sel.set("Todos")
        self.design_canvas.redraw()
        self._update_pos_display()
        self._update_sel_info()
        self._refresh_layers()

    def _on_canvas_drag_move(self, dx_mm, dy_mm):
        """Llamado durante drag-move en el canvas: mueve la selección activa."""
        if not self._drag_undo_pushed:
            self._push_undo()
            self._drag_undo_pushed = True
        if self._sel_idx >= 0 and self._sel_idx < len(self.path_offsets):
            self.path_offsets[self._sel_idx][0] += dx_mm
            self.path_offsets[self._sel_idx][1] += dy_mm
        elif self._sel_set:
            for i in self._sel_set:
                if i < len(self.path_offsets):
                    self.path_offsets[i][0] += dx_mm
                    self.path_offsets[i][1] += dy_mm
        else:
            return
        # Solo redibuja visualmente; HPGL se regenera al soltar
        styled = self._effective_styled()
        self.design_canvas.styled    = styled
        self.design_canvas._selected = self._sel_idx
        self.design_canvas.cut_paths = [d['pts'] for d in styled]
        self.design_canvas.redraw()

    def _on_canvas_drag_end(self):
        """Llamado al soltar el mouse tras drag-move: finaliza y regenera HPGL."""
        self._drag_undo_pushed = False
        self._generate_hpgl()
        self._update_pos_display()

    def _clear_sel_set(self):
        """Clear the rubber-band selection and remove 'Selección' from combobox."""
        self._sel_set = set()
        self.design_canvas._sel_set = set()
        vals = list(self.cb_obj['values'])
        if "Selección" in vals:
            vals.remove("Selección")
            self.cb_obj['values'] = vals
        if self.var_obj_sel.get() == "Selección":
            self.var_obj_sel.set("Todos")

    def _copy_selected(self):
        if not self.current_styled:
            return
        if self._sel_idx >= 0 and self._sel_idx < len(self.current_styled):
            indices = [self._sel_idx]
        elif self._sel_set:
            indices = sorted(i for i in self._sel_set if i < len(self.current_styled))
        else:
            indices = list(range(len(self.current_styled)))
        self._clipboard = [
            ({'pts': list(self.current_styled[i]['pts']),
              'fill': self.current_styled[i].get('fill'),
              'stroke': self.current_styled[i].get('stroke'),
              '_pinched': None},
             list(self.path_offsets[i]),
             self.path_scales[i],
             self.path_rotations[i])
            for i in indices
        ]

    def _paste(self):
        if not self._clipboard or not self.current_styled:
            return
        self._push_undo()
        new_indices = []
        for d, offset, scale, rotation in self._clipboard:
            self.current_styled.append(dict(d))
            self.path_offsets.append([offset[0] + 5.0, offset[1] + 5.0])
            self.path_scales.append(scale)
            self.path_rotations.append(rotation)
            new_indices.append(len(self.current_styled) - 1)

        n = len(self.current_styled)
        self.cb_obj['values'] = ["Todos"] + [f"Objeto {i+1}" for i in range(n)]
        vals = list(self.cb_obj['values'])
        if "Selección" not in vals:
            vals.insert(1, "Selección")
            self.cb_obj['values'] = vals

        self._sel_idx = -1
        self._sel_set = set(new_indices)
        self.design_canvas._selected = -1
        self.design_canvas._sel_set  = set(new_indices)
        self.var_obj_sel.set("Selección")

        effective = self._effective_styled()
        self.design_canvas.cut_paths = [d['pts'] for d in effective]
        self.design_canvas.set_paths(effective, selected=-1)
        self._generate_hpgl()
        self._update_pos_display()
        total_pts = sum(len(d["pts"]) for d in self.current_styled)
        self._update_sel_info()
        self._refresh_layers()

    def _delete_selected(self):
        """Elimina el path individual seleccionado o todos los del grupo rubber-band."""
        if not self.current_styled:
            return
        self._push_undo()
        if self._sel_idx >= 0 and self._sel_idx < len(self.current_styled):
            to_delete = {self._sel_idx}
        elif self._sel_set:
            to_delete = {i for i in self._sel_set if i < len(self.current_styled)}
        else:
            return

        keep = [i for i in range(len(self.current_styled)) if i not in to_delete]
        self.current_styled  = [self.current_styled[i]  for i in keep]
        self.path_offsets    = [self.path_offsets[i]    for i in keep]
        self.path_scales     = [self.path_scales[i]     for i in keep]
        self.path_rotations  = [self.path_rotations[i]  for i in keep]

        # Limpiar selección
        self._sel_idx = -1
        self._sel_set = set()
        self.design_canvas._sel_set  = set()
        self.design_canvas._selected = -1

        # Actualizar combobox
        self.cb_obj['values'] = ["Todos"] + [f"Objeto {i+1}" for i in range(len(self.current_styled))]
        self.var_obj_sel.set("Todos")
        self.var_scale.set(100.0)
        self.var_rotate.set(0.0)

        # Refrescar vista
        self._generate_hpgl()
        if self.current_styled:
            effective = self._effective_styled()
            self.design_canvas.cut_paths = [d['pts'] for d in effective]
            self.design_canvas.set_paths(effective, selected=-1)
            self._update_pos_display()
            total_pts = sum(len(d["pts"]) for d in self.current_styled)
            self._update_sel_info()
        else:
            self.design_canvas.set_paths([], selected=-1)
            self._update_sel_info()
        self._refresh_layers()

    # ── Preview helpers ────────────────────────────────────────────────────────

    # ── Undo ───────────────────────────────────────────────────────────────────

    _UNDO_MAX = 50

    def _push_undo(self):
        self._redo_stack.clear()
        self._undo_stack.append({
            'styled':    [dict(d) for d in self.current_styled],
            'offsets':   [list(o) for o in self.path_offsets],
            'scales':    list(self.path_scales),
            'rotations': list(self.path_rotations),
        })
        if len(self._undo_stack) > self._UNDO_MAX:
            self._undo_stack.pop(0)

    def _undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append({
            'styled':    [dict(d) for d in self.current_styled],
            'offsets':   [list(o) for o in self.path_offsets],
            'scales':    list(self.path_scales),
            'rotations': list(self.path_rotations),
        })
        state = self._undo_stack.pop()
        self.current_styled  = state['styled']
        self.path_offsets    = state['offsets']
        self.path_scales     = state['scales']
        self.path_rotations  = state['rotations']
        self._sel_idx = -1
        self._sel_set = set()
        self.design_canvas._sel_set  = set()
        self.design_canvas._selected = -1
        self.cb_obj['values'] = ["Todos"] + [f"Objeto {i+1}" for i in range(len(self.current_styled))]
        self.var_obj_sel.set("Todos")
        self.var_scale.set(100.0)
        self.var_rotate.set(0.0)
        self._generate_hpgl()
        if self.current_styled:
            effective = self._effective_styled()
            self.design_canvas.cut_paths = [d['pts'] for d in effective]
            self.design_canvas.set_paths(effective, selected=-1)
            self._update_pos_display()
            total_pts = sum(len(d['pts']) for d in self.current_styled)
            self._update_sel_info()
        else:
            self.design_canvas.set_paths([], selected=-1)
            self._update_sel_info()
        self._log("Deshacer")

    def _redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append({
            'styled':    [dict(d) for d in self.current_styled],
            'offsets':   [list(o) for o in self.path_offsets],
            'scales':    list(self.path_scales),
            'rotations': list(self.path_rotations),
        })
        state = self._redo_stack.pop()
        self.current_styled  = state['styled']
        self.path_offsets    = state['offsets']
        self.path_scales     = state['scales']
        self.path_rotations  = state['rotations']
        self._sel_idx = -1
        self._sel_set = set()
        self.design_canvas._sel_set  = set()
        self.design_canvas._selected = -1
        self.cb_obj['values'] = ["Todos"] + [f"Objeto {i+1}" for i in range(len(self.current_styled))]
        self.var_obj_sel.set("Todos")
        self.var_scale.set(100.0)
        self.var_rotate.set(0.0)
        self._generate_hpgl()
        if self.current_styled:
            effective = self._effective_styled()
            self.design_canvas.cut_paths = [d['pts'] for d in effective]
            self.design_canvas.set_paths(effective, selected=-1)
            self._update_pos_display()
            total_pts = sum(len(d['pts']) for d in self.current_styled)
            self._update_sel_info()
        else:
            self.design_canvas.set_paths([], selected=-1)
            self._update_sel_info()
        self._log("Rehacer")

    def _fit_view(self):
        self.design_canvas._auto_fit()

    def _zoom(self, factor):
        self.design_canvas.zoom *= factor
        self.design_canvas.redraw()

    def _on_pan_mode_toggle(self):
        on = self._var_pan_mode.get()
        self.design_canvas.pan_mode = on
        self.design_canvas.canvas.config(cursor='hand2' if on else 'crosshair')

    def _toggle_cut_overlay(self):
        self.design_canvas.show_cut = self._var_cut_overlay.get()
        self.design_canvas.redraw()

    # ── HPGL viewer ────────────────────────────────────────────────────────────

    def _view_hpgl(self):
        if not self.current_hpgl:
            messagebox.showinfo("Sin HPGL", "Abre un archivo primero.")
            return
        win = tk.Toplevel(self.root, bg=UI.PANEL)
        win.title("HPGL generado")
        win.geometry("640x520")
        txt = scrolledtext.ScrolledText(win, font=F_MONO)
        txt.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        txt.insert(tk.END, self.current_hpgl)
        txt.config(state=tk.DISABLED)

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.current_hpgl)
            messagebox.showinfo("Copiado", "HPGL copiado al portapapeles.", parent=win)

        ttk.Button(win, text="Copiar al portapapeles", command=copy).pack(pady=6)

    # ── Log ────────────────────────────────────────────────────────────────────

    def _log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self._log_buffer.append(line)
        if self.log and self.log.winfo_exists():
            self.log.config(state=tk.NORMAL)
            self.log.insert(tk.END, line)
            self.log.see(tk.END)
            self.log.config(state=tk.DISABLED)

    def _clear_log(self):
        self._log_buffer.clear()
        if self.log and self.log.winfo_exists():
            self.log.config(state=tk.NORMAL)
            self.log.delete('1.0', tk.END)
            self.log.config(state=tk.DISABLED)

    # ── Help dialogs ───────────────────────────────────────────────────────────

    def _show_deps(self):
        lines = [
            "Estado de dependencias:\n",
            f"  pyserial       : {'✓ instalado' if HAS_SERIAL else '✗ falta  →  pip install pyserial'}",
            f"  svgpathtools   : {'✓ instalado' if HAS_SVG    else '✗ falta  →  pip install svgpathtools'}",
            f"  ezdxf          : {'✓ instalado' if HAS_DXF    else '✗ falta  →  pip install ezdxf'}",
            f"  pymupdf        : {'✓ instalado' if HAS_MUPDF  else '✗ falta  →  pip install pymupdf'}",
        ]
        messagebox.showinfo("Dependencias", "\n".join(lines))

    def _show_about(self):
        messagebox.showinfo("Acerca de",
            f"Plotter Antike — Controlador de Plotter de Corte\n"
            f"Versión {VERSION}\n\n"
            "Formatos de entrada : SVG, AI (PDF), DXF\n"
            "Protocolo de salida : HPGL\n"
            "Velocidad           : 10 – 800 mm/s\n"
            "Presión             : 10 – 500 g\n\n"
            "tkinter + pyserial + svgpathtools + ezdxf + pymupdf")

    # ── Auto-update ────────────────────────────────────────────────────────────

    def _check_for_updates(self, silent=True):
        threading.Thread(target=self._update_check_thread, args=(silent,), daemon=True).start()

    def _update_check_thread(self, silent):
        try:
            import urllib.request
            import json as _json
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={'User-Agent': 'PlotterAntike'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = _json.loads(resp.read())
            latest = data['tag_name'].lstrip('v')
            if _vkey(latest) and _vkey(VERSION) and _vkey(latest) > _vkey(VERSION):
                self.root.after(0, lambda: self._show_update_dialog(latest, data))
            elif not silent:
                self.root.after(0, lambda: messagebox.showinfo(
                    "Actualizaciones", f"Ya tienes la versión más reciente ({VERSION})."))
        except Exception:
            if not silent:
                self.root.after(0, lambda: messagebox.showwarning(
                    "Actualizaciones",
                    "No se pudo verificar actualizaciones.\nComprueba tu conexión a internet."))

    def _show_update_dialog(self, latest, release_data):
        msg = (f"Nueva versión disponible: {latest}\n"
               f"Versión actual: {VERSION}\n\n"
               "¿Deseas descargar e instalar la actualización?")
        if not messagebox.askyesno("Actualización disponible", msg):
            return
        # Solo paquetes de ESTA app: los releases del repo también traen los de
        # Design Studio, y bajarse uno ajeno terminaría en un instalador que no existe.
        assets = [a for a in release_data.get('assets', []) if 'PlotterAntike' in a.get('name', '')]
        if sys.platform == 'win32':
            url = next((a['browser_download_url'] for a in assets if 'Windows' in a['name']), None)
            if url:
                threading.Thread(target=self._download_and_install, args=(url,), daemon=True).start()
                return
        elif sys.platform == 'darwin':
            url = next((a['browser_download_url'] for a in assets if 'Mac' in a['name']), None)
            if url:
                threading.Thread(target=self._download_and_install_mac, args=(url,), daemon=True).start()
                return
        import webbrowser
        webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases/latest")

    def _download_and_install(self, url):
        try:
            import urllib.request
            import zipfile
            import tempfile
            import subprocess
            self.root.after(0, lambda: self.var_status.set("Descargando actualización…"))
            tmp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(tmp_dir, "update.zip")
            def _progress(count, block, total):
                if total > 0:
                    pct = min(int(count * block * 100 / total), 100)
                    self.root.after(0, lambda p=pct: self.var_status.set(f"Descargando… {p}%"))
            urllib.request.urlretrieve(url, zip_path, reporthook=_progress)
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(tmp_dir)
            bat_path = os.path.join(tmp_dir, "instalar.bat")
            if not os.path.exists(bat_path):
                raise FileNotFoundError("instalar.bat no encontrado en el paquete")
            self.root.after(0, lambda: self._launch_installer(bat_path))
        except Exception as e:
            err = str(e)
            self.root.after(0, lambda: self.var_status.set("Error en actualización"))
            self.root.after(0, lambda: messagebox.showerror(
                "Error de actualización", f"No se pudo instalar:\n{err}"))

    def _download_and_install_mac(self, url):
        try:
            import urllib.request
            import zipfile
            import tempfile
            import stat
            self.root.after(0, lambda: self.var_status.set("Descargando actualización…"))
            tmp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(tmp_dir, "update.zip")
            def _progress(count, block, total):
                if total > 0:
                    pct = min(int(count * block * 100 / total), 100)
                    self.root.after(0, lambda p=pct: self.var_status.set(f"Descargando… {p}%"))
            urllib.request.urlretrieve(url, zip_path, reporthook=_progress)
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(tmp_dir)
            new_bin = os.path.join(tmp_dir, "PlotterAntike")
            if not os.path.exists(new_bin):
                raise FileNotFoundError("PlotterAntike no encontrado en el paquete")
            os.chmod(new_bin, os.stat(new_bin).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            self.root.after(0, lambda: self._launch_installer_mac(new_bin))
        except Exception as e:
            err = str(e)
            self.root.after(0, lambda: self.var_status.set("Error en actualización"))
            self.root.after(0, lambda: messagebox.showerror(
                "Error de actualización", f"No se pudo instalar:\n{err}"))

    def _launch_installer(self, bat_path):
        messagebox.showinfo(
            "Actualización lista",
            "La actualización se instalará ahora.\n"
            "La aplicación se cerrará automáticamente.")
        import subprocess
        subprocess.Popen(
            ['cmd', '/c', bat_path],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)

    def _launch_installer_mac(self, new_bin):
        import stat
        import subprocess
        current = sys.executable
        messagebox.showinfo(
            "Actualización lista",
            "La actualización se instalará ahora.\n"
            "La aplicación se cerrará automáticamente.")
        script = f"""#!/bin/bash
sleep 1
cp "{new_bin}" "{current}"
chmod +x "{current}"
"{current}" &
"""
        script_path = os.path.join(os.path.dirname(new_bin), "update.sh")
        with open(script_path, 'w') as f:
            f.write(script)
        os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IEXEC)
        subprocess.Popen(['bash', script_path], start_new_session=True)
        self.root.quit()

    # ── Config persistence ─────────────────────────────────────────────────────

    _CONFIG_PATH = _config_path()

    def _load_config(self):
        # ¿Ya existe config? Si sí, no es la primera vez: no molestamos con el diálogo de inicio.
        self._has_config = self._CONFIG_PATH.exists()
        try:
            if self._CONFIG_PATH.exists():
                data = json.loads(self._CONFIG_PATH.read_text(encoding='utf-8'))
                self.var_work_w.set(float(data.get('work_w', 300.0)))
                self.var_work_h.set(float(data.get('work_h', 200.0)))
                self.var_overcut.set(float(data.get('overcut', 1.0)))
                self.var_corner_angle.set(float(data.get('corner_angle', 0.0)))
                if data.get('port'):
                    self.var_port.set(data['port'])
                if data.get('baud'):
                    self.var_baud.set(str(data['baud']))
        except Exception:
            pass

    def _save_config(self):
        try:
            self._CONFIG_PATH.write_text(json.dumps({
                'work_w':        self.var_work_w.get(),
                'work_h':        self.var_work_h.get(),
                'overcut':       self.var_overcut.get(),
                'corner_angle':  self.var_corner_angle.get(),
                'port':          self.var_port.get(),
                'baud':          self.var_baud.get(),
            }), encoding='utf-8')
        except Exception:
            pass

    def _ask_work_area_startup(self):
        self._open_work_area_dialog(startup=True)

    def _open_work_area_dialog(self, startup=False):
        dlg = tk.Toplevel(self.root, bg=UI.PANEL)
        dlg.title("Área de trabajo")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.transient(self.root)

        if startup:
            ttk.Label(dlg, text="¿Cuál es el área de trabajo del plotter?",
                      font=_font(12, 'bold')).pack(padx=20, pady=(18, 4))
            ttk.Label(dlg, text="Podés cambiarlo después en  Archivo → Área de trabajo…",
                      foreground=UI.MUTED).pack(padx=20, pady=(0, 10))

        frm = ttk.Frame(dlg, padding=(20, 8, 20, 4))
        frm.pack()
        var_w = tk.DoubleVar(value=self.var_work_w.get())
        var_h = tk.DoubleVar(value=self.var_work_h.get())
        ttk.Label(frm, text="Ancho (mm):", width=13, anchor=tk.W).grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(frm, from_=10, to=9999, increment=10, textvariable=var_w, width=10
                    ).grid(row=0, column=1, pady=5)
        ttk.Label(frm, text="Alto  (mm):", width=13, anchor=tk.W).grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(frm, from_=10, to=9999, increment=10, textvariable=var_h, width=10
                    ).grid(row=1, column=1, pady=5)

        def _apply():
            try:
                w, h = var_w.get(), var_h.get()
                if w < 10 or h < 10:
                    messagebox.showwarning("Valor inválido", "El área mínima es 10×10 mm.", parent=dlg)
                    return
            except tk.TclError:
                return
            self.var_work_w.set(w)
            self.var_work_h.set(h)
            self._save_config()
            self._update_work_area()
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", _apply)

        btn_row = ttk.Frame(dlg, padding=(20, 8, 20, 16))
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="Aceptar", command=_apply).pack(side=tk.RIGHT, padx=(6, 0))
        if not startup:
            ttk.Button(btn_row, text="Cancelar", command=dlg.destroy).pack(side=tk.RIGHT)

        dlg.update_idletasks()
        px = self.root.winfo_rootx() + (self.root.winfo_width()  - dlg.winfo_reqwidth())  // 2
        py = self.root.winfo_rooty() + (self.root.winfo_height() - dlg.winfo_reqheight()) // 2
        dlg.geometry(f"+{px}+{py}")

        self.root.wait_window(dlg)

    # ── Run ────────────────────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = PlotterApp()
    app.run()
