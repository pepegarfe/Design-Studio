#!/usr/bin/env python3
"""
Servicio del plotter compartido por Design Studio (escritorio y servidor web).

⚠️ SIN VERIFICAR con hardware — construido el 21-jul-2026 sin plotter conectado.
La lógica serial se reutiliza de plotter_control.PlotterController (probada en el original),
pero la comunicación real con el plotter aún NO se ha probado en esta app nueva.

Maneja con gracia la ausencia de plotter: cada método devuelve {'ok':False,'error':...}
en vez de tronar.
"""
import os
import time
import json
import re
import threading

import plotter_control as core

# La versión web atiende a varios a la vez. Dos cosas que antes no podían pasar:
# - leer un archivo mientras otro pedido lo escribe (se vería a medias, y cnc_get() caería a los
#   valores de fábrica: el siguiente guardado BORRARÍA las fresas) → _escribir() es de un golpe;
# - dos cambios seguidos pisándose (leer-cambiar-guardar) → _CONFIG_EN_FILA los pone en fila.
_CONFIG_EN_FILA = threading.RLock()


def _en_fila(f):
    def con_fila(*a, **k):
        with _CONFIG_EN_FILA:
            return f(*a, **k)
    con_fila.__name__, con_fila.__doc__ = f.__name__, f.__doc__
    return con_fila


def _escribir(p, texto):
    """Escribe el archivo de un golpe: quien lo lea ve el viejo o el nuevo, nunca uno a medias."""
    tmp = p.with_name(f'{p.name}.{threading.get_ident()}.tmp')
    try:
        tmp.write_text(texto, encoding='utf-8')
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)


@_en_fila
def set_workarea(w, h):
    """Guarda el área de trabajo en la misma config que usa el original."""
    try:
        w, h = float(w), float(h)
        if w < 10 or h < 10:
            return {'ok': False, 'error': 'El área mínima es 10 × 10 mm.'}
        p = core._config_path()
        data = {}
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                data = {}
        data['work_w'] = w
        data['work_h'] = h
        _escribir(p, json.dumps(data))
        return {'ok': True, 'work': [w, h]}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def flip_paths_y(paths):
    """Voltea verticalmente (sobre el centro del conjunto) una lista de {'pts':[[x,y],..]}.

    Convención: la UI dibuja Y hacia ARRIBA, y TODO lo que se le entrega debe venir ya en esa
    orientación. El parser SVG entrega Y-abajo (hay que voltear); el de AI ya invierte la Y al
    parsear y el DXF es Y-arriba de nacimiento (NO voltear). ⚠️ El volteo va POR FORMATO aquí
    en el backend — un volteo ciego de todo en la UI fue el bug que puso los .ai/.dxf de cabeza.
    """
    ys = [p[1] for d in paths for p in d['pts']]
    if not ys:
        return paths
    m = min(ys) + max(ys)
    for d in paths:
        d['pts'] = [[p[0], round(m - p[1], 3)] for p in d['pts']]
    return paths


# ===== CNC (RichAuto) — Fase A: máquina, material y biblioteca de fresas =====
# ⚠️ En archivo PROPIO (cnc_config.json), no en plotter_config.json: la app tkinter
# (_save_config en plotter_control.py) sobrescribe ese JSON con solo sus llaves y
# borraría lo nuestro en silencio. Mismo folder que la config del plotter.

def _cnc_path():
    return core._config_path().with_name('cnc_config.json')


# --- último puerto usado (para no volver a elegirlo cada vez que se abre la app) ---
# ⚠️ Archivo PROPIO por el mismo motivo que cnc_config.json: la app tkinter reescribe
# plotter_config.json con SOLO sus llaves y borraría esto en silencio.
# ⚠️ encoding='utf-8' explícito en las dos direcciones (regla del proyecto).

def _prefs_path():
    return core._config_path().with_name('plotter_prefs.json')


def plotter_prefs():
    """{'port', 'baud'} de la última conexión exitosa. Sin archivo: puerto vacío."""
    try:
        p = _prefs_path()
        if p.exists():
            d = json.loads(p.read_text(encoding='utf-8'))
            return {'port': d.get('port') or None, 'baud': int(d.get('baud') or 9600)}
    except Exception:
        pass
    return {'port': None, 'baud': 9600}


def _prefs_save(port, baud):
    try:
        _escribir(_prefs_path(), json.dumps({'port': port, 'baud': int(baud)}))
    except Exception:
        pass      # sin permisos de escritura no es motivo para impedir el corte


# ESQUEMA v2 (estilo Aspire): la fresa es GEOMETRÍA (nombre, Ø, notas) y sus DATOS DE CORTE
# van POR MATERIAL en `cut` — una fresa física, un juego de números por cada material.
# El material activo (material.type) decide qué juego usa el formulario de trayectorias.
# feed/plunge en mm/min; pass_depth = profundidad por pasada; stepover_pct = % del Ø.
_CUT_FIELDS = ('pass_depth', 'feed', 'plunge', 'rpm', 'stepover_pct')

