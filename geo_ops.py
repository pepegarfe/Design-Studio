# -*- coding: utf-8 -*-
"""Operaciones de geometría del DISEÑO: booleanas (unir/restar/intersectar) y
contorno-offset. Reciben figuras en mm (coordenadas EFECTIVAS de la UI) y
devuelven anillos nuevos en mm.

Convenciones (las mismas del CAM en cnc_gcode.py):
- Una "unidad" = lista de anillos cerrados que se combinan PAR-IMPAR
  (symmetric_difference): la "O" es letra + hueco, no dos discos.
- Entre unidades: unión. Restar = la PRIMERA unidad menos las demás (la de
  abajo en el orden de dibujo — la UI manda ese orden).

shapely es OPCIONAL (HAS_SHAPELY), igual que en el resto del proyecto.

API:
    boolean_op({'op': 'union'|'difference'|'intersection', 'units': [[[x,y]...]...]})
    offset_op({'dist': mm (+afuera/-adentro), 'units': ídem})
    ambos → {'ok': True, 'paths': [{'pts': [[x,y]...]}...]} | {'ok': False, 'error': ...}
"""

import math

try:
    from shapely.geometry import Polygon, LineString
    from shapely.ops import unary_union, polygonize
    HAS_SHAPELY = True
except Exception:
    HAS_SHAPELY = False

import plotter_control as core   # _simplify_mm: la misma limpieza que usan los parsers

_NEED = 'Falta la librería shapely (pip install shapely).'


def _poly_of_unit(rings):
    """Anillos de una unidad → polígono con anidado par-impar (o None)."""
    region = None
    for pts in rings or []:
        if not pts or len(pts) < 3:
            continue
        try:
            p = Polygon(pts)
            if not p.is_valid:
                p = p.buffer(0)
            if p.is_empty:
                continue
            region = p if region is None else region.symmetric_difference(p)
        except Exception:
            continue
    return region


def _units_polys(units):
    polys = [_poly_of_unit(u) for u in units or []]
    return [p for p in polys if p is not None and not p.is_empty]


def _rings_of(geom):
    """Geometría → lista de anillos {'pts': ...} (exteriores + huecos), simplificados."""
    out = []
    if geom is None or geom.is_empty:
        return out
    geoms = list(getattr(geom, 'geoms', [geom]))
    for g in geoms:
        if g.geom_type != 'Polygon':
            continue
        for ring in [g.exterior] + list(g.interiors):
            pts = [[float(x), float(y)] for x, y in ring.coords]
            pts = core._simplify_mm(pts, 0.003)
            if len(pts) >= 4:                 # triángulo cerrado como mínimo
                out.append({'pts': pts})
    return out


def boolean_op(data):
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    o = data or {}
    op = o.get('op')
    polys = _units_polys(o.get('units'))
    if len(polys) < 2:
        return {'ok': False, 'error': 'Se necesitan al menos dos figuras cerradas.'}
    try:
        if op == 'union':
            res = unary_union(polys)
        elif op == 'difference':
            res = polys[0]
            for p in polys[1:]:
                res = res.difference(p)
        elif op == 'intersection':
            res = polys[0]
            for p in polys[1:]:
                res = res.intersection(p)
        elif op == 'exclude':                # Exclusión: quita los traslapes, deja el resto
            res = polys[0]
            for p in polys[1:]:
                res = res.symmetric_difference(p)
        else:
            return {'ok': False, 'error': 'Operación desconocida.'}
    except Exception as e:
        return {'ok': False, 'error': f'La operación falló: {e}'}
    paths = _rings_of(res)
    if not paths:
        return {'ok': False, 'error': 'La operación dejó un resultado vacío '
                                      '(¿las figuras no se tocan?).'}
    return {'ok': True, 'paths': paths}


