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

## 26-nov-2026: proyecto de cortes de prueba en la cuenta de Jose
«Prueba de parametros MDF 6mm 2F» en Mis proyectos (id `p2bbfdaeccffb`): 6 probetas de flor
ondulada (Ø ~73 mm) con hueco cuadrado de 30 mm, perfil por fuera a 12.2 mm en 3 pasadas, 3
puentes, rampa suave 10°, bajada 381. Archivo 1 = S4 con F1270 / 1800 / 2400; archivo 2 = S2 con
F1800 / 2400 / 3000 (apagado: casillas). Marcas taladradas de 2 mm (1-3 agujeros; arriba del
hueco en el archivo 1, abajo en el 2) PRIMERO en cada archivo. Verificado: el .tap del servidor en
vivo = el de la interfaz local = el revisado (huella idéntica), fondo completo, puentes a 3 mm.
Generador: scratchpad (se pierde); si hay que rehacerlo, la receta es esta nota.
⏳ Falta que Jose lo corte y diga cuál quedó mejor → ajustar la fresa en «Fresas…».
Lección: Chrome nuevo pide permiso de «red local» y una petición de una página https a
127.0.0.1 se queda colgada sin aviso; para pasar un archivo grande a una pestaña, crear un
`<input type=file>` en ella y usar la herramienta de subir archivo.
Mismo día (26-nov): Jose pidió cortar todo en UN archivo → el generador ahora cambia de marcha
entre cortes (ver `.claude/rules/cnc.md`). ⏳ La primera vez que lo corra: escuchar si el husillo
cambia de sonido al pasar a las probetas 4-6. Las notas del proyecto de prueba todavía dicen
«un grupo por archivo» (se escribieron antes): basta con encender las casillas del grupo S2.

## 26-nov-2026: MATRIZ giro × avance (la prueba de verdad)
Jose pidió una prueba que mida las dos variables. Proyecto «Matriz giro x avance MDF 6mm 2F» en
su cuenta (id `p0f7f7488a6d4`): 4 filas (S8/S6/S4/S2) × 4 avances (1270/1800/2400/3000) = 16
ranuras a 4 mm en UNA pasada, perfil «sobre la línea», sin rampa ni puentes. Cada ranura: 120 mm
recto + media vuelta + 120 mm ondulado (±3 mm, onda de 15 mm); 303.5 mm en total. Se cortan en
orden salteado (S6, S2, S8, S4) y al final se REPITE S6·F1270 para ver si el calor de la fresa
cambió algo. UN archivo con 4 cambios de marcha (≈4 min) — de paso prueba si el A11E obedece el
cambio a medio archivo. Placa de ~60 × 28 cm. Verificado: tap del servidor en vivo = interfaz
local = revisado (sha 6cc105bfe16bdf26), todo a −4, cada ranura a su avance.
Qué mide Jose por casilla: viruta o polvo, color de la pared, rebaba, sonido, y video para sacar
el avance REAL en el tramo ondulado (tiempo esperado a avance programado: F1270 14.3 s, F1800
10.1 s, F2400 7.6 s, F3000 6.1 s por ranura, sin contar bajada). No tiene calibrador claro.
Etapas siguientes: (2) las 2-3 mejores como pieza real (proyecto «Prueba de parametros…», que
quedó de antes con 6 combinaciones); (3) profundidad por pasada 2.5/4/6.

### Misma noche: prueba en el AIRE + columna F3600 (pedido de Jose)
- La matriz se REEMPLAZÓ (mismo id `p0f7f7488a6d4`): ahora 5 avances (…, 3600) = 20 ranuras + la
  repetición, 73 × 27 cm, ≈4 min, sha defeb9a1d9ba02eb.
- NUEVO «Prueba en el AIRE avances y marchas» (id `p207c0e2570de`): un recto de 900 mm y un
  ondulado de 900 mm (recorrido real 1187.7 mm), cada uno a F1270/1800/2400/3000/3600 = 10
  recorridos; cada avance con otra marcha (S6, S2, S8, S4, S6) para OÍR los 4 cambios. Baja solo
  1 mm: se corre SIN material y con el cero de Z fijado ~30 mm arriba de la mesa. Sha 853faf7f5f0d6583.
  Tiempos si alcanzara el avance (recto / ondulado, s): 1270 → 42.5 / 56.1 · 1800 → 30.0 / 39.6 ·
  2400 → 22.5 / 29.7 · 3000 → 18.0 / 23.8 · 3600 → 15.0 / 19.8. Avance real = largo ÷ tiempo medido.
- Orden acordado: PRIMERO el aire (¿obedece el cambio de marcha? ¿a cuánto va de verdad en
  curvas?), luego la matriz (quizá con menos columnas según lo que salga).