CNC_DEFAULTS = {
    'machine': 'plotter',                              # máquina activa al abrir la app
    'theme': 'light',                                  # tema de la interfaz (claro por default)
    'units': 'mm',                                     # unidades de MEDICIÓN de la UI: mm | in
    'fillview': False,                                 # pintar las figuras RELLENAS en el lienzo
    'sheets': 1,                                       # nº de hojas/láminas en la mesa (CNC)
    'quote': {'mat_roll': 80.0,                        # $ por METRO LINEAL de rollo (plotter)
              'mat_m2': 350.0,                         # $ por m² de lámina (CNC)
              'rate_plotter': 300.0,                   # $ por hora de máquina (plotter)
              'rate_cnc': 500.0,                       # $ por hora de máquina (CNC)
              'setup': 50.0,                           # cargo fijo de preparación
              'margin': 30.0},                         # margen % sobre el subtotal
    'work': [1220.0, 2440.0],                          # cama de la CNC de Jose (122×244 cm)
    'material': {'thickness': 15.0, 'z_zero': 'top',   # z_zero: 'top' (cara superior) | 'bed' (cama)
                 'clearance': 5.0, 'home_end': True,   # Z segura (mm) y "volver a X0 Y0 al terminar"
                 'spinup': 10.0,                       # seg de espera tras M03 (RPM del husillo)
                 # RPM reales de las marchas S1-S8, LEÍDAS DEL HANDLE de Jose (24-jul:
                 # MACHINE SETUP → Spindle Setup → Spindle speed). ⚠️ S1 es la MÁS RÁPIDA
                 # (18000) y baja 1000 por marcha hasta S8=11000 — el orden no importa:
                 # el archivo elige por CERCANÍA de RPM, no por número.
                 'gears': [18000, 17000, 16000, 15000, 14000, 13000, 12000, 11000],
                 'type': 'mdf'},                       # material ACTIVO (id de `materials`)
    'materials': [
        {'id': 'mdf', 'name': 'MDF / triplay'},
        {'id': 'acr', 'name': 'Acrílico'},
        {'id': 'pvc', 'name': 'PVC espumado'},
        {'id': 'mad', 'name': 'Madera sólida'},
    ],
    'tool_sel': 't6-2f',
    'preset_rev': 1,                                   # ver _PRESET_FIXES: correcciones ya aplicadas
    # Las 5 fresas más comunes de un router de taller, con datos de ARRANQUE por material,
    # basados en tablas de chip load publicadas (feed = RPM × filos × chip load) y práctica
    # de rotulación: MDF ~0.10–0.25 mm/diente; acrílico SIEMPRE mejor con 1 filo (O-flute) y
    # avance alto para no derretir; PVC espumado rápido (3.5–6.5 m/min publicado; aquí
    # conservador) y con menos RPM; madera dura ~0.08–0.20. ⚠️ Son puntos de partida: cada
    # máquina/fresa se afina cortando. Ver .claude/memoria/cnc-richauto.md (fuentes).
    'tools': [
        {'id': 't6-1f', 'name': 'Fresa 6 mm · 1 filo (O-flute)', 'dia': 6.0,
         'notes': 'La reina para acrílico y PVC: un solo filo expulsa la viruta caliente sin derretir el borde.',
         'cut': {
            'mdf': {'pass_depth': 5.0, 'feed': 3000, 'plunge': 900,  'rpm': 18000, 'stepover_pct': 40},
            'acr': {'pass_depth': 3.0, 'feed': 2400, 'plunge': 500,  'rpm': 17000, 'stepover_pct': 40},
            'pvc': {'pass_depth': 8.0, 'feed': 4000, 'plunge': 1200, 'rpm': 14000, 'stepover_pct': 45},
            'mad': {'pass_depth': 4.0, 'feed': 2400, 'plunge': 700,  'rpm': 18000, 'stepover_pct': 40},
         }},
        {'id': 't6-2f', 'name': 'Fresa 6 mm · 2 filos (espiral)', 'dia': 6.0,
         'notes': 'El caballo de batalla en MDF, triplay y madera. En acrílico tiende a derretir: mejor la de 1 filo.',
         'cut': {
            # MDF = los datos del `.tap` de Aspire que deja la pieza limpia (28-oct-2026), NO la
            # tabla de chip load (da 0.04 mm/filo, debajo del rango "ideal"): lo que manda en
            # contornos ondulados es que la máquina vaya PAREJA, no el bocado ideal. 12.2 mm ÷
            # 2.5 = 5 pasadas de 2.44, las mismas de Aspire. Ver memoria rebaba-microsegmentos.
            'mdf': {'pass_depth': 2.5, 'feed': 1270, 'plunge': 381,  'rpm': 16000, 'stepover_pct': 40},
            'acr': {'pass_depth': 2.5, 'feed': 1800, 'plunge': 450,  'rpm': 16000, 'stepover_pct': 35},
            'pvc': {'pass_depth': 6.0, 'feed': 3000, 'plunge': 900,  'rpm': 14000, 'stepover_pct': 45},
            'mad': {'pass_depth': 4.0, 'feed': 2800, 'plunge': 800,  'rpm': 18000, 'stepover_pct': 40},
         }},
        {'id': 't6-comp', 'name': 'Fresa 6 mm · compresión', 'dia': 6.0,
         'notes': 'Para triplay y melamina: borde limpio por AMBAS caras. La primera pasada debe rebasar ~1×Ø de profundidad para que trabaje bien.',
         'cut': {
            'mdf': {'pass_depth': 6.0, 'feed': 3000, 'plunge': 800, 'rpm': 18000, 'stepover_pct': 40},
            'acr': {'pass_depth': 2.5, 'feed': 1500, 'plunge': 400, 'rpm': 16000, 'stepover_pct': 35},
            'pvc': {'pass_depth': 6.0, 'feed': 2500, 'plunge': 800, 'rpm': 14000, 'stepover_pct': 45},
            'mad': {'pass_depth': 5.0, 'feed': 2500, 'plunge': 700, 'rpm': 18000, 'stepover_pct': 40},
         }},
        {'id': 't3-1f', 'name': 'Fresa 3.175 mm (1/8″) · 1 filo', 'dia': 3.175,
         'notes': 'Detalle fino en plásticos y letras chicas. Frágil: no exagerar la pasada.',
         'cut': {
            'mdf': {'pass_depth': 2.5, 'feed': 2000, 'plunge': 600, 'rpm': 18000, 'stepover_pct': 40},
            'acr': {'pass_depth': 1.5, 'feed': 1600, 'plunge': 400, 'rpm': 18000, 'stepover_pct': 40},
            'pvc': {'pass_depth': 3.0, 'feed': 2600, 'plunge': 800, 'rpm': 15000, 'stepover_pct': 45},
            'mad': {'pass_depth': 2.0, 'feed': 1600, 'plunge': 500, 'rpm': 18000, 'stepover_pct': 40},
         }},
        {'id': 't3-2f', 'name': 'Fresa 3.175 mm (1/8″) · 2 filos', 'dia': 3.175,
         'notes': 'Detalle fino en maderas.',
         'cut': {
            'mdf': {'pass_depth': 2.0, 'feed': 2200, 'plunge': 600, 'rpm': 18000, 'stepover_pct': 40},
            'acr': {'pass_depth': 1.2, 'feed': 1200, 'plunge': 350, 'rpm': 16000, 'stepover_pct': 35},
            'pvc': {'pass_depth': 2.5, 'feed': 2200, 'plunge': 700, 'rpm': 15000, 'stepover_pct': 45},
            'mad': {'pass_depth': 1.8, 'feed': 1600, 'plunge': 500, 'rpm': 18000, 'stepover_pct': 40},
         }},
    ],
}