def offset_op(data):
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    o = data or {}
    try:
        dist = float(o.get('dist') or 0)
    except Exception:
        dist = 0.0
    if abs(dist) < 0.01:
        return {'ok': False, 'error': 'Da la distancia del contorno (± mm).'}
    polys = _units_polys(o.get('units'))
    if not polys:
        return {'ok': False, 'error': 'Se necesita al menos una figura cerrada.'}
    geom = unary_union(polys)
    # redondeos con sagita ~0.005 mm según la distancia (sin N fijo burdo)
    qs = int(math.pi / 2 / max(1e-6, math.sqrt(2 * 0.005 / abs(dist)))) + 1
    qs = max(16, min(96, qs))
    try:
        off = geom.buffer(dist, quad_segs=qs)
    except Exception as e:
        return {'ok': False, 'error': f'El contorno falló: {e}'}
    paths = _rings_of(off)
    if not paths:
        return {'ok': False, 'error': 'El contorno hacia adentro se comió toda la figura.'}
    return {'ok': True, 'paths': paths}


def _qs_for(radius):
    """Segmentos de redondeo por sagita ~0.005 mm."""
    qs = int(math.pi / 2 / max(1e-6, math.sqrt(2 * 0.005 / max(1e-6, abs(radius))))) + 1
    return max(16, min(96, qs))


def expand_op(data):
    """Engrosar línea: polilíneas ABIERTAS → figura cerrada con grosor total
    `width` (media a cada lado, puntas y uniones redondas)."""
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    o = data or {}
    try:
        width = float(o.get('width') or 0)
    except Exception:
        width = 0.0
    if width < 0.05:
        return {'ok': False, 'error': 'Da el grosor de la línea (mm).'}
    geoms = []
    for pts in o.get('paths') or []:
        if pts and len(pts) >= 2:
            try:
                geoms.append(LineString(pts).buffer(width / 2.0, quad_segs=_qs_for(width / 2.0)))
            except Exception:
                continue
    if not geoms:
        return {'ok': False, 'error': 'Se necesita al menos una línea abierta.'}
    paths = _rings_of(unary_union(geoms))
    if not paths:
        return {'ok': False, 'error': 'No salió ninguna figura.'}
    return {'ok': True, 'paths': paths}


def round_op(data):
    """Esquinas redondeadas con radio r: apertura+cierre morfológicos
    (erosión r → dilatación 2r → erosión r), que redondea esquinas convexas
    Y cóncavas. Cada unidad se procesa APARTE (no une figuras vecinas)."""
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    o = data or {}
    try:
        r = float(o.get('r') or 0)
    except Exception:
        r = 0.0
    if r < 0.05:
        return {'ok': False, 'error': 'Da el radio del redondeo (mm).'}
    qs = _qs_for(r)
    out = []
    comidas = 0
    for u in o.get('units') or []:
        poly = _poly_of_unit(u)
        if poly is None or poly.is_empty:
            continue
        try:
            rounded = poly.buffer(-r, quad_segs=qs).buffer(2 * r, quad_segs=qs).buffer(-r, quad_segs=qs)
        except Exception:
            continue
        rings = _rings_of(rounded)
        if rings:
            out.extend(rings)
        else:
            comidas += 1               # radio más grande que la figura: se devuelve INTACTA
            for pts in u:
                if pts and len(pts) >= 3:
                    out.append({'pts': [[float(x), float(y)] for (x, y) in pts]})
    if not out or comidas == len(o.get('units') or []):
        return {'ok': False, 'error': 'Ese radio se come las figuras enteras — usa uno más chico.'}
    res = {'ok': True, 'paths': out}
    if comidas:
        res['eaten'] = comidas
    return res


def divide_op(data):
    """Dividir (Pathfinder): parte las figuras por TODOS sus cruces; cada carita
    del arreglo queda como pieza independiente (lista de 'faces', cada una con
    sus anillos par-impar)."""
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    polys = _units_polys((data or {}).get('units'))
    if len(polys) < 2:
        return {'ok': False, 'error': 'Se necesitan al menos dos figuras cerradas.'}
    total = unary_union(polys)
    lines = unary_union([p.boundary for p in polys])
    faces = []
    try:
        for f in polygonize(lines):
            rp = f.representative_point()
            if total.covers(rp):                 # solo las caras que SON material
                rings = _rings_of(f)
                if rings:
                    faces.append([r['pts'] for r in rings])
    except Exception as e:
        return {'ok': False, 'error': f'No se pudo dividir: {e}'}
    if len(faces) < 2:
        return {'ok': False, 'error': 'Las figuras no se cruzan — no hay nada que dividir.'}
    return {'ok': True, 'faces': faces}


