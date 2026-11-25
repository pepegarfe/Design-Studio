"""Barrido de combinaciones de corte CNC: mide en el G-code si la fresa llega al fondo en
TODO el recorrido, si se pasa, si cruza material en rápido, si corta en línea recta por fuera,
si los puentes quedan a su altura y si hay picadas verticales con la rampa encendida.

    /opt/homebrew/bin/python3 barrido_cnc.py [semilla] [cuántos]      (p. ej. 7 4000, ~4 min)

Esperado hoy (25-nov-2026): solo "NO GENERA" (trazos abiertos con Por fuera/dentro o
cajeado: es correcto rechazarlos) y unas ~50 "PICADA VERTICAL" de menos de 0.4 mm con puentes.
Complementa a auditar_gcode.py: aquél prueba casos fijos; éste busca combinaciones raras."""
import sys, math, re, random, itertools, collections
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import studio_backend as sb, cnc_gcode as cg

TOOL = {'id': 't', 'name': 'F6', 'dia': 6.0, 'pass_depth': 2.7, 'feed': 1270, 'plunge': 381,
        'rpm': 16000, 'stepover_pct': 40}

def sq(x, y, w, h): return [(x, y), (x+w, y), (x+w, y+h), (x, y+h), (x, y)]
def circ(cx, cy, r, n=72): return [(cx+r*math.cos(2*math.pi*k/n), cy+r*math.sin(2*math.pi*k/n)) for k in range(n)] + [(cx+r, cy)]
def star(cx, cy, r1, r2, n=5):
    p = [(cx+(r1 if k % 2 == 0 else r2)*math.cos(math.pi*k/n), cy+(r1 if k % 2 == 0 else r2)*math.sin(math.pi*k/n)) for k in range(2*n)]
    return p + [p[0]]

SHAPES = {
    'cuadrado': [sq(20, 20, 80, 50)],
    'circulo': [circ(60, 60, 30)],
    'circulo_chico': [circ(30, 30, 5)],
    'estrella': [star(60, 60, 40, 18)],
    'con_hueco': [sq(10, 10, 100, 80), circ(60, 50, 15)],
    'linea': [[(20, 20), (80, 20)]],
    'linea_L': [[(20, 20), (80, 20), (80, 70)]],
    'linea_corta': [[(20, 20), (32, 20)]],
    'linea_curva': [[(20+k, 20+10*math.sin(k/8)) for k in range(0, 101, 2)]],
}
OPS = [('profile', 'outside'), ('profile', 'inside'), ('profile', 'on'), ('profile', 'left'),
       ('profile', 'right'), ('pocket', None)]
RAMPS = [None, {'on': True, 'type': 'smooth', 'mode': 'angle', 'v': 10},
         {'on': True, 'type': 'smooth', 'mode': 'dist', 'v': 25},
         {'on': True, 'type': 'zigzag', 'mode': 'angle', 'v': 10},
         {'on': True, 'type': 'zigzag', 'mode': 'dist', 'v': 25},
         {'on': True, 'type': 'spiral', 'mode': 'angle', 'v': 3}]
TABS = [None, {'on': True, 'mode': 'n', 'v': 3, 'w': 8, 'h': 3},
        {'on': True, 'mode': 'dist', 'v': 60, 'w': 8, 'h': 3}, 'manual']

def parse(tap):
    """Lista de movimientos (x0,y0,z0,x1,y1,z1,rapido)."""
    x = y = None; z = None; g = None; mv = []
    for ln in tap.splitlines():
        if ln.startswith('(') or not ln.strip(): continue
        m = re.match(r'G0?([01])\b', ln)
        if m: g = int(m.group(1))
        pal = dict(re.findall(r'([XYZ])(-?\d+\.?\d*)', ln))
        if not pal: continue
        nx = float(pal.get('X', x if x is not None else 0)); ny = float(pal.get('Y', y if y is not None else 0))
        nz = float(pal['Z']) if 'Z' in pal else z
        if x is not None and z is not None:
            mv.append((x, y, z, nx, ny, nz, g == 0))
        x, y, z = nx, ny, nz
    return mv

C = 0.1
def raster(mv):
    cel = {}
    for x0, y0, z0, x1, y1, z1, rap in mv:
        if rap: continue
        L = math.hypot(x1-x0, y1-y0); n = max(1, int(L / 0.04))
        for k in range(n+1):
            t = k/n; px, py, pz = x0+(x1-x0)*t, y0+(y1-y0)*t, z0+(z1-z0)*t
            key = (round(px/C), round(py/C))
            if pz < cel.get(key, 1e9): cel[key] = pz
    return cel