# Migración v1→v2: los presets viejos traían el material EN EL NOMBRE ("Fresa 6 mm · MDF")
# y un solo juego de datos. Se agrupan por (nombre-base, Ø) y cada uno aporta el juego de
# su material; sin palabra clave reconocible, sus datos se copian a TODOS los materiales.
_MAT_KEYWORDS = (('mdf', 'mdf'), ('triplay', 'mdf'), ('acril', 'acr'), ('acríl', 'acr'),
                 ('pvc', 'pvc'), ('espumado', 'pvc'), ('madera', 'mad'))


def _migrate_tools_v1(old_tools, materials):
    mat_ids = [m['id'] for m in materials]
    groups = {}
    for t in old_tools:
        name = str(t.get('name') or 'Fresa')
        low = name.lower()
        mat = next((mid for kw, mid in _MAT_KEYWORDS if kw in low), None)
        base = name
        if mat and '·' in name:
            base = name.rsplit('·', 1)[0].strip()     # "Fresa 6 mm · MDF/triplay" → "Fresa 6 mm"
        cut = {k: float(t.get(k, d)) for k, d in
               zip(_CUT_FIELDS, (3.0, 2000, 500, 18000, 40))}
        key = (base, round(float(t.get('dia', 6.0)), 3))
        g = groups.setdefault(key, {'id': str(t.get('id') or f't{len(groups)}'),
                                    'name': base, 'dia': key[1], 'notes': '', 'cut': {}})
        for mid in ([mat] if mat else mat_ids):       # sin material claro → a todos
            g['cut'].setdefault(mid, dict(cut))
    out = list(groups.values())
    for g in out:                                     # completar materiales faltantes con el 1er juego
        first = next(iter(g['cut'].values()), None)
        for mid in mat_ids:
            if first:
                g['cut'].setdefault(mid, dict(first))
    return out


# Correcciones de los datos de FÁBRICA que deben llegar a las instalaciones que ya existen (la
# config guardada reemplaza a CNC_DEFAULTS entera, así que cambiar los defaults no basta). Cada
# una se aplica UNA vez (`preset_rev`) y solo si la fresa sigue con los números VIEJOS de fábrica:
# si Jose ya los ajustó a mano, son suyos y no se tocan.
_PRESET_FIXES = [
    # rev 1 (28-oct-2026): 6 mm 2 filos en MDF, de F4000 a los datos de Aspire
    (1, 't6-2f', 'mdf',
     {'pass_depth': 5.0, 'feed': 4000, 'plunge': 1000, 'rpm': 18000},
     {'pass_depth': 2.5, 'feed': 1270, 'plunge': 381, 'rpm': 16000}),
]