# ---------- vinil: recuadro y líneas de DESCARTE ----------

def weed_op(data):
    """Recuadro alrededor del diseño y, opcional, líneas que parten el sobrante en tiras para
    pelarlo más rápido. Las líneas NUNCA cruzan una figura: se recortan contra todas (las cerradas
    cuentan como macizas; las abiertas, como un trazo con margen), con 0.6 mm de respiro.

    data: {'paths': [pts...], 'margin': mm, 'step_h': mm (0 = sin), 'step_v': mm (0 = sin)}
    → {'ok', 'box': pts, 'lines': [pts...]}  (mm, mismas coordenadas que llegaron)."""
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    try:
        from shapely.geometry import box as _box
        paths = [[(float(x), float(y)) for x, y in pts] for pts in (data.get('paths') or []) if pts and len(pts) >= 2]
        if not paths:
            return {'ok': False, 'error': 'No hay figuras para el descarte.'}
        margin = max(0.0, float(data.get('margin', 5) or 0))
        step_h = max(0.0, float(data.get('step_h', 0) or 0))
        step_v = max(0.0, float(data.get('step_v', 0) or 0))
        xs = [x for pts in paths for x, _ in pts]
        ys = [y for pts in paths for _, y in pts]
        x0, y0, x1, y1 = min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin
        caja = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
        lineas = []
        if step_h > 0 or step_v > 0:
            solidos = []
            for pts in paths:
                cerrado = len(pts) >= 4 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= 0.05
                try:
                    if cerrado:
                        g = Polygon(pts)
                        g = g if g.is_valid else g.buffer(0)
                    else:
                        g = LineString(pts)
                    if not g.is_empty:
                        solidos.append(g.buffer(0.6, quad_segs=4))
                except Exception:
                    continue
            tapado = unary_union(solidos) if solidos else None
            libre = _box(x0, y0, x1, y1)

            def recorta(a, b):
                ln = LineString([a, b])
                g = ln.difference(tapado) if tapado is not None else ln
                for q in getattr(g, 'geoms', [g]):
                    if q.geom_type == 'LineString' and q.length >= 2.0:      # tiras de menos de 2 mm no ayudan
                        lineas.append([[round(x, 3), round(y, 3)] for x, y in q.coords])

            if step_h > 0 and (y1 - y0) > step_h * 1.5 and (y1 - y0) / step_h <= 400:
                y = y0 + step_h
                while y < y1 - step_h * 0.4:
                    recorta((x0, y), (x1, y))
                    y += step_h
            if step_v > 0 and (x1 - x0) > step_v * 1.5 and (x1 - x0) / step_v <= 400:
                x = x0 + step_v
                while x < x1 - step_v * 0.4:
                    recorta((x, y0), (x, y1))
                    x += step_v
        return {'ok': True, 'box': caja, 'lines': lineas}
    except Exception as e:
        return {'ok': False, 'error': f'Descarte: {e}'}


# ---------- CNC: ALIVIO EN ESQUINAS para ensambles (dogbone) ----------

