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

## ⏳ Pendiente (confirmado que NO existe; nada de esto está hecho)
- **Mosaico**: partir una pieza más grande que la hoja, con cola de milano o solape (Aspire lo
  tiene). El más grande; proyecto aparte.
- **Textos del SVG**: el lector los DESCARTA sin avisar (entraron 23 figuras y 0 textos). Pidió que
  entren como notas que no se cortan.
- **Tamaño de la hoja por trabajo** (1220×550) que avise si algo se sale; hoy solo existe la cama
  de la máquina, y se guarda para siempre.
- **Seleccionar todo lo del mismo color** (asignó 17 barrenos con 17 clics).
- **Asignar operación por capa o color al importar** (capa `cajeado_6` → cajeado de 6 mm); hoy el
  nombre de la capa no se conserva al abrir.
- **Calibración por pantalla** (idea, Jose: «déjalo como idea»): hoy `ds_zcal` es UNO por
  navegador; con monitor externo o cambiando la resolución de la Mac el 100 % queda mal. Guardar uno
  por pantalla (llave = tamaño en píxeles) y avisar «esta pantalla no está calibrada».