def _apply_preset_fixes(data, rev):
    """Aplica las correcciones de fábrica pendientes (> rev). Devuelve True si hay que guardar."""
    if rev >= _PRESET_FIXES[-1][0]:
        return False
    for n, tid, mid, old, new in _PRESET_FIXES:
        if n <= rev:
            continue
        for t in data['tools']:
            cut = (t.get('cut') or {}).get(mid)
            if t.get('id') == tid and cut and all(float(cut.get(k, -1)) == v for k, v in old.items()):
                cut.update({k: float(v) for k, v in new.items()})
    data['preset_rev'] = _PRESET_FIXES[-1][0]
    return True


@_en_fila
def cnc_get():
    """Config del CNC completa (defaults + lo guardado encima), migrando esquemas viejos."""
    data = json.loads(json.dumps(CNC_DEFAULTS))   # copia profunda de los defaults
    try:
        p = _cnc_path()
        if p.exists():
            saved = json.loads(p.read_text(encoding='utf-8'))
            for k in ('machine', 'theme', 'units', 'fillview', 'sheets', 'quote', 'work',
                      'material', 'materials', 'tool_sel', 'tools'):
                if k in saved:
                    data[k] = saved[k]
            fix = _apply_preset_fixes(data, int(saved.get('preset_rev', 0) or 0))
            data['material'] = {**CNC_DEFAULTS['material'], **(data.get('material') or {})}
            data['quote'] = {**CNC_DEFAULTS['quote'], **(data.get('quote') or {})}
            if data['tools'] and 'cut' not in data['tools'][0]:      # esquema v1 → migrar
                data['tools'] = _migrate_tools_v1(data['tools'], data['materials'])
                if not any(t['id'] == data['tool_sel'] for t in data['tools']):
                    data['tool_sel'] = data['tools'][0]['id']
                _escribir(p, json.dumps({k: data[k] for k in
                                         ('machine', 'theme', 'units', 'fillview', 'sheets', 'work',
                                          'material', 'materials', 'tool_sel', 'tools')},
                                        ensure_ascii=False, indent=1))
            if not any(m['id'] == data['material'].get('type') for m in data['materials']):
                data['material']['type'] = data['materials'][0]['id']
            if fix:   # aparte: si no se puede escribir, la corrección igual vale en memoria
                try:
                    _escribir(p, json.dumps(data, ensure_ascii=False, indent=1))
                except Exception:
                    pass
    except Exception:
        pass
    data['ok'] = True
    return data


