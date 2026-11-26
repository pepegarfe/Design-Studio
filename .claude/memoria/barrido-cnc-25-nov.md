---
name: barrido-cnc-25-nov
description: "25-nov-2026: barrido automático de 3341 combinaciones de corte CNC (barrido_cnc.py) tras el reporte de la rampa sin terminar; 4 errores encontrados y arreglados, 1 menor y 1 sospecha de DXF pendientes"
metadata:
  node_type: memory
  type: project
  originSessionId: 63cead03-81d7-4118-88e7-6e9e343252a1
  modified: 2026-11-25T19:40:56.473Z
---

# Barrido de combinaciones CNC (25-nov-2026)

Jose reportó que las entradas en rampa «no terminan» (`gato-2 doble.tap`: las líneas abiertas
quedaban con una cuña de 5.3 a 8 mm en sus primeros 25 mm). Después pidió buscar «otros errores
similares». En vez de leer el código a ojo se escribió `barrido_cnc.py`: genera miles de
combinaciones (forma × operación × lado × rampa × puentes × acabado × inicio × profundidad × cero)
y MIDE en el G-code, punto por punto, si la fresa llegó a donde debía.

## Encontrado y arreglado (detalle técnico en `.claude/rules/cnc.md`)
1. **Rampa de trayecto abierto** (líneas y cadenas del cajeado): la última pasada dejaba la cuña
   y cada intermedia bajaba en vertical en material sin cortar. Ahora CADA pasada regresa a fondo
   sobre su rampa. ⚠️ Primero dije que las intermedias no lo necesitaban: era cierto para la
   cuña, no para la picada; el barrido lo delató (690 casos).
2. **Espiral + acabado**: el anillo de acabado no daba su vuelta plana → pared en tornillo y casi
   todo el espesor sin cortar tras el arranque (117 casos). El más grave: la pieza no se suelta.
3. **Zigzag que cruza un puente** le comía hasta 0.9 mm de altura.
4. **Derecha/Izquierda en figura cerrada** salía como línea abierta (shapely `offset_curve`).

Verificado: auditoría 179/179 (las 5 pruebas nuevas FALLAN con el código viejo), servidor
232/232, y en 1728 combinaciones el G-code es idéntico al de antes salvo en los casos corregidos.
⏳ Ninguno cortado en la máquina real todavía.

## Pendiente
- MENOR: con puentes, una pasada que arranca sobre la subida de un puente baja en vertical
  ≤ 0.38 mm (49/3341). No se tocó.
- SOSPECHA, sin archivo real: ezdxf aplana mal una SPLINE cerrada PERIÓDICA (manda puntos a
  cientos de mm). Hecha a mano con `closed_uniform_bspline`; no se sabe si Corel/AutoCAD las
  guardan así. Pedirle a Jose un DXF real con curvas cerradas antes de arreglar.
- El barrido NO cubre: taladro, varias trayectorias en un archivo, mosaico, plotter (este último
  se revisó aparte: SVG y DXF cierran bien sus figuras).

Relacionado: [[rebaba-microsegmentos]] (la rampa a avance de picada), [[cnc-richauto]].

## Mismo día: el humo del `gato-2 doble.tap` (Jose bajó a S4)
Medido en el archivo: el 28 % del tiempo de corte era RAMPA a F381 (viruta 0.012 mm/filo a
16000 RPM: raspa). Causa: `_emit_cut` mandaba toda rampa al avance de picada. Arreglado: se
limita solo la velocidad VERTICAL a la picada (las rampas de ~10° van ya a F1270). Recorrido
idéntico; solo cambian las F de las bajadas. ~5 min menos en ese trabajo.
Queda de fondo: aun a F1270 la viruta es 0.040 mm/filo (bajo; MDF quiere 0.10–0.25), y la
tabla de marchas S2–S8 = 12000–18000 sigue SIN medir (ver [[cnc-richauto]]). Preguntado a Jose:
qué marcha usaba con Aspire (entonces la máquina ignoraba la S del archivo), qué marca el
variador en S4 y S6, y si el humo salía al entrar o en todo el recorrido.
✅ Respuesta de Jose (25-nov-2026): el variador marca S4=14000, S6=16000 (escribió "1600"),
S8=18000 → la tabla de marchas de la app es CORRECTA; el giro no era el problema. Lo que
humeaba era la viruta delgada (sobre todo las rampas a F381). Faltan: qué marcha usaba con
Aspire y dónde salía el humo.
