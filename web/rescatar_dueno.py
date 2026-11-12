#!/usr/bin/env python3
"""Rescate: el DUEÑO olvidó su contraseña.

Desde la web nadie puede restablecer la cuenta del dueño (es quien restablece a los demás), así
que esto se corre EN EL SERVIDOR, donde están los datos:

    Railway:   railway ssh    y luego    python web/rescatar_dueno.py
    En la Mac: /opt/homebrew/bin/python3 web/rescatar_dueno.py

Imprime una contraseña TEMPORAL. Al entrar con ella el sitio obliga a elegir una nueva, y todas
las sesiones abiertas del dueño se cierran. No toca diseños, fresas ni las demás cuentas.
Lee las cuentas de DS_DATOS (en Railway ya viene puesto: /data).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import web_auth as auth   # noqa: E402


def main():
    quien = auth.dueno()
    if not quien:
        print('No hay ninguna cuenta en', auth.DATOS, '- nada que rescatar.')
        return 1
    clave, err = auth.restablecer_clave(quien, rescate=True)
    if err:
        print('No se pudo:', err)
        return 1
    print('Cuenta del dueño:', quien)
    print('Contraseña temporal:', clave)
    print('Entra con ella: el sitio te pedirá elegir una nueva.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