def hondo(cel, x, y):
    kx, ky = round(x/C), round(y/C); best = 1e9
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            v = cel.get((kx+dx, ky+dy))
            if v is not None and v < best: best = v
    return best

def muestras(pts, paso=0.5):
    out = []
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0]-a[0], b[1]-a[1]); n = max(1, int(L/paso))
        for k in range(n): out.append((a[0]+(b[0]-a[0])*k/n, a[1]+(b[1]-a[1])*k/n))
    out.append(pts[-1]); return out

def caso(shape, op, side, ramp, tabs, last_pass, start, depth, zz):
    mat = {'thickness': 15.0, 'z_zero': zz, 'clearance': 5.0, 'home_end': True}
    pl = {'paths': SHAPES[shape], 'op': op, 'depth': depth, 'tool': TOOL, 'material': mat,
          'name': 'b', 'label': 'b', 'direction': 'climb', 'start': start,
          'last_pass': last_pass, 'last_rev': False}
    if side: pl['side'] = side
    if ramp: pl['ramp'] = ramp
    if tabs == 'manual':
        # un puente a mano sobre el primer anillo del recorrido calculado
        pv = sb.cnc_toolpaths_preview(pl)
        if not pv.get('ok') or not pv['toolpaths']: return None
        t0 = pv['toolpaths'][0]; pl['tabs'] = {'on': True, 'mode': 'manual', 'pts': [t0[len(t0)//3]], 'w': 8, 'h': 3}
    elif tabs: pl['tabs'] = tabs
    r = sb.cnc_build_tap(pl)
    if not r.get('ok'):
        return ('NO GENERA', r.get('error'))
    job, op2, tps, drills, *_ = sb._as_job(pl)
    z_top = 15.0 if zz == 'bed' else 0.0
    z_fin = z_top - start - depth
    mv = parse(r['tap'])
    prob = []
    # 1) nunca más hondo de lo pedido
    zmin = min(min(m[2], m[5]) for m in mv)
    if zmin < z_fin - 1e-3: prob.append('MAS HONDO %.3f < %.3f' % (zmin, z_fin))
    # 2) rápidos dentro del material
    for m in mv:
        if m[6] and (m[0], m[1]) != (m[3], m[4]) and min(m[2], m[5]) < z_top - start - 1e-6:
            prob.append('RAPIDO EN MATERIAL z=%.2f' % min(m[2], m[5])); break
    # 3) cortes que no van sobre ningún recorrido (línea recta por donde no debe)
    rec = set()
    for t in tps:
        for x, y in muestras(cg._rpts(t), 0.05): rec.add((round(x/C), round(y/C)))
    fuera = 0
    for m in mv:
        if m[6] or min(m[2], m[5]) >= z_top - start - 1e-6: continue
        L = math.hypot(m[3]-m[0], m[4]-m[1]); n = max(1, int(L/0.3))
        for k in range(1, n):
            px, py = m[0]+(m[3]-m[0])*k/n, m[1]+(m[4]-m[1])*k/n
            kx, ky = round(px/C), round(py/C)
            if not any((kx+a, ky+b) in rec for a in (-1, 0, 1) for b in (-1, 0, 1)):
                fuera += 1; break
    if fuera: prob.append('CORTE FUERA DEL RECORRIDO en %d movimientos' % fuera)
    # 4) todo el recorrido llega al fondo (fuera de los puentes)
    cel = raster(mv)
    tabxy = []
    if job.get('tabs'):
        tabxy = cg.tab_points(tps, job['tabs'], job['depth'], 6.0)[0]
    exc = 4 + 6 + 3*2 + 0.5     # medio puente + rampa del puente + margen
    peor, donde = 0, None
    for t in tps:
        for x, y in muestras(cg._rpts(t)):
            if any(math.hypot(x-a, y-b) < exc for a, b in tabxy): continue
            h = hondo(cel, x, y)
            if h - z_fin > peor: peor, donde = h - z_fin, (round(x, 1), round(y, 1))
    if peor > 0.02: prob.append('NO LLEGA AL FONDO: falta %.2f mm en %s' % (peor, donde))
    # 5) los puentes existen a su altura
    if tabxy:
        z_tab = z_fin + min(3, depth)
        for a, b in tabxy:
            h = hondo(cel, a, b)
            if abs(h - z_tab) > 0.05: prob.append('PUENTE A %.2f (esperado %.2f) en %s' % (h, z_tab, (round(a, 1), round(b, 1)))); break
    # 6) con rampa, ninguna bajada vertical en material nuevo (más hondo que lo ya cortado ahí)
    if ramp:
        visto = {}
        for m in mv:
            if m[6]: continue
            if (m[0], m[1]) == (m[3], m[4]) and m[5] < m[2] - 1e-6 and m[5] < z_top - start - 1e-6:
                k = (round(m[0]/C), round(m[1]/C))
                prev = min([visto.get((k[0]+a, k[1]+b), 1e9) for a in (-1, 0, 1) for b in (-1, 0, 1)])
                if m[5] < min(prev, z_top - start) - 0.05:
                    prob.append('PICADA VERTICAL CON RAMPA de %.2f mm a z=%.2f en %s' % (min(prev, z_top - start) - m[5], m[5], (m[0], m[1]))); break
            L = math.hypot(m[3]-m[0], m[4]-m[1]); n = max(1, int(L/0.04))
            for k in range(n+1):
                t = k/n; key = (round((m[0]+(m[3]-m[0])*t)/C), round((m[1]+(m[4]-m[1])*t)/C))
                pz = m[2]+(m[5]-m[2])*t
                if pz < visto.get(key, 1e9): visto[key] = pz
    return prob

if __name__ == '__main__':
    random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    todos = list(itertools.product(SHAPES, OPS, range(len(RAMPS)), range(len(TABS)), (0, 0.3), (0, 2), (2.5, 8, 12.2), ('top', 'bed')))
    random.shuffle(todos)
    tipos = collections.defaultdict(list)
    hechos = 0
    for shape, (op, side), ri, ti, lp, st, d, zz in todos[:N]:
        if op == 'pocket' and ti: continue
        try:
            p = caso(shape, op, side, RAMPS[ri], TABS[ti], lp, st, d, zz)
        except Exception as e:
            p = ['EXCEPCION %r' % e]
        if p is None: continue
        hechos += 1
        if isinstance(p, tuple):
            tipos['NO GENERA: ' + str(p[1])[:80]].append((shape, op, side, ri, ti, lp, st, d, zz)); continue
        for x in p:
            tipos[re.sub(r'[-\d.]+', '#', x)[:60]].append((shape, op, side, ri, ti, lp, st, d, zz, x))
    print('casos probados:', hechos)
    for k, v in sorted(tipos.items(), key=lambda kv: -len(kv[1])):
        print('\n== %s  (%d)' % (k, len(v)))
        for e in v[:6]: print('   ', e)

def resumen(N, seed):
    random.seed(seed)
    todos = list(itertools.product(SHAPES, OPS, range(len(RAMPS)), range(len(TABS)), (0, 0.3), (0, 2), (2.5, 8, 12.2), ('top', 'bed')))
    random.shuffle(todos)
    cuenta = collections.Counter(); total = collections.Counter(); ej = {}
    for shape, (op, side), ri, ti, lp, st, d, zz in todos[:N]:
        if op == 'pocket' and ti: continue
        p = caso(shape, op, side, RAMPS[ri], TABS[ti], lp, st, d, zz)
        if p is None or isinstance(p, tuple): continue
        abierto = shape.startswith('linea')
        for dim, val in (('forma', shape), ('op', op + '/' + str(side)), ('rampa', ri), ('puentes', ti), ('acabado', lp), ('inicio', st), ('prof', d), ('cero', zz)):
            total[(dim, val)] += 1
            for x in p:
                t = x.split(' a z')[0].split(':')[0].split(' en ')[0][:25]
                cuenta[(t, dim, val)] += 1
                ej.setdefault((t, dim, val), (shape, op, side, ri, ti, lp, st, d, zz, x))
    tipos = sorted({k[0] for k in cuenta})
    for t in tipos:
        print('\n######', t)
        for dim in ('forma', 'op', 'rampa', 'puentes', 'acabado', 'inicio', 'prof', 'cero'):
            fila = ['%s=%d/%d' % (v, cuenta[(t, d2, v)], total[(d2, v)]) for (d2, v) in sorted(total, key=str) if d2 == dim]
            print('  ', dim, ' '.join(fila))
