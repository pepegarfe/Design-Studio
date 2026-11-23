---
name: tablet-fire-instalar-pwa
description: "Por qué la Estación no se \"instalaba\" en la tablet Amazon Fire (KFRAWI) — no era el sitio: Play Store y servicios de Google apagados y cuenta de Google sin sesión; el acceso directo iba a un escritorio invisible."
metadata:
  node_type: memory
  type: project
  originSessionId: 130b077a-6888-4299-a7dd-79d63c3281cb
  modified: 2026-11-23T18:40:58.469Z
---

**Diagnóstico del 23-nov-2026** (tablet Amazon Fire HD, modelo KFRAWI, Fire OS 8.3, Chrome 150
instalado aparte con Play Store). Contexto: [[sin-escritorio-pwa]].

**El sitio estaba bien**: con la tablet por USB y la depuración de Chrome
(`adb forward tcp:9333 localabstract:chrome_devtools_remote`), `Page.getInstallabilityErrors`
devolvió **cero errores** y el manifiesto de `/estacion` con sus íconos se leyó completo.

Lo que fallaba, por capas:
1. **Play Store (`com.android.vending`) y Servicios de Google (`com.google.android.gms`) estaban
   DESACTIVADOS** (`enabled=3`, "por el usuario"). Chrome necesita la Play Store para instalar
   una app web de verdad (WebAPK); el registro decía `BIND_PLAY_INSTALL_SERVICE ... not found`.
   Reactivados con `adb shell pm enable ...` (Jose aprobó).
2. Sin la Play Store, Chrome cae a un **acceso directo**, y ese acceso se guarda en
   **`com.android.launcher3`**, un lanzador escondido; el escritorio visible es el de Amazon
   (`com.amazon.firelauncher`), que **solo muestra apps instaladas**. Resultado: "instalo y no
   aparece nada", sin error. Ya había uno de estos fantasmas del 11-nov (cuando Jose intentó).
3. Con todo activado, la **cuenta de Google de la tablet perdió la sesión** (`BadAuthentication`,
   "User needs to (re)enter credentials"): la Play Store no instala nada hasta que Jose vuelva a
   escribir su contraseña EN la tablet. En la Play Store se quedaba en bucle "Reintentar" (ese
   botón NO abre la pantalla de contraseña). Hay DOS cuentas de Google en la tablet (la de
   antike.mx y la de Gmail): Jose cambió de cuenta en el círculo de la Play Store y con eso bastó.
4. ✅ **Instalada el 23-nov-2026** como WebAPK `org.chromium.webapk.a0214c21a919c811b_v2`: sale en
   el escritorio de Amazon como "Estación" y abre a pantalla completa con la cuenta pepegarfe.
   (La otra cuenta de Google sigue sin sesión; no estorba.)
5. ⚠️ **Play Store y Servicios de Google se apagaron A PROPÓSITO el 10-nov** (proyecto
   `~/servidor-tablet`, `ajustes-cambiados.md`): fallaban en bucle a 136 % de CPU y la tablet
   corre el recolector de Maps y los vigías de precios. Yo los encendí sin leer esa nota — error.
   Tras instalar se **volvieron a apagar** (23-nov): la RAM libre subió de ~487 a ~575 MB y la
   Estación **sigue abriendo** como app. Para reinstalarla o cambiarle nombre/ícono hay que
   encenderlos otra vez un rato y apagarlos al terminar.

**Regla:** antes de cambiar el estado de la tablet, leer `~/servidor-tablet/ajustes-cambiados.md`.

**Why:** en la Fire, "Agregar a la pantalla principal" parece éxito pero no deja nada visible.
**How to apply:** si una PWA "no se instala" en una Fire, la prueba es `adb shell pm list packages
| grep webapk` — si no aparece un `org.chromium.webapk.*` nuevo, fue acceso directo, no
instalación. Checador y Omniseller sí están como WebAPK (jul/ago-2026, cuando la Play Store
funcionaba).