def dogbone_op(data):
    """Una fresa redonda no puede dejar una esquina interior a escuadra: deja un radio y la pieza
    que debía entrar no entra. El alivio añade en cada esquina un mordisco circular del tamaño de
    la fresa para que la esquina de la otra pieza quepa.

    data: {'items': [pts...] (anillos CERRADOS, mm), 'dia': Ø fresa, 'mode': 'hueco' | 'pieza'}
      - 'hueco': la figura es un HUECO (se corta por dentro o se cajea) → se alivian sus esquinas
        salientes, AGRANDANDO el hueco.
      - 'pieza': la figura es una PIEZA (se corta por fuera) → se alivian sus esquinas entrantes,
        QUITÁNDOLE material.
    En los dos casos el centro del círculo va sobre la bisectriz de la esquina, a un radio de
    distancia, así que el círculo pasa justo por el vértice. El radio es el de la fresa + 0.1 mm:
    con el radio EXACTO el recorrido de la fresa se reduciría a un punto y desaparecería.
    Solo esquinas de verdad (entre 30° y 150°): las facetas de una curva no cuentan.
    → {'ok', 'results': [{'pts': ..., 'n': esquinas aliviadas} | None]}"""
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    try:
        from shapely.geometry import Point
        dia = float(data.get('dia') or 0)
        if not (0.2 <= dia <= 60):
            return {'ok': False, 'error': 'Diámetro de fresa fuera de rango (0.2–60 mm).'}
        r = dia / 2.0 + 0.1
        mode = 'pieza' if data.get('mode') == 'pieza' else 'hueco'
        out, total = [], 0
        for pts in data.get('items') or []:
            try:
                pts = [(float(x), float(y)) for x, y in pts]
                if len(pts) < 4 or math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 0.05:
                    out.append(None)
                    continue
                ring = core._simplify_mm([list(q) for q in pts[:-1]], 0.01)
                ring = [tuple(q) for q in ring]
                poly = Polygon(ring)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if poly.is_empty or poly.geom_type != 'Polygon':
                    out.append(None)
                    continue
                ring = list(poly.exterior.coords)[:-1]
                n = len(ring)
                area2 = sum(ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1] for i in range(n))
                ccw = area2 > 0
                circulos = []
                for i in range(n):
                    px, py = ring[i - 1]
                    cx, cy = ring[i]
                    nx, ny = ring[(i + 1) % n]
                    ax, ay, bx, by = px - cx, py - cy, nx - cx, ny - cy
                    la, lb = math.hypot(ax, ay), math.hypot(bx, by)
                    if la < 1e-6 or lb < 1e-6:
                        continue
                    ax, ay, bx, by = ax / la, ay / la, bx / lb, by / lb
                    ang = math.degrees(math.acos(max(-1.0, min(1.0, ax * bx + ay * by))))   # abertura de la esquina
                    if not (30.0 <= ang <= 150.0):
                        continue
                    if min(la, lb) < r * 0.6:                      # lados más cortos que la fresa: no es una esquina útil
                        continue
                    giro = (cx - px) * (ny - cy) - (cy - py) * (nx - cx)
                    saliente = (giro > 0) == ccw                   # esquina convexa del polígono
                    if (mode == 'hueco') != saliente:
                        continue
                    sx, sy = ax + bx, ay + by
                    ls = math.hypot(sx, sy)
                    if ls < 1e-6:
                        continue
                    circulos.append(Point(cx + sx / ls * r, cy + sy / ls * r).buffer(r, quad_segs=12))
                if not circulos:
                    out.append({'pts': [list(q) for q in pts], 'n': 0})
                    continue
                todos = unary_union(circulos)
                res = poly.union(todos) if mode == 'hueco' else poly.difference(todos)
                if res.geom_type == 'MultiPolygon':
                    res = max(res.geoms, key=lambda g: g.area)
                if res.is_empty or res.geom_type != 'Polygon':
                    out.append(None)
                    continue
                np_ = core._simplify_mm([[float(x), float(y)] for x, y in res.exterior.coords], 0.003)
                out.append({'pts': np_, 'n': len(circulos)})
                total += len(circulos)
            except Exception:
                out.append(None)
        return {'ok': True, 'results': out, 'total': total}
    except Exception as e:
        return {'ok': False, 'error': f'Alivio de esquinas: {e}'}


