---
name: interfaz-y-corte-12-nov
description: "La sesión larga del 12-nov-2026 — rediseño de la interfaz web (Diseño → Corte, tres pasos de la CNC, teléfono), funciones nuevas (puentes a mano, cajeado con acabado, color y corte por color, descarte, PDF, Mis proyectos, alivio de esquinas), lo que Jose rechazó y lo que quedó pendiente"
metadata:
  node_type: memory
  type: project
  originSessionId: 7c7f36ce-19d2-4a33-afda-0d07dab90adc
  modified: 2026-11-13T01:02:00.956Z
---

# Interfaz y Corte: lo que se hizo el 12-nov-2026

Una sola sesión, ~30 commits, todo en línea al terminar (último: `5d0dd74`). Las **reglas** de cada
cosa viven en `CLAUDE.md` (secciones "Reglas visuales", "Diseño → Corte", "Color, descarte, alivios
y Mis proyectos" y las de CNC). Aquí va la **historia y el porqué**, que el código no cuenta.

## Cómo se decidió
Jose pidió analizar los cuatro menús contra la industria. El método que funcionó, y que conviene
repetir: **capturas reales de la app → propuestas dibujadas a tamaño real en una página → Jose
elige → se programa por etapas, cada una probada → se sube**. Ver [[preferencias-interfaz-jose]]
(qué le gusta y qué rechazó) y [[como-verificar-la-interfaz]] (cómo se prueba sin su Chrome).

## Qué quedó (en orden)
1. **Limpieza visual**: encuadre al diseño al abrir, magenta solo para el siguiente paso,
   interruptores con nombre, avisos arriba, botón "v dev" fuera (la huella `BUILD` va en el menú
   de cuenta).
2. **Diseño | Corte en las dos máquinas**; la ventana "Plotter" pasó al panel; menú Archivo;
   Organizar; botón Imagen.
3. **Corte de la CNC**, tres vueltas hasta que le gustó: primero estilo Aspire (lista ↔
   formulario), luego la propuesta "D" (pasos, color por corte, Revisar como paso), y al final
   **tres pasos en una barra: Material · Cortes · Revisar**. El formulario terminó **fijo y
   reordenado**, sin "Más opciones".
4. **Generador**: puentes a mano, cajeado con pasada de acabado + primer anillo lento + rampa de
   inicio, un archivo por fresa, aviso de orden peligroso, y el arreglo de rendimiento
   (`_point_at` binario + memoria de recorridos + vista 3D que no muestra lo anterior).
5. **Teléfono**: barra superior en iconos, deshacer/rehacer sobre el lienzo, un renglón abajo.
6. **Tipografías**: el selector pinta cada nombre con su letra también en la web (muestras de 2 KB).
7. **Paquete "nivel profesional" 1–3**: color por figura y corte por color, descarte, PDF,
   Mis proyectos (con miniatura) y alivio de esquinas.

## Errores míos que conviene recordar
- **Rompí el editor en producción ~7 min** (`1a90baa` → `2149b96`): metí un comentario `//` a media
  línea que seguía con código. Lo hice DESPUÉS de las pruebas y la prueba que corrió junto al push
  no imprimió nada. Desde entonces: sintaxis de los dos `<script>` antes de subir y de la página
  EN VIVO después.
- **Dos veces di por buena una prueba que no había probado nada** (comparó dos archivos vacíos; no
  bajó archivo). Eran mis guiones, desactualizados por un cambio mío.
- **Le recomendé la "pasada final delgada"** de Aspire sin ver que contradice su propia regla
  medida de `_passes()`. Lo detecté al ir a programarla y no la hice.
- **Los cajeados nacieron con rampa** y eso destapó una búsqueda cuadrática vieja: calcular pasó a
  tardar segundos en Railway. Jose lo notó antes que yo.

## Pendiente (nada de esto está hecho)
- **Ningún corte real** con lo nuevo: puentes a mano, cajeado con acabado, alivio de esquinas,
  vinil por colores. Lo primero, en un retazo.
- **Teléfono real**: todo lo de móvil se probó simulado.
- **EPS y CDR**: faltan programas del sistema (Ghostscript, libcdr) que no hay en la Mac, y un
  `.cdr` de muestra. Pedírselo a Jose y probar directo en Railway.
- **Texto de un solo trazo** para grabar (falta la tabla de una fuente Hershey con acentos y ñ).
- **Exportar con color** (PNG/PDF/SVG salen sin los colores) — es la "prueba a color para el cliente".
- De la lista de funciones: mosaico, imprimir-y-cortar (¿tiene sensor su plotter?), V-carve,
  incrustaciones, cotas, órdenes de trabajo y control de retazos.
- Decisiones de Jose abiertas: ajustes por material en el plotter; el aviso de "sin puentes" que
  se fue al quitar la lista de la máquina en Revisar.
- **Railway reinicia con cada nota**: la sincronización de Obsidian sube sola los cambios de
  `CLAUDE.md` y de esta carpeta ("Notas: cambios desde Obsidian") y cada subida tumba el sitio ~30 s.
  Ofrecido configurar "Watch Paths"; sin respuesta.
- **`CLAUDE.md` pasa de 400 líneas** contra la regla de <200 de Jose. Ofrecido moverlo a
  `.claude/rules/`; sin respuesta.