@_en_fila
def cnc_set(patch):
    """Aplica un cambio parcial (solo las llaves presentes) y persiste. Devuelve la config completa."""
    try:
        patch = patch or {}
        cur = cnc_get()
        cur.pop('ok', None)
        if 'machine' in patch:
            if patch['machine'] not in ('plotter', 'cnc'):
                return {'ok': False, 'error': 'Máquina desconocida.'}
            cur['machine'] = patch['machine']
        if 'theme' in patch:
            if patch['theme'] not in ('light', 'dark'):
                return {'ok': False, 'error': 'Tema desconocido.'}
            cur['theme'] = patch['theme']
        if 'units' in patch:
            if patch['units'] not in ('mm', 'in'):
                return {'ok': False, 'error': 'Unidades desconocidas.'}
            cur['units'] = patch['units']
        if 'fillview' in patch:
            cur['fillview'] = bool(patch['fillview'])
        if 'sheets' in patch:
            n = int(patch['sheets'])
            if not (1 <= n <= 8):
                return {'ok': False, 'error': 'Hojas: entre 1 y 8.'}
            cur['sheets'] = n
        if 'quote' in patch:
            q = patch['quote'] or {}
            base = {**CNC_DEFAULTS['quote'], **(cur.get('quote') or {})}
            for k in ('mat_roll', 'mat_m2', 'rate_plotter', 'rate_cnc', 'setup', 'margin'):
                if k in q:
                    v = float(q[k])
                    if not (0 <= v <= 1e7):
                        return {'ok': False, 'error': 'Tarifa fuera de rango.'}
                    base[k] = v
            cur['quote'] = base
        if 'work' in patch:
            w, h = float(patch['work'][0]), float(patch['work'][1])
            if w < 10 or h < 10:
                return {'ok': False, 'error': 'El área mínima es 10 × 10 mm.'}
            cur['work'] = [w, h]
        if 'materials' in patch:
            mats = []
            for m in (patch['materials'] or []):
                nm = str(m.get('name') or '').strip()
                if nm:
                    mats.append({'id': str(m.get('id') or f'm{len(mats)}'), 'name': nm})
            if not mats:
                return {'ok': False, 'error': 'Debe quedar al menos un material.'}
            cur['materials'] = mats
        mat_ids = [m['id'] for m in cur['materials']]
        if 'material' in patch:
            m = patch['material'] or {}
            old = cur['material']
            t = float(m.get('thickness', old['thickness']))
            if not (0 < t <= 500):
                return {'ok': False, 'error': 'Grosor de material fuera de rango (0–500 mm).'}
            zz = m.get('z_zero', old['z_zero'])
            if zz not in ('top', 'bed'):
                return {'ok': False, 'error': 'Cero de Z inválido.'}
            cl = float(m.get('clearance', old.get('clearance', 5.0)))
            if not (1 <= cl <= 200):
                return {'ok': False, 'error': 'La Z segura debe estar entre 1 y 200 mm.'}
            sp = float(m.get('spinup', old.get('spinup', 10.0)))
            if not (0 <= sp <= 120):
                return {'ok': False, 'error': 'La espera del husillo debe estar entre 0 y 120 s.'}
            gears = m.get('gears', old.get('gears'))
            if gears is not None:
                try:
                    gears = [round(float(x)) for x in gears]
                except (TypeError, ValueError):
                    return {'ok': False, 'error': 'Las marchas deben ser números (RPM).'}
                if len(gears) not in (8, 9) or any(not (100 <= g <= 60000) for g in gears):
                    return {'ok': False, 'error': 'Las marchas son 8 valores de RPM (100–60000).'}
            # ⚠️ dict RECONSTRUIDO con lista blanca: toda llave nueva del material debe
            # añadirse AQUÍ o se pierde en cada guardado (así se perdía spinup al inicio)
            cur['material'] = {'thickness': t, 'z_zero': zz, 'clearance': cl,
                               'home_end': bool(m.get('home_end', old.get('home_end', True))),
                               'spinup': sp, 'gears': gears,
                               'type': str(m.get('type', old.get('type', mat_ids[0])))}
        if cur['material'].get('type') not in mat_ids:
            cur['material']['type'] = mat_ids[0]
        if 'tools' in patch:
            tools = []
            for t in (patch['tools'] or []):
                cut = {}
                for mid, c in (t.get('cut') or {}).items():
                    if mid not in mat_ids:
                        continue                      # datos de un material borrado: se podan
                    cut[mid] = {
                        'pass_depth': max(0.1, float(c.get('pass_depth', 3.0))),
                        'feed': max(1, float(c.get('feed', 2000))),
                        'plunge': max(1, float(c.get('plunge', 500))),
                        'rpm': max(0, float(c.get('rpm', 18000))),
                        'stepover_pct': min(90, max(10, float(c.get('stepover_pct') or 40))),
                    }
                if not cut:
                    cut = {mat_ids[0]: {'pass_depth': 3.0, 'feed': 2000, 'plunge': 500,
                                        'rpm': 18000, 'stepover_pct': 40}}
                tools.append({
                    'id': str(t.get('id') or f't{len(tools)}'),
                    'name': str(t.get('name') or 'Fresa'),
                    'dia': max(0.1, float(t.get('dia', 6.0))),
                    'notes': str(t.get('notes') or ''),
                    'cut': cut,
                })
            if not tools:
                return {'ok': False, 'error': 'Debe quedar al menos una fresa.'}
            cur['tools'] = tools
        if 'tool_sel' in patch:
            cur['tool_sel'] = str(patch['tool_sel'])
        if not any(t['id'] == cur['tool_sel'] for t in cur['tools']):
            cur['tool_sel'] = cur['tools'][0]['id']
        _escribir(_cnc_path(), json.dumps(cur, ensure_ascii=False, indent=1))
        cur['ok'] = True
        return cur
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ---- Fases B/C: trayectorias (perfil/cajeado/taladro) y G-code .tap (ver cnc_gcode.py) ----

_NO_CLOSED = ('Ningún trazado cerrado que procesar '
              '(los trazos abiertos solo admiten Perfil "Sobre la línea").')


def _cnc_make(data):
    """Normaliza el payload de la UI y calcula las trayectorias de la operación pedida.
    Devuelve (op, toolpaths, drills, skipped, tool, material, depth, tabs, name)."""
    import cnc_gcode
    paths = [[(float(p[0]), float(p[1])) for p in pts] for pts in (data.get('paths') or [])]
    if not paths:
        raise ValueError('No hay trazados.')
    tool = data.get('tool') or {}
    material = data.get('material') or {}
    depth = float(data.get('depth') or material.get('thickness') or 15.0)
    op = data.get('op') or 'profile'
    dia = float(tool.get('dia', 6.0))
    direction = 'conv' if data.get('direction') == 'conv' else 'climb'
    allowance = float(data.get('allowance') or 0)
    tps, drills = [], []
    if op == 'pocket':
        step = dia * float(tool.get('stepover_pct') or 40) / 100.0
        tps, skipped = cnc_gcode.make_pocket(paths, dia, step, direction, allowance)
    elif op == 'drill':
        drills, skipped = cnc_gcode.drill_points(paths)
    else:
        op = 'profile'
        side = data.get('side') if data.get('side') in ('outside', 'inside', 'on', 'left', 'right') else 'outside'
        tps, skipped = cnc_gcode.make_toolpaths(paths, side, dia, direction, allowance,
                                                last_pass=float(data.get('last_pass') or 0),
                                                last_rev=bool(data.get('last_rev')))
    if not tps and not drills:
        raise ValueError(_NO_CLOSED)
    tabs = data.get('tabs') or None
    if tabs and not tabs.get('on', True):
        tabs = None
    if tabs:
        v = float(tabs.get('v', tabs.get('n', 0)) or 0)   # 'n' = formato viejo (cantidad)
        tabs = {'mode': 'dist' if tabs.get('mode') == 'dist' else 'n', 'v': v,
                'w': float(tabs.get('w') or 8), 'h': float(tabs.get('h') or 3)}
        if v <= 0:
            tabs = None
    return (op, tps, drills, skipped, tool, material, depth, tabs,
            _norm_ramp(data.get('ramp')), data.get('name') or 'diseno')