# ───────────────────────── Mosaico (24-nov-2026) ─────────────────────────
# Partir una pieza MÁS GRANDE que la placa en tramos que se ensamblan. Pedido de un probador:
# "es exactamente este trabajo; Aspire lo tiene y aquí no existe".
#
# Cómo se construye cada tramo (todo en mm, coordenadas EFECTIVAS de la UI):
#   1. La pieza se cuadricula: columnas y filas IGUALES, las mínimas para que cada tramo, con
#      las uniones que le sobresalen, quepa en la placa (`tile` menos `borde` por lado).
#   2. Cada costura lleva uniones ALTERNADAS (una sale a un lado, la siguiente al otro): así
#      ningún tramo queda con todo "macho" ni todo "hembra" y la costura no se abre.
#   3. Región de un tramo = su rectángulo + sus uniones − las del vecino que le entran.
#   4. Las esquinas de la región se REDONDEAN al radio de la fresa (+0.1): una fresa redonda no
#      puede cortar una esquina interior viva, y si una pieza la tiene viva y la otra redonda no
#      encajan. Con el mismo radio en las dos, el arco convexo de una es el cóncavo de la otra.
#   5. La región se encoge `holgura/2`: entre las dos piezas queda `holgura` para que entren.
#   6. Tramo = región ∩ diseño. Lo que queda fuera de la pieza (uniones al aire) desaparece solo.

def _union_cola(X, yc, d, n, w, signo):
    """Cola de milano en una costura VERTICAL x=X, centrada en yc, que sale `d` hacia `signo`
    (+1 derecha, −1 izquierda). Cuello `n` (en la costura) y cabeza `w` (al fondo, más ancha)."""
    return Polygon([(X, yc - n / 2), (X + signo * d, yc - w / 2), (X + signo * d, yc + w / 2), (X, yc + n / 2)])


def _union_puzzle(X, yc, d, n, w, signo):
    """Rompecabezas: cuello recto de ancho `n` y una bola de diámetro `w` al fondo."""
    from shapely.geometry import Point, box
    rb = w / 2.0
    cx = X + signo * (d - rb)
    cuello = box(min(X, cx), yc - n / 2, max(X, cx), yc + n / 2)
    return cuello.union(Point(cx, yc).buffer(rb, quad_segs=16))


