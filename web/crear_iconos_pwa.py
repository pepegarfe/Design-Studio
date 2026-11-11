#!/usr/bin/env python3
"""Genera los iconos de las DOS apps instalables (PWA) y los de la pestaña del navegador.

  Design Studio      → cuadro MAGENTA con la cabeza de corte en blanco (la marca del editor).
  Estación de corte  → cuadro OSCURO con un botón magenta de "cortar" (triángulo de play).

Dos dibujos distintos a propósito: instaladas lado a lado en el teléfono del taller, hay que
distinguirlas de un vistazo. Uso:  python3 web/crear_iconos_pwa.py   (escribe en iconos/)

Por app salen: -192 y -512 (esquinas redondeadas, fondo transparente), -maskable-512 (fondo a
sangre: Android lo recorta con SU forma, así que el dibujo va en el 80 % central), -180
(iPhone), -32 (pestaña) y .ico (el /favicon.ico que piden los navegadores sin que nadie se lo diga).
"""
import os
from PIL import Image, ImageDraw

MAGENTA, OSCURO, BLANCO = '#D11E68', '#171A20', '#ffffff'
AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(os.path.dirname(AQUI), 'iconos')


def _lienzo(size, fondo, sangre):
    s = size * 4                                   # se dibuja en grande y se reduce (antialias)
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if sangre:
        d.rectangle([0, 0, s, s], fill=fondo)
    else:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=fondo)
    return img, d, s


def studio(size, sangre=False):
    """La marca del editor: dos ruedas y las guías cruzadas del cabezal (el SVG de la barra)."""
    img, d, s = _lienzo(size, MAGENTA, sangre)
    pad = 0.24 if sangre else 0.16                 # maskable: todo dentro de la zona segura
    k = s * (1 - 2 * pad) / 24.0
    P = lambda x, y: (s * pad + x * k, s * pad + y * k)
    lw = max(2, int(k * 2.0))
    r = k * 3.0
    for cx, cy in ((6, 6), (6, 18)):
        c = P(cx, cy)
        d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], outline=BLANCO, width=lw)
    for a, b in (((20, 4), (8.12, 15.88)), ((14.47, 14.48), (20, 20)), ((8.12, 8.12), (12, 12))):
        d.line([P(*a), P(*b)], fill=BLANCO, width=lw, joint='curve')
    return img.resize((size, size), Image.LANCZOS)


def estacion(size, sangre=False):
    """La estación: el botón de CORTAR — disco magenta con un triángulo blanco, sobre oscuro."""
    img, d, s = _lienzo(size, OSCURO, sangre)
    c = s / 2.0
    R = s * (0.27 if sangre else 0.33)
    d.ellipse([c - R, c - R, c + R, c + R], fill=MAGENTA)
    t = R * 0.50                                   # triángulo, corrido a la derecha para verse centrado
    d.polygon([(c - t * 0.62, c - t), (c - t * 0.62, c + t), (c + t * 1.05, c)], fill=BLANCO)
    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(SALIDA, exist_ok=True)
    for nombre, dibujo in (('studio', studio), ('estacion', estacion)):
        for n in (32, 180, 192, 512):
            dibujo(n).save(os.path.join(SALIDA, f'{nombre}-{n}.png'))
        dibujo(512, sangre=True).save(os.path.join(SALIDA, f'{nombre}-maskable-512.png'))
        dibujo(256).save(os.path.join(SALIDA, f'{nombre}.ico'), format='ICO',
                         sizes=[(16, 16), (32, 32), (48, 48)])
        print('OK ', nombre)


if __name__ == '__main__':
    main()