def _norm_ramp(r):
    """True/False (legado) o dict {'on','type','mode','v'} → lo que espera cnc_gcode."""
    if isinstance(r, dict):
        if not r.get('on', True):
            return None
        return {'type': r.get('type', 'smooth'), 'mode': r.get('mode', 'angle'),
                'v': float(r.get('v') or 0) or None}
    return bool(r)


def _as_job(data):
    """Convierte un payload de trayectoria en un job de cnc_gcode.build_jobs()."""
    op, tps, drills, skipped, tool, material, depth, tabs, ramp, name = _cnc_make(data)
    start = max(0.0, float(data.get('start') or 0))
    if op == 'drill':
        job = {'op': 'drill', 'points': drills, 'tool': tool, 'depth': depth, 'start': start,
               'label': data.get('label') or ('taladro %d puntos' % len(drills))}
    else:
        job = {'op': 'contour', 'toolpaths': tps, 'tool': tool, 'depth': depth, 'start': start,
               'tabs': (tabs if op == 'profile' else None), 'ramp': ramp,
               'label': data.get('label') or ('cajeado' if op == 'pocket' else 'perfil')}
    return job, op, tps, drills, skipped, tool, material, name


def cnc_toolpaths_preview(data):
    """Trayectorias para pintar en el lienzo (+ puntos de taladro) + estimación de tiempo."""
    import cnc_gcode
    try:
        job, op, tps, drills, skipped, tool, material, name = _as_job(data)
        _, secs = cnc_gcode.build_jobs([job], material, name)
        # sin banderas de acabado, y redondeado a 0.01mm: solo se PINTA (el puente
        # JS<->Python de pywebview serializa JSON — floats completos lo engordan 2.4x)
        flat = [[[round(x, 2), round(y, 2)] for x, y in cnc_gcode._rpts(t)] for t in tps]
        gear = cnc_gcode.gear_for(tool.get('rpm', 18000), (material or {}).get('gears'))
        return {'ok': True, 'op': op, 'toolpaths': flat, 'drills': drills,
                'dia': float(tool.get('dia', 6.0)), 'skipped': skipped, 'secs': round(secs),
                'gear': gear or None}
    except Exception as e:
        return {'ok': False, 'error': f'Trayectorias: {e}'}


def cnc_build_tap(data):
    """El .tap completo. Acepta UNA trayectoria (payload plano) o VARIAS en orden
    (data['jobs'] = lista de payloads; material/name compartidos). Todas las de la
    lista deben usar la MISMA fresa: el RichAuto no tiene cambiador automático."""
    import cnc_gcode
    try:
        raw = data.get('jobs')
        if raw:
            mat, name = data.get('material') or {}, data.get('name') or 'diseno'
            ids = {(j.get('tool') or {}).get('id') or (j.get('tool') or {}).get('name')
                   for j in raw}
            if len(ids) > 1:
                return {'ok': False, 'error':
                        'Las trayectorias activas usan FRESAS DISTINTAS. Exporta un archivo '
                        'por fresa (apaga las otras trayectorias con el ojito) — en la '
                        'máquina se cambia la fresa y se vuelve a fijar el cero de Z.'}
            jobs, skipped = [], 0
            for j in raw:
                try:
                    job, _, _, _, sk, _, _, _ = _as_job({**j, 'material': mat, 'name': name})
                except Exception as e:
                    return {'ok': False, 'error': f"{j.get('label') or 'trayectoria'}: {e}"}
                jobs.append(job)
                skipped += sk
            tap, secs = cnc_gcode.build_jobs(jobs, mat, name)
        else:
            job, _, _, _, skipped, _, mat, name = _as_job(data)
            tap, secs = cnc_gcode.build_jobs([job], mat, name)
        return {'ok': True, 'tap': tap, 'lines': tap.count('\n'),
                'skipped': skipped, 'secs': round(secs)}
    except Exception as e:
        return {'ok': False, 'error': f'G-code: {e}'}