def _uniones_costura(X, a, b, d, paso, forma):
    """Uniones a lo largo de una costura vertical x=X entre y=a e y=b. Devuelve [(polígono,
    signo)]. Se dejan libres los extremos (cruces con otras costuras o el borde)."""
    n, w = d * 0.75, d * 1.25
    libre = d * 1.2
    L = (b - a) - 2 * libre
    if L < w:
        return []
    k = max(1, int(L // paso) + 1)
    out = []
    for i in range(k):
        yc = a + libre + (L * (i + 0.5) / k)
        signo = 1 if i % 2 == 0 else -1
        f = _union_cola if forma == 'cola' else _union_puzzle
        out.append((f(X, yc, d, n, w, signo), signo))
    return out


def _girar(poly, vertical_a_horizontal):
    """Las costuras HORIZONTALES se construyen como verticales y se giran (x,y)→(y,x)."""
    from shapely.affinity import affine_transform
    return affine_transform(poly, [0, 1, 1, 0, 0, 0]) if vertical_a_horizontal else poly


def mosaic_op(data):
    """data: {'units': [[anillo...]...] (la pieza), 'tile': [ancho, alto] de la placa,
              'joint': 'cola' | 'puzzle' | 'recta', 'size': fondo de la unión (mm),
              'gap': holgura total (mm), 'dia': Ø de la fresa, 'margin': borde libre por lado}
    → {'ok', 'cols', 'rows', 'tiles': [{'row','col','paths':[{'pts'}...], 'bbox'}...],
       'seams': [[[x,y],[x,y]]...], 'warnings': [...]}"""
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    try:
        from shapely.geometry import box
        o = data or {}
        polys = _units_polys(o.get('units'))
        if not polys:
            return {'ok': False, 'error': 'Selecciona la pieza (figuras cerradas) que quieres partir.'}
        pieza = unary_union(polys)
        tw, th = [float(v) for v in (o.get('tile') or [0, 0])[:2]]
        forma = o.get('joint') if o.get('joint') in ('cola', 'puzzle', 'recta') else 'cola'
        d = float(o.get('size') or 30.0) if forma != 'recta' else 0.0
        gap = max(0.0, min(3.0, float(o.get('gap') if o.get('gap') is not None else 0.2)))
        dia = float(o.get('dia') or 6.0)
        margen = max(0.0, float(o.get('margin') if o.get('margin') is not None else 10.0))
        R = dia / 2.0 + 0.1
        avisos = []
        if forma != 'recta':
            if not (5.0 <= d <= 300.0):
                return {'ok': False, 'error': 'El fondo de la unión debe medir entre 5 y 300 mm.'}
            if d * 0.75 < dia * 1.6:
                return {'ok': False, 'error': ('Con una fresa de %g mm la unión debe tener al menos %g mm de fondo: '
                                               'si no, la fresa no entra en el cuello.') % (dia, math.ceil(dia * 1.6 / 0.75))}
        x0, y0, x1, y1 = pieza.bounds
        W, H = x1 - x0, y1 - y0
        # útil por tramo: la placa menos el borde y lo que sobresalen las uniones (d por cada lado
        # en el PEOR caso: un tramo de en medio recibe uniones salientes en las dos costuras)
        uw, uh = tw - 2 * margen - 2 * d, th - 2 * margen - 2 * d
        if uw < 20 or uh < 20:
            return {'ok': False, 'error': 'La placa es muy chica para esas uniones y ese borde.'}
        cols = max(1, math.ceil(W / uw - 1e-9))
        rows = max(1, math.ceil(H / uh - 1e-9))
        if cols * rows == 1:
            return {'ok': False, 'error': 'La pieza ya cabe en la placa: no hace falta partirla.'}
        if cols * rows > 60:
            return {'ok': False, 'error': 'Saldrían %d tramos: revisa el tamaño de la placa.' % (cols * rows)}
        xs = [x0 + W * i / cols for i in range(cols + 1)]
        ys = [y0 + H * j / rows for j in range(rows + 1)]
        G = max(W, H) + 1000.0                         # los tramos de la orilla se extienden de sobra
        paso = d * 3.2
        # uniones de cada costura: (polígono, quién lo POSEE como (col,row))
        propias = {}
        for i in range(1, cols):                        # costuras verticales x = xs[i]
            for j in range(rows):
                for p, s in _uniones_costura(xs[i], ys[j], ys[j + 1], d, paso, forma) if forma != 'recta' else []:
                    dueno = (i - 1, j) if s > 0 else (i, j)   # sale a la derecha = es del tramo izquierdo
                    propias.setdefault(dueno, []).append(p)
        for j in range(1, rows):                        # costuras horizontales y = ys[j] (construidas giradas)
            for i in range(cols):
                for p, s in _uniones_costura(ys[j], xs[i], xs[i + 1], d, paso, forma) if forma != 'recta' else []:
                    p = _girar(p, True)
                    dueno = (i, j - 1) if s > 0 else (i, j)   # sale hacia arriba = es del tramo de abajo
                    propias.setdefault(dueno, []).append(p)
        # Solo uniones ENTERAS dentro de la pieza (con su redondeo y holgura de respiro): una
        # unión a medias, mordida por un hueco o por la orilla, no agarra y queda frágil.
        dentro = pieza.buffer(-(R + gap + 1.0))
        sueltas = sum(len(ps) for ps in propias.values())
        propias = {k: [p for p in ps if dentro.contains(p)] for k, ps in propias.items()}
        quitadas = sueltas - sum(len(ps) for ps in propias.values())
        todas = [(k, p) for k, ps in propias.items() for p in ps]
        # 'avoid': cajas [x0,y0,x1,y1] de lo que NO se parte (notas, grabados): la etiqueta las esquiva
        cajas = [box(*[float(v) for v in c[:4]]).buffer(15) for c in (o.get('avoid') or [])[:500] if len(c) >= 4]
        estorbos = unary_union(cajas) if cajas else None
        tiles, perdidos = [], 0
        for j in range(rows):
            for i in range(cols):
                rx0 = xs[i] if i > 0 else x0 - G
                rx1 = xs[i + 1] if i < cols - 1 else x1 + G
                ry0 = ys[j] if j > 0 else y0 - G
                ry1 = ys[j + 1] if j < rows - 1 else y1 + G
                reg = box(rx0, ry0, rx1, ry1)
                mias = propias.get((i, j), [])
                if mias:
                    reg = unary_union([reg] + mias)
                ajenas = [p for k, p in todas if k != (i, j)]
                if ajenas:
                    reg = reg.difference(unary_union(ajenas))
                if forma != 'recta':
                    viva = reg
                    reg = reg.buffer(-R, join_style=1).buffer(R, join_style=1)   # redondea lo convexo
                    reg = reg.buffer(R, join_style=1).buffer(-R, join_style=1)   # y lo cóncavo
                    # ⚠️ En los CRUCES de costuras las cuatro esquinas son salientes (la fresa las corta
                    # vivas por fuera): redondearlas dejaba un agujero de ~8 mm² en cada cruce.
                    cruces = [box(xs[ci] - 2 * R, ys[cj] - 2 * R, xs[ci] + 2 * R, ys[cj] + 2 * R)
                              for ci in (i, i + 1) for cj in (j, j + 1) if 0 < ci < cols and 0 < cj < rows]
                    if cruces:
                        reg = reg.union(viva.intersection(unary_union(cruces)))
                if gap > 0:
                    reg = reg.buffer(-gap / 2.0, join_style=2)
                parte = pieza.intersection(reg)
                if parte.is_empty:
                    continue
                trozos = [g for g in getattr(parte, 'geoms', [parte]) if g.geom_type == 'Polygon' and g.area > 1.0]
                perdidos += len([g for g in getattr(parte, 'geoms', [parte]) if g.geom_type == 'Polygon' and g.area <= 1.0])
                if not trozos:
                    continue
                geo = unary_union(trozos)
                paths = _rings_of(geo)
                if paths:
                    bx = geo.bounds
                    # dónde va la etiqueta: el punto MÁS holgado del trozo mayor (no el centro del
                    # rectángulo, que puede caer en un hueco)
                    from shapely.ops import polylabel
                    mayor = max(trozos, key=lambda g: g.area)
                    if estorbos is not None:            # que no caiga sobre una nota o un grabado
                        libre = mayor.difference(estorbos)
                        libres = [g for g in getattr(libre, 'geoms', [libre]) if g.geom_type == 'Polygon']
                        if libres:
                            mayor = max(libres, key=lambda g: g.area)
                    try:
                        lp = polylabel(mayor, tolerance=1.0)
                        holgura_lp = mayor.exterior.distance(lp) if not mayor.interiors else min(
                            [mayor.exterior.distance(lp)] + [h.distance(lp) for h in mayor.interiors])
                    except Exception:
                        lp, holgura_lp = mayor.representative_point(), 20.0
                    tiles.append({'row': j, 'col': i, 'paths': paths,
                                  'bbox': [round(v, 3) for v in bx],
                                  'label_at': [round(lp.x, 2), round(lp.y, 2)], 'label_room': round(holgura_lp, 2)})
                    if (bx[2] - bx[0]) > tw - 2 * margen + 0.01 or (bx[3] - bx[1]) > th - 2 * margen + 0.01:
                        avisos.append('El tramo %d-%d mide %.0f × %.0f mm: no cabe en la placa con su borde.'
                                      % (j + 1, i + 1, bx[2] - bx[0], bx[3] - bx[1]))
        if quitadas and forma != 'recta':
            avisos.append('%d unión(es) no se pusieron porque caían en un hueco o en la orilla de la pieza.' % quitadas)
        if perdidos:
            avisos.append('%d pedacito(s) de menos de 1 mm² se descartaron (uniones que caían en una orilla).' % perdidos)
        seams = [[[xs[i], y0], [xs[i], y1]] for i in range(1, cols)] + [[[x0, ys[j]], [x1, ys[j]]] for j in range(1, rows)]
        return {'ok': True, 'cols': cols, 'rows': rows, 'tiles': tiles, 'seams': seams, 'warnings': avisos}
    except Exception as e:
        return {'ok': False, 'error': f'Mosaico: {e}'}
