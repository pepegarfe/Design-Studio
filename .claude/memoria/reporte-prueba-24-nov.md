---
name: reporte-prueba-24-nov
description: "Reporte de un probador (24-nov-2026) cortando un SVG de 23 figuras en la CNC: qué se arregló ese día (foco, grupos, casilla, Recorridos, zoom real) y qué quedó pendiente (mosaico, textos, hoja por trabajo, selección por color, operación por capa, calibrar por pantalla)"
metadata:
  node_type: memory
  type: project
  originSessionId: 63cead03-81d7-4118-88e7-6e9e343252a1
  modified: 2026-11-24T22:36:33.990Z
---

# Reporte de prueba del 24-nov-2026 (CNC, SVG de 23 figuras)

Jose pegó el reporte de alguien que hizo un trabajo real: un SVG de 1220×550 con 17 barrenos,
letras A–D y una nota «voltear». Se reprodujo cada punto en la copia de prueba
([[como-verificar-la-interfaz]]) antes de tocar nada.

## Hecho y subido ese día
- **Letras que cambiaban la herramienta**: el renombrado con doble clic perdía el foco cuando la
  vista previa llegaba a media escritura (solo en Railway, que es lento). Se reprodujo retrasando
  la respuesta 3 s. Regla en `.claude/rules/interfaz-web.md`.
- **Doble clic = entrar al grupo** (el SVG entra como UN grupo).
- **Ojo → casilla «se corta»**, **botón «Recorridos» junto al zoom**, **el clic toma la figura y
  no el recorrido**: elegidos por Jose de opciones dibujadas (ver [[preferencias-interfaz-jose]]).
  Descubierto: **Calcular enciende los recorridos solo** — por eso tapaban los barrenos.
- **Zoom: 100 % = tamaño real** (antes era ~¼) + escribir el % + «Calibrar tamaño real» con regla.

## No reproducido
- «Cambié los puentes de 3 a 4 y no tomó»: en la prueba sí tomó al pulsar Recalcular. Sospecha
  (mía): se cambió el número sin Recalcular. Si vuelve a salir, preguntar los pasos exactos.

## Hecho la segunda tanda (24-nov-2026, «haz del 1 al 4 sin parar»)
- ✅ **Textos del SVG → notas** que se ven y no se cortan (antes se perdían sin aviso).
- ✅ **Elegir por color**: fichas en Cortes + clic derecho.
- ✅ **Placa del trabajo** en Material, con aviso «Se sale de la placa».
- ✅ **Cortes desde capas** (`cajeado_6` → cajeado de 6 mm), propuestos con un botón.
  Supuesto MÍO, sin confirmar con Jose: el número de la capa es la PROFUNDIDAD (no la fresa).
- ✅ **Textos de DXF y AI/PDF → notas** también (mismo día, pedido aparte).
- Detalle técnico en `.claude/rules/interfaz-web.md` ("Notas, capas…").
- Trampa propia: `python3 auditar_gcode.py` con el Python del SISTEMA falla por falta de shapely
  (parece un error del código); se corre con `/opt/homebrew/bin/python3`.

## ⏳ Pendiente
- **Mosaico** (EN MARCHA, 24-nov-2026): el MOTOR ya está escrito, en `geo_ops.mosaic_op` (cola de
  milano / rompecabezas / recta; cuadrícula igual; uniones alternadas y solo ENTERAS dentro de la
  pieza; esquinas redondeadas a fresa+0.1 salvo en los cruces; holgura). Medido: tramos sin
  encimarse, holgura exacta, la fresa sigue la forma a 0.017 mm. **Sin subir y sin pantalla.**
  Opciones de pantalla publicadas para Jose: https://claude.ai/artifact/SAoBB7awvBJg2wecJagkUL
  (recomendé A+A: sección «Mosaico» en el panel de Diseño + tramos separados con etiqueta-nota).
  El solape (media madera) quedó FUERA: exige voltear la placa.
- **Calibración por pantalla** (idea, Jose: «déjalo como idea»): hoy `ds_zcal` es UNO por
  navegador; con monitor externo o cambiando la resolución de la Mac el 100 % queda mal. Guardar uno
  por pantalla (llave = tamaño en píxeles) y avisar «esta pantalla no está calibrada».