def load_workarea():
    """Área de trabajo guardada (misma config que la app vieja), o el default del plotter."""
    try:
        p = core._config_path()
        if p.exists():
            d = json.loads(p.read_text(encoding='utf-8'))   # ⚠️ ver la regla del encoding abajo
            return float(d.get('work_w', 3000.0)), float(d.get('work_h', 600.0))
    except Exception:
        pass
    return 3000.0, 600.0


def load_vector(path):
    """Lee un vector (SVG/DXF/AI) y lo entrega como lo espera la UI: trazados en mm
    con Y hacia ARRIBA (el volteo del SVG va aquí, POR FORMATO — ver flip_paths_y)."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == '.svg':
            styled = core.SVGParser().parse(path)
        elif ext == '.dxf':
            styled = core.DXFParser().parse(path)
        elif ext == '.ai':
            styled = core.AIParser().parse(path)
        else:
            return {'ok': False, 'error': 'Formato no soportado (usa SVG, DXF, AI o .dstudio).'}
    except Exception as e:
        return {'ok': False, 'error': f'No se pudo leer el archivo: {e}'}
    paths = []
    xs, ys = [], []
    for d in styled:
        pts = d.get('pts') or []
        if len(pts) < 2:
            continue
        rp = [[round(float(x), 3), round(float(y), 3)] for (x, y) in pts]
        paths.append({'pts': rp})
        for x, y in rp:
            xs.append(x); ys.append(y)
    bbox = [min(xs), min(ys), max(xs), max(ys)] if xs else [0, 0, 0, 0]
    if ext == '.svg':
        flip_paths_y(paths)   # solo SVG viene Y-abajo; AI/DXF ya llegan Y-arriba
    ww, wh = load_workarea()
    return {'ok': True, 'name': os.path.basename(path),
            'paths': paths, 'bbox': bbox, 'work': [ww, wh]}


def build_hpgl(data):
    """Genera HPGL desde trazados efectivos (mm) + parámetros de corte."""
    conv = core.HPGLConverter(
        speed=int(float(data.get('speed', 320))),
        pressure=int(float(data.get('pressure', 140))),
        overcut_mm=float(data.get('overcut', 0.0)),
        corner_angle_deg=float(data.get('corner', 0.0)))
    conv.initialize()
    for p in data.get('paths', []):
        conv.add_path([(float(pt[0]), float(pt[1])) for pt in p])
    conv.finalize()
    return conv.get_hpgl()


def test_square_hpgl(size_mm=10):
    """El cuadrado del test de corte. Lo usan el escritorio y el navegador (Web Serial)."""
    return core.HPGLConverter(speed=200, pressure=140).test_square(size_mm)


def _port_items():
    """Puertos con nombre legible y separando el grano de la paja.

    La señal es el VID/PID: un cable USB de verdad lo trae (el FTDI del plotter da
    'FT232R USB UART' de fabricante FTDI); los aparatos internos del sistema
    (Bluetooth, audífonos emparejados, consola de depuración) vienen VACÍOS y NUNCA
    son un plotter. Por eso se marcan como 'otro' y se mandan al fondo de la lista:
    el nombre crudo /dev/cu.usbserial-AO004NFH no le dice nada a nadie.
    """
    if not core.HAS_SERIAL:
        return []
    import serial.tools.list_ports as lp
    usb, otros = [], []
    for p in lp.comports():
        dev = p.device
        corto = dev.replace('/dev/cu.', '').replace('/dev/tty.', '')
        desc = (p.description or '').strip()
        if desc.lower() in ('n/a', 'none', ''):
            desc = ''
        # en Windows la descripción ya trae el COM ('USB Serial Port (COM3)'): sobra
        desc = re.sub(r'\s*\(COM\d+\)$', '', desc)
        if p.vid is not None:                       # cable USB real
            det = desc or (p.manufacturer or '').strip() or 'adaptador USB'
            # en Windows el propio nombre (COM3) ya es corto y es el que la gente busca
            base = dev if dev.upper().startswith('COM') else 'Cable USB'
            usb.append({'port': dev, 'label': f'{base} — {det}', 'kind': 'usb'})
        else:
            if 'bluetooth' in corto.lower():
                lab = 'Bluetooth (entrante)'
            elif 'debug' in corto.lower():
                lab = 'Consola interna del equipo'
            elif dev.upper().startswith('COM'):
                lab = f'{dev} — puerto serie del equipo'
            else:
                lab = corto
            otros.append({'port': dev, 'label': lab, 'kind': 'otro'})
    return usb + otros                              # los cables USB primero


class PlotterService:
    def __init__(self):
        self.ctrl = core.PlotterController()
        self.port = None
        self.baud = 9600
        self._thread = None
        self._abort = False
        self._prog = {'active': False, 'sent': 0, 'total': 0, 'done': False,
                      'error': None, 'cancelled': False}

    # --- estado / puertos ---
    def ports(self):
        try:
            items = _port_items()
            # 'ports' (solo nombres) se mantiene por compatibilidad con la UI vieja
            return {'ok': True, 'ports': [i['port'] for i in items], 'items': items,
                    'has_serial': core.HAS_SERIAL}
        except Exception as e:
            return {'ok': False, 'error': str(e), 'ports': [], 'items': []}

    def status(self):
        pref = plotter_prefs()
        return {'ok': True, 'connected': bool(self.ctrl.connected),
                'port': self.port, 'baud': self.baud, 'has_serial': core.HAS_SERIAL,
                'last_port': pref['port'], 'last_baud': pref['baud']}

    # --- conexión ---
    def connect(self, port, baud=9600):
        if not port:
            return {'ok': False, 'error': 'Elige un puerto primero.'}
        try:
            self.ctrl.connect(port, int(baud))
            self.port, self.baud = port, int(baud)
            _prefs_save(self.port, self.baud)     # la próxima vez sale ya elegido
            try:
                self.ctrl.send('IN;')
            except Exception:
                pass
            return self.status()
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo conectar: {e}'}

    def disconnect(self):
        try:
            self.ctrl.disconnect()
        except Exception:
            pass
        return self.status()

    # --- control manual ---
    def _guard(self):
        return None if self.ctrl.connected else {'ok': False, 'error': 'Plotter no conectado'}

    def jog(self, direction, dist):
        g = self._guard()
        if g:
            return g
        if direction not in ('up', 'down', 'left', 'right'):
            return {'ok': False, 'error': 'Dirección inválida'}
        try:
            self.ctrl.move_relative(direction, float(dist))
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def pen(self, down):
        g = self._guard()
        if g:
            return g
        try:
            self.ctrl.send('PD;' if down else 'PU;')
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def command(self, which):
        g = self._guard()
        if g:
            return g
        cmd = {'origin': 'PS;', 'home': 'PU0,0;'}.get(which)
        if not cmd:
            return {'ok': False, 'error': 'Comando desconocido'}
        try:
            self.ctrl.send(cmd)
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # --- envío del corte (hilo de fondo + progreso) ---
    def send_design(self, data):
        g = self._guard()
        if g:
            return g
        if self._prog['active']:
            return {'ok': False, 'error': 'Ya hay un envío en curso'}
        try:
            hpgl = build_hpgl(data)
        except Exception as e:
            return {'ok': False, 'error': f'HPGL: {e}'}
        self._abort = False
        self._prog = {'active': True, 'sent': 0, 'total': 0, 'done': False,
                      'error': None, 'cancelled': False}
        lines = [l.strip() for l in hpgl.split('\n') if l.strip()]
        self._prog['total'] = len(lines)

        def run():
            try:
                for i, line in enumerate(lines):
                    if self._abort:
                        self._prog['cancelled'] = True
                        break
                    self.ctrl.send(line)
                    time.sleep(0.01)
                    self._prog['sent'] = i + 1
            except Exception as e:
                self._prog['error'] = str(e)
            finally:
                self._prog['active'] = False
                self._prog['done'] = True

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return {'ok': True, 'total': len(lines)}

    def progress(self):
        p = dict(self._prog)
        p['ok'] = True
        return p

    def cancel(self):
        self._abort = True
        try:
            self.ctrl.abort()
        except Exception:
            pass
        return {'ok': True}

    def test_cut(self, size_mm=10):
        g = self._guard()
        if g:
            return g
        try:
            return self._send_raw(test_square_hpgl(size_mm))
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _send_raw(self, hpgl):
        if self._prog['active']:
            return {'ok': False, 'error': 'Ya hay un envío en curso'}
        self._abort = False
        lines = [l.strip() for l in hpgl.split('\n') if l.strip()]
        self._prog = {'active': True, 'sent': 0, 'total': len(lines), 'done': False,
                      'error': None, 'cancelled': False}

        def run():
            try:
                for i, line in enumerate(lines):
                    if self._abort:
                        self._prog['cancelled'] = True
                        break
                    self.ctrl.send(line)
                    time.sleep(0.01)
                    self._prog['sent'] = i + 1
            except Exception as e:
                self._prog['error'] = str(e)
            finally:
                self._prog['active'] = False
                self._prog['done'] = True

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return {'ok': True, 'total': len(lines)}


# Instancia única compartida
SERVICE = PlotterService()


# ------------------------------------------------------------ autoguardado
# Respaldo periódico del proyecto (autosave.dstudio junto a la config): si la
# app muere, al reabrir se ofrece recuperar. Se limpia al guardar de verdad.

def _autosave_path():
    return _cnc_path().parent / 'autosave.dstudio'


def autosave_save(data):
    try:
        _escribir(_autosave_path(), json.dumps(data or {}, ensure_ascii=False))
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def autosave_load():
    p = _autosave_path()
    if not p.exists():
        return {'ok': True, 'exists': False}
    try:
        import datetime
        proj = json.loads(p.read_text(encoding='utf-8'))
        if not proj.get('objects'):
            return {'ok': True, 'exists': False}
        hhmm = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime('%H:%M')
        return {'ok': True, 'exists': True, 'project': proj, 'time': hhmm}
    except Exception:
        return {'ok': True, 'exists': False}


def autosave_clear():
    try:
        _autosave_path().unlink(missing_ok=True)
    except Exception:
        pass
    return {'ok': True}

