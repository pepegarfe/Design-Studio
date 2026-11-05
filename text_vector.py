# -*- coding: utf-8 -*-
"""Texto → trazos de corte, con las fuentes instaladas en el sistema.

Convierte una frase en polilíneas en mm (Y hacia ARRIBA, la convención de la UI)
usando fontTools para leer los contornos de los glifos. El tamaño pedido es la
ALTURA DE LAS MAYÚSCULAS en mm (como en Aspire: "texto de 20 mm" = una A de
20 mm), no el cuerpo tipográfico en puntos.

API:
    list_fonts()      -> {'ok', 'fonts': [{'name','path','index'}...]}  (con caché)
    text_paths(opts)  -> {'ok', 'paths': [{'pts': [[x,y],...]}...]}
        opts: text, path, index, size (mm), tracking (mm entre letras),
              line (factor de interlineado, 1.0 = natural), align ('left'|'center'|'right')

Igual que las demás dependencias, es OPCIONAL: sin fontTools la app arranca y
solo esta función se deshabilita (HAS_FONTS).
"""

import os
import sys
import logging

logging.getLogger('fontTools').setLevel(logging.ERROR)   # fuentes viejas gritan warnings inofensivos

try:
    from fontTools.ttLib import TTFont, TTCollection
    from fontTools.pens.basePen import BasePen
    from fontTools.pens.boundsPen import BoundsPen
    HAS_FONTS = True
except Exception:
    HAS_FONTS = False

import plotter_control as core   # reusa el Douglas-Peucker del motor (_simplify_mm)


# ---------------------------------------------------------------- fuentes del sistema

