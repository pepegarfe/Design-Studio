"""Los bytes EXACTOS que la app de escritorio le manda al plotter, sin plotter.

Cambia el cable (serial.Serial) por uno de mentira que anota todo lo que se escribe y corre
el servicio real del escritorio (PlotterService). web/test_plotter_web.mjs compara esto,
byte a byte, con lo que manda el navegador. No guarda nada: el "último puerto" no se toca.

Uso: python3 web/bytes_escritorio.py   (imprime JSON)
"""
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AQUI)
sys.argv[0] = os.path.join(AQUI, 'design_studio.py')

import plotter_control as core
import studio_backend as be

DISENO = {'paths': [[[0, 0], [40, 0], [40, 20], [0, 20], [0, 0]],
                    [[60, 5], [75.5, 5], [70, 18.25]]],
          'speed': 300, 'pressure': 120, 'overcut': 0.5, 'corner': 30}


class CableFalso:
    def __init__(self, *a, **k):
        self.escrito = bytearray()
        self.is_open = True

    def write(self, b):
        self.escrito += b

    def flush(self):
        pass

    def close(self):
        self.is_open = False


core.serial.Serial = CableFalso
be._prefs_save = lambda *a: None   # no tocar la config real


def esperar(svc):
    while svc._prog['active']:
        time.sleep(0.01)


svc = be.PlotterService()
svc.connect('falso', 9600)
cable: CableFalso = svc.ctrl.ser   # type: ignore[assignment]
salida = {}


def tomar(nombre, accion):
    cable.escrito.clear()
    accion()
    esperar(svc)
    salida[nombre] = cable.escrito.decode('latin-1')


salida['conectar'] = cable.escrito.decode('latin-1')
tomar('jog_der_2.5', lambda: svc.jog('right', 2.5))
tomar('jog_abajo_0.33', lambda: svc.jog('down', 0.33))
tomar('jog_izq_10', lambda: svc.jog('left', 10))
tomar('jog_arriba_1', lambda: svc.jog('up', 1))
tomar('pluma_abajo', lambda: svc.pen(True))
tomar('pluma_arriba', lambda: svc.pen(False))
tomar('origen', lambda: svc.command('origin'))
tomar('casa', lambda: svc.command('home'))
tomar('enviar', lambda: svc.send_design(dict(DISENO)))
tomar('test_corte', lambda: svc.test_cut())
tomar('cancelar', lambda: svc.cancel())
salida['diseno'] = DISENO
# lo que el servidor le devuelve al navegador (/api/hpgl y /api/test_square)
salida['hpgl'] = be.build_hpgl(DISENO)
salida['test_square_hpgl'] = be.test_square_hpgl(10)
print(json.dumps(salida))
