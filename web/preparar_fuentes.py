"""Baja de Google Fonts las familias de web/fuentes_google.txt, como .ttf, a una carpeta.

Uso:  python web/preparar_fuentes.py <carpeta_destino>

Lo corre el Dockerfile al construir el servidor (Railway): allá no hay fuentes de la Mac, y el
servidor lee SOLO las de DS_FUENTES (text_vector._font_dirs). Por familia pide Regular y Bold con
sus itálicas, si existen (lo mismo que se instaló en la Mac en ago-2026, ver fuentes-google.md).

⚠️ El User-Agent VIEJO no es descuido: con uno moderno Google responde .woff2, que fontTools no
abre sin librerías extra y text_vector no escanea. Con este responde .ttf.
⚠️ Falla (código 1) si se pierde más del 5 % de las familias: un servidor que arranca con la
mitad de las fuentes no da ningún error, solo le faltan fuentes a quien las busque.
"""
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

AQUI = os.path.dirname(os.path.abspath(__file__))
LISTA = os.path.join(AQUI, 'fuentes_google.txt')
# Safari 5 (2011): Firefox 24 YA recibe .woff (probado el 11-nov-2026: 0 de 206 familias).
UA_VIEJO = ('Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10_6_8; de-at) AppleWebKit/533.21.1 '
            '(KHTML, like Gecko) Version/5.0.5 Safari/533.21.1')
ESTILOS = [(0, 400), (0, 700), (1, 400), (1, 700)]   # (itálica, peso)


def _bajar(url, intentos=3):
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA_VIEJO})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500 or i == intentos - 1:   # un 400 (estilo que no existe) no mejora
                raise
        except Exception:
            if i == intentos - 1:
                raise
        time.sleep(2 * (i + 1))
    raise RuntimeError('sin respuesta: ' + url)


def _css(familia, estilos):
    pares = ';'.join(f'{i},{w}' for i, w in estilos)
    q = urllib.parse.quote(familia) + ':ital,wght@' + pares
    return _bajar('https://fonts.googleapis.com/css2?family=' + q).decode('utf-8')


def _bloques(css):
    """[(itálica, peso, url_ttf)] de una hoja css2."""
    out = []
    for b in re.findall(r'@font-face\s*{(.*?)}', css, re.S):
        it = 1 if re.search(r'font-style:\s*italic', b) else 0
        w = re.search(r'font-weight:\s*(\d+)', b)
        u = re.search(r'url\((https://[^)]+\.ttf)\)', b)
        if w and u:
            out.append((it, int(w.group(1)), u.group(1)))
    return out


def una_familia(familia, destino):
    """Devuelve cuántos archivos bajó (0 = la familia se perdió)."""
    try:
        css = _css(familia, ESTILOS)
    except Exception:
        # Google responde 400 si pides un estilo que la familia no tiene: entonces se pide
        # cada uno por separado y se queda con los que existan.
        css = ''
        for e in ESTILOS:
            try:
                css += _css(familia, [e])
            except Exception:
                pass
        if not css:
            try:   # familias sin peso 400 (solo 300, solo 800...): lo que Google dé por defecto
                css = _bajar('https://fonts.googleapis.com/css2?family='
                             + urllib.parse.quote(familia)).decode('utf-8')
            except Exception:
                return 0
    vistos, n = set(), 0
    base = re.sub(r'[^A-Za-z0-9]+', '', familia)
    for it, w, url in _bloques(css):
        if url in vistos:   # una fuente variable da la MISMA url para varios pesos
            continue
        vistos.add(url)
        nombre = f"{base}-{w}{'i' if it else ''}.ttf"
        ruta = os.path.join(destino, nombre)
        if not os.path.exists(ruta):
            with open(ruta, 'wb') as f:
                f.write(_bajar(url))
        n += 1
    return n


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    destino = sys.argv[1]
    os.makedirs(destino, exist_ok=True)
    with open(LISTA, encoding='utf-8') as f:
        familias = [l.strip() for l in f if l.strip() and not l.startswith('#')]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda fa: (fa, una_familia(fa, destino)), familias))
    perdidas = [fa for fa, n in res if not n]
    archivos = sum(n for _, n in res)
    print(f'Fuentes: {len(familias) - len(perdidas)}/{len(familias)} familias, {archivos} archivos')
    if perdidas:
        print('  sin bajar:', ', '.join(perdidas))
    return 1 if len(perdidas) > len(familias) * 0.05 else 0


if __name__ == '__main__':
    sys.exit(main())