def _font_dirs():
    # Servidor en internet: su catálogo propio, no las fuentes de la máquina donde corre.
    catalogo = os.environ.get('DS_FUENTES')
    if catalogo:
        return [catalogo]
    home = os.path.expanduser('~')
    if sys.platform == 'darwin':
        return ['/System/Library/Fonts', '/System/Library/Fonts/Supplemental',
                '/Library/Fonts', os.path.join(home, 'Library/Fonts')]
    if os.name == 'nt':
        return [os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Microsoft\Windows\Fonts')]
    return ['/usr/share/fonts', '/usr/local/share/fonts', os.path.join(home, '.fonts'),
            os.path.join(home, '.local/share/fonts')]


def _font_name(font):
    """(nombre legible, familia, estilo) o None si no se puede leer.
    La familia y el estilo por separado permiten a la UI previsualizar con CSS
    (font-family + font-weight/style)."""
    try:
        name = font['name']
        fam = name.getDebugName(16) or name.getDebugName(1)
        sub = name.getDebugName(17) or name.getDebugName(2)
        if not fam:
            return None
        fam = fam.strip()
        sub = (sub or '').strip()
        if sub and sub.lower() not in ('regular', 'normal', ''):
            return (fam + ' ' + sub, fam, sub)
        return (fam, fam, '')
    except Exception:
        return None


def _usable(font):
    """Solo fuentes con alfabeto latino (fuera emoji, símbolos, ideogramas puros)."""
    try:
        cmap = font.getBestCmap()
        return ord('A') in cmap and ord('a') in cmap
    except Exception:
        return False


_FONT_CACHE = None
_CACHE_V = 2          # subirlo invalida cachés viejos en disco (p.ej. al agregar campos)


def _cache_file():
    """El caché de fuentes vive junto a la config de la instalación (no en /tmp). Es COMÚN a
    todas las cuentas: las fuentes son las mismas y escanearlas tarda ~5 s."""
    try:
        return str(core._config_compartida().with_name('fonts_cache.json'))
    except Exception:
        return os.path.join(os.path.expanduser('~'), '.builtbyjose_fonts_cache.json')


def _dirs_sig():
    """Firma barata de las carpetas de fuentes (mtime + nº de archivos del nivel
    raíz): si nadie instaló/quitó fuentes, el caché de disco sigue siendo válido."""
    sig = []
    for d in _font_dirs():
        try:
            sig.append([d, os.path.getmtime(d), len(os.listdir(d))])
        except Exception:
            sig.append([d, 0, 0])
    return sig


def list_fonts(refresh=False):
    global _FONT_CACHE
    if not HAS_FONTS:
        return {'ok': False, 'error': 'Falta la librería fontTools (pip install fonttools).'}
    if _FONT_CACHE is not None and not refresh:
        return {'ok': True, 'fonts': _FONT_CACHE}
    import json
    # 1) caché de DISCO: el escaneo completo tarda ~5 s; con caché el arranque es instantáneo
    if not refresh:
        try:
            data = json.load(open(_cache_file(), encoding='utf-8'))
            if data.get('v') == _CACHE_V and data.get('sig') == _dirs_sig() and data.get('fonts'):
                _FONT_CACHE = data['fonts']
                return {'ok': True, 'fonts': _FONT_CACHE}
        except Exception:
            pass
    # 2) escaneo real
    import time
    out = {}
    vistos = 0
    for d in _font_dirs():
        if not os.path.isdir(d):
            continue
        for base, _dirs, files in os.walk(d):
            for fn in sorted(files):
                if fn.startswith('.'):
                    continue
                # ⚠️ Soltar el intérprete cada 16 archivos. Python solo deja correr UN
                # hilo a la vez, y este escaneo es Python puro: sin esta pausa acapara
                # el intérprete y deja sin aire a la ventana (en Windows se ve como
                # "No responde"). Cuesta ~nada y hace que el escaneo sea buen vecino.
                vistos += 1
                if not vistos % 16:
                    time.sleep(0)
                ext = os.path.splitext(fn)[1].lower()
                path = os.path.join(base, fn)
                try:
                    if ext in ('.ttf', '.otf'):
                        f = TTFont(path, lazy=True)
                        nm = _font_name(f)
                        if nm and not nm[0].startswith('.') and _usable(f):
                            out.setdefault(nm[0], {'name': nm[0], 'family': nm[1], 'sub': nm[2],
                                                   'path': path, 'index': 0})
                        f.close()
                    elif ext == '.ttc':
                        coll = TTCollection(path, lazy=True)
                        for i, f in enumerate(coll.fonts):
                            nm = _font_name(f)
                            if nm and not nm[0].startswith('.') and _usable(f):
                                out.setdefault(nm[0], {'name': nm[0], 'family': nm[1], 'sub': nm[2],
                                                       'path': path, 'index': i})
                        coll.close()
                except Exception:
                    continue   # fuente corrupta o rara: se salta, no se truena
    _FONT_CACHE = sorted(out.values(), key=lambda e: e['name'].lower())
    try:
        json.dump({'v': _CACHE_V, 'sig': _dirs_sig(), 'fonts': _FONT_CACHE},
                  open(_cache_file(), 'w', encoding='utf-8'))
    except Exception:
        pass   # sin permisos de escritura: se queda el caché de memoria y ya
    return {'ok': True, 'fonts': _FONT_CACHE}


# ---------------------------------------------------------------- glifo → polilíneas

class _FlatPen(BasePen):
    """Aplana los contornos con De Casteljau adaptativo por tolerancia.

    BasePen ya resuelve lo peludo del protocolo: puntos on-curve implícitos de
    TrueType, contornos todo-off-curve, súper-Béziers de CFF y glifos compuestos
    (los descompone contra el glyphSet). Aquí solo caen segmentos simples.
    """

    def __init__(self, glyph_set, tol):
        super().__init__(glyph_set)
        self.tol = tol            # en unidades de la fuente
        self.contours = []
        self._cur = None

    # -- utilería
    @staticmethod
    def _dist_chord(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if L2 == 0:
            return ((p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2) ** 0.5
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
        t = max(0.0, min(1.0, t))
        qx, qy = a[0] + t * dx, a[1] + t * dy
        return ((p[0] - qx) ** 2 + (p[1] - qy) ** 2) ** 0.5

    def _flat_q(self, p0, c, p1, depth=0):
        if depth > 16 or self._dist_chord(c, p0, p1) <= self.tol:
            self._cur.append(p1)
            return
        c0 = ((p0[0] + c[0]) / 2, (p0[1] + c[1]) / 2)
        c1 = ((c[0] + p1[0]) / 2, (c[1] + p1[1]) / 2)
        m = ((c0[0] + c1[0]) / 2, (c0[1] + c1[1]) / 2)
        self._flat_q(p0, c0, m, depth + 1)
        self._flat_q(m, c1, p1, depth + 1)

    def _flat_c(self, p0, c1, c2, p1, depth=0):
        if depth > 16 or (self._dist_chord(c1, p0, p1) <= self.tol and
                          self._dist_chord(c2, p0, p1) <= self.tol):
            self._cur.append(p1)
            return
        ab = ((p0[0] + c1[0]) / 2, (p0[1] + c1[1]) / 2)
        bc = ((c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2)
        cd = ((c2[0] + p1[0]) / 2, (c2[1] + p1[1]) / 2)
        abc = ((ab[0] + bc[0]) / 2, (ab[1] + bc[1]) / 2)
        bcd = ((bc[0] + cd[0]) / 2, (bc[1] + cd[1]) / 2)
        m = ((abc[0] + bcd[0]) / 2, (abc[1] + bcd[1]) / 2)
        self._flat_c(p0, ab, abc, m, depth + 1)
        self._flat_c(m, bcd, cd, p1, depth + 1)

    # -- protocolo del pen
    def _moveTo(self, pt):
        self._cur = [pt]

    def _lineTo(self, pt):
        self._cur.append(pt)

    def _qCurveToOne(self, c, end):
        self._flat_q(self._getCurrentPoint(), c, end)

    def _curveToOne(self, c1, c2, end):
        self._flat_c(self._getCurrentPoint(), c1, c2, end)

    def _closePath(self):
        if self._cur and len(self._cur) >= 2:
            if self._cur[0] != self._cur[-1]:
                self._cur.append(self._cur[0])
            self.contours.append(self._cur)
        self._cur = None

    def _endPath(self):
        if self._cur and len(self._cur) >= 2:
            self.contours.append(self._cur)
        self._cur = None


def _cap_height(font, glyph_set, cmap, upem):
    """Altura de mayúsculas en unidades de fuente: medida sobre la H real; si la
    fuente no trae H, cae al sCapHeight de OS/2 y al final a 0.7×em."""
    for ch in ('H', 'M', 'A', 'X'):
        g = cmap.get(ord(ch))
        if not g:
            continue
        try:
            bp = BoundsPen(glyph_set)
            glyph_set[g].draw(bp)
            if bp.bounds and bp.bounds[3] > 0:
                return bp.bounds[3]
        except Exception:
            pass
    try:
        cap = getattr(font['OS/2'], 'sCapHeight', 0)
        if cap:
            return cap
    except Exception:
        pass
    return 0.7 * upem


def _kern_lookup(font):
    """Tabla 'kern' clásica (formato 0) si existe. GPOS queda fuera a propósito
    (v1): la mayoría de las fuentes de rótulo traen kern plano o ninguno."""
    try:
        for sub in font['kern'].kernTables:
            table = getattr(sub, 'kernTable', None)
            if table:
                return table
    except Exception:
        pass
    return {}


def text_paths(opts):
    if not HAS_FONTS:
        return {'ok': False, 'error': 'Falta la librería fontTools (pip install fonttools).'}
    o = opts or {}
    text = (o.get('text') or '').rstrip('\n')
    if not text.strip():
        return {'ok': False, 'error': 'Escribe algún texto.'}
    path = o.get('path') or ''
    if not os.path.isfile(path):
        return {'ok': False, 'error': 'No encuentro esa fuente en el sistema.'}
    size = float(o.get('size') or 30.0)          # mm de altura de mayúsculas
    if not (0.1 <= size <= 5000):
        return {'ok': False, 'error': 'Tamaño fuera de rango (0.1–5000 mm).'}
    tracking = float(o.get('tracking') or 0.0)   # mm extra entre letras
    line_f = float(o.get('line') or 1.0)         # factor de interlineado
    align = o.get('align') or 'left'
    arc_deg = max(-350.0, min(350.0, float(o.get('arc') or 0.0)))   # curvatura (+arco arriba / −valle)

    try:
        font = TTFont(path, fontNumber=int(o.get('index') or 0), lazy=True)
    except Exception as e:
        return {'ok': False, 'error': f'No se pudo abrir la fuente: {e}'}
    try:
        upem = font['head'].unitsPerEm or 1000
        glyph_set = font.getGlyphSet()
        cmap = font.getBestCmap()
        hmtx = font['hmtx']
        kern = _kern_lookup(font)
        cap = _cap_height(font, glyph_set, cmap, upem)
        scale = size / cap                        # unidades de fuente → mm
        # interlineado natural de la fuente (ascenso + descenso + hueco)
        try:
            hhea = font['hhea']
            line_adv = (hhea.ascent - hhea.descent + hhea.lineGap) * scale
        except Exception:
            line_adv = 1.2 * upem * scale
        line_adv *= line_f
        tol_units = max(0.003 / scale, 0.25)      # aplanado ~0.003 mm reales (piso anti-bucle)

        lines = text.split('\n')
        all_paths = []
        widths = []
        per_line = []                             # [(contornos_mm_de_la_línea, ancho_mm)]
        for li, ln in enumerate(lines):
            pen_x = 0.0                           # cursor en mm
            contours_mm = []
            prev_glyph = None
            for ch in ln:
                g = cmap.get(ord(ch))
                if g is None:
                    prev_glyph = None
                    if ch == '\t' and ord(' ') in cmap:
                        pen_x += 4 * hmtx[cmap[ord(' ')]][0] * scale
                    continue                      # carácter sin glifo: se salta
                if prev_glyph is not None:
                    pen_x += kern.get((prev_glyph, g), 0) * scale
                pen = _FlatPen(glyph_set, tol_units)
                try:
                    glyph_set[g].draw(pen)
                except Exception:
                    pen.contours = []
                gcx = pen_x + hmtx[g][0] * scale / 2.0    # centro del glifo (para el arco)
                for cont in pen.contours:
                    pts = [[px * scale + pen_x, py * scale] for (px, py) in cont]
                    contours_mm.append((pts, gcx))
                pen_x += hmtx[g][0] * scale + tracking
                prev_glyph = g
            if ln:
                pen_x -= tracking                 # el último tracking sobra
            per_line.append((contours_mm, max(0.0, pen_x)))
            widths.append(max(0.0, pen_x))

        maxw = max(widths) if widths else 0.0
        for li, (contours_mm, w) in enumerate(per_line):
            dx = 0.0
            if align == 'center':
                dx = (maxw - w) / 2
            elif align == 'right':
                dx = maxw - w
            dy = -li * line_adv                   # las líneas bajan (Y-arriba)
            # Arco: cada glifo se coloca RÍGIDO sobre el círculo (se rota, no se deforma),
            # con la baseline siguiendo el arco. +grados = arco (centro arriba), − = valle.
            arc_ok = arc_deg and w > 0.5
            if arc_ok:
                import math as _m
                th = _m.radians(abs(arc_deg))
                R = w / th
                sgn = 1.0 if arc_deg > 0 else -1.0
                cx0 = dx + w / 2.0
            for pts, gcx in contours_mm:
                if arc_ok:
                    phi = (gcx + dx - cx0) / R
                    rot = -sgn * phi
                    ca, sa = _m.cos(rot), _m.sin(rot)
                    X = cx0 + R * _m.sin(phi)
                    Y = sgn * (R * _m.cos(phi) - R)
                    moved = []
                    for (x, y) in pts:
                        lx, ly = (x + dx) - (gcx + dx), y
                        moved.append([X + lx * ca - ly * sa, Y + lx * sa + ly * ca + dy])
                else:
                    moved = [[x + dx, y + dy] for (x, y) in pts]
                moved = core._simplify_mm(moved, 0.003)
                if len(moved) >= 2:
                    all_paths.append({'pts': moved})

        if not all_paths:
            return {'ok': False, 'error': 'Ese texto no produjo trazos (¿solo espacios?).'}
        return {'ok': True, 'paths': all_paths}
    except Exception as e:
        return {'ok': False, 'error': f'No se pudo vectorizar el texto: {e}'}
    finally:
        try:
            font.close()
        except Exception:
            pass
