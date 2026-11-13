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
