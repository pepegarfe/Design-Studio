---
name: sin-escritorio-pwa
description: 11-nov-2026 Jose eliminó la app de escritorio; Design Studio queda solo web, instalable como dos PWA (editor y estación) que se actualizan solas
metadata:
  type: project
---

El **11-nov-2026** Jose pidió **eliminar la app de escritorio** y dejar Design Studio solo como
sitio web instalable en **dos PWA**: el editor (`/`) y la estación de corte (`/estacion`), cada una
con su logo, y que se actualicen solas.

**Why:** el sitio ya estaba en Railway y era la versión que se mantenía; el escritorio obligaba a
compilar, firmar e instalar por separado (y la PC del taller llevaba meses sin actualizar). Es una
decisión de Jose, no una deducción técnica.

**How to apply:**
- No proponer arreglos "para el escritorio" ni releases de GitHub: ya no existen `design_studio.py`,
  `updater.py`, el instalador ni la CI. Lo que sigue vivo y por qué está en CLAUDE.md ("Qué es").
- La **PC del taller** ahora necesita internet y Chrome/Edge para usar la app (antes trabajaba sin
  red). ⏳ Pendiente de Jose: instalar la PWA allá y retirar la app vieja.
- Las reglas de las PWA (recursos públicos, sin service worker, `BUILD`) viven en CLAUDE.md,
  sección "Distribución". La historia del escritorio queda en [[design-studio]] como archivo.
- Quedaron sin borrar, a propósito, carpetas locales fuera de git: `dist/`, `build/`, `studio.ico`,
  `studio.icns`, `arranque.log` (no se recuperan si se borran; Jose decide).
