// Prueba el <script id="motor"> REAL de web/prueba_webusb.html contra un chip FTDI simulado,
// y compara byte a byte el cuadrado con lo que manda el escritorio (web/bytes_escritorio.py).
//
// Uso: node web/test_webusb.mjs
// Lo que NO prueba: que un teléfono Android de verdad suelte el chip a Chrome. Eso solo se
// sabe con el teléfono y el plotter.
import fs from 'fs';
import vm from 'vm';
import path from 'path';
import { execFileSync } from 'child_process';
import { fileURLToPath } from 'url';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const PY = fs.existsSync('/opt/homebrew/bin/python3') ? '/opt/homebrew/bin/python3' : 'python3';
const html = fs.readFileSync(path.join(AQUI, 'prueba_webusb.html'), 'utf8');
const src = html.match(/<script id="motor">([\s\S]*?)<\/script>/)[1];
const ctx = { TextEncoder, setTimeout, Date, Promise, Uint8Array, Error, Math };
vm.createContext(ctx);
vm.runInContext(src + '\n;globalThis.M={hpglCuadrado,hpglAire,bytesAbortar,ftdiBaud,pasosFtdi,' +
                'abrirFtdi,enviar,diagnosticoSoporte,FTDI_VID};', ctx);
const M = ctx.M;
const esc = JSON.parse(execFileSync(PY, [path.join(AQUI, 'bytes_escritorio.py')], { encoding: 'utf8' }));

let fallos = 0;
const ok = (c, msg, extra = '') => {
  console.log((c ? 'OK   ' : 'FALLA') + ' ' + msg + (c || !extra ? '' : '  — ' + extra));
  if (!c) fallos++;
};
const texto = bytes => Buffer.from(bytes).toString('latin1');

// Chip FTDI de mentira con la forma de un USBDevice de Chrome. Anota cada mensaje de control y
// cada byte. `lento` simula el cable a 9600 (~1 ms por byte); las opciones rompen cosas a propósito.
function chipFalso({ tomado = false, sinSalida = false, rechaza = null, cortaEnvio = null,
                     lento = false, sinConfig = true } = {}) {
  const c = { control: [], datos: [], abierto: false, reclamado: false, envios: 0, maxPaquete: 0 };
  const intf = { interfaceNumber: 0, alternate: { endpoints: sinSalida
    ? [{ endpointNumber: 1, direction: 'in', type: 'bulk' }]
    : [{ endpointNumber: 1, direction: 'in', type: 'bulk' },
       { endpointNumber: 2, direction: 'out', type: 'bulk' }] } };
  const config = { interfaces: [intf] };
  c.dev = {
    vendorId: 0x0403, productId: 0x6001, productName: 'FT232R USB UART',
    configuration: sinConfig ? null : config,
    async open() { c.abierto = true; },
    async selectConfiguration(n) { if (n === 1) this.configuration = config; },
    async claimInterface(n) {
      if (tomado) { const e = new Error('Unable to claim interface.'); e.name = 'NetworkError'; throw e; }
      c.reclamado = n === 0;
    },
    async controlTransferOut(s) {
      c.control.push(s);
      return { status: rechaza === s.request ? 'stall' : 'ok' };
    },
    async transferOut(ep, datos) {
      if (!c.reclamado) throw new Error('mandó datos sin reclamar el chip');
      c.envios++;
      if (cortaEnvio !== null && c.envios > cortaEnvio) {
        const e = new Error('The device was disconnected.'); e.name = 'NotFoundError'; throw e;
      }
      if (lento) await new Promise(r => setTimeout(r, datos.length));
      c.maxPaquete = Math.max(c.maxPaquete, datos.length);
      c.datos.push(...datos);
      return { status: ep === 2 ? 'ok' : 'stall', bytesWritten: datos.length };
    },
    async close() { c.abierto = false; },
  };
  return c;
}

const lineas = arr => arr.map(l => l + '\n').join('');

// 1 · Velocidades: los valores que publican libftdi / FTDI (AN232B-05).
const tabla = [[9600, 0x4138, 0], [19200, 0x809c, 0], [38400, 0xc04e, 0], [57600, 0xc034, 0],
               [115200, 0x001a, 0], [300, 0x2710, 0], [3000000, 0, 0]];
for (const [baud, v, i] of tabla) {
  const r = M.ftdiBaud(baud);
  ok(r.value === v && r.index === i, `velocidad ${baud} → divisor 0x${v.toString(16)}`,
     `salió 0x${r.value.toString(16)} / ${r.index}`);
}

// 2 · Abrir: configuración, reclamar, y los 5 mensajes al chip en orden y bien dirigidos.
{
  const c = chipFalso();
  const w = await M.abrirFtdi(c.dev, 9600);
  ok(c.abierto && c.reclamado && c.dev.configuration !== null, 'abre, elige configuración y reclama el chip');
  const esperado = [[0, 0, 1], [1, 0x0303, 1], [2, 0, 1], [4, 0x0008, 1], [3, 0x4138, 0]];
  const real = c.control.map(s => [s.request, s.value, s.index]);
  ok(JSON.stringify(real) === JSON.stringify(esperado), 'mensajes al chip: reiniciar, DTR/RTS, sin flujo, 8N1, 9600',
     JSON.stringify(real));
  ok(c.control.every(s => s.requestType === 'vendor' && s.recipient === 'device'),
     'todos van como mensajes del fabricante al aparato');
  ok(typeof w === 'function', 'devuelve con qué escribir');
}

// 3 · Lo que llega al plotter: byte a byte igual que el escritorio.
{
  const c = chipFalso();
  const w = await M.abrirFtdi(c.dev, 9600);
  await w(new TextEncoder().encode('IN;\n'));
  ok(texto(c.datos) === esc.conectar, 'al conectar manda lo mismo que el escritorio (IN;)');
  c.datos.length = 0;
  const r = await M.enviar(w, M.hpglCuadrado(10, 200, 140), { detener: false }, { pausaMs: 0 });
  ok(r.completo && texto(c.datos) === esc.test_corte, 'cuadrado de prueba = "Corte de prueba" del escritorio, byte a byte',
     JSON.stringify(texto(c.datos)));
  c.datos.length = 0;
  await M.enviar(w, M.hpglAire(), { detener: false }, { pausaMs: 0 });
  ok(texto(c.datos) === 'PU;\nPR400,0;\nPR0,400;\nPR-400,0;\nPR0,-400;\n',
     'mover en el aire: cuchilla arriba y cuadrito de 1 cm que vuelve al inicio');
  ok(!/PD/.test(texto(c.datos)), 'mover en el aire NUNCA baja la cuchilla');
}

// 4 · Diseño largo: se parte en paquetes de 64 y no se pierde ni un byte, aunque el cable sea lento.
{
  const c = chipFalso({ lento: true });
  const w = await M.abrirFtdi(c.dev, 9600);
  const largo = new TextEncoder().encode(esc.enviar.repeat(3));
  await w(largo);
  ok(texto(c.datos) === esc.enviar.repeat(3), `envío de ${largo.length} bytes llega completo con el cable lento`);
  ok(c.maxPaquete <= 64, 'ningún paquete pasa de 64 bytes', 'máximo ' + c.maxPaquete);
}

// 5 · Detener a medias: para de enviar.
{
  const c = chipFalso();
  const w = await M.abrirFtdi(c.dev, 9600);
  const st = { detener: false };
  const r = await M.enviar(w, M.hpglCuadrado(10, 200, 140), st,
                           { pausaMs: 0, progreso: i => { if (i === 3) st.detener = true; } });
  ok(!r.completo && r.enviadas === 3, 'Detener corta el envío en la línea donde se pidió');
  await w(M.bytesAbortar());
  ok(texto(c.datos).endsWith(esc.cancelar), 'y manda el mismo paro que el escritorio (ESC + IN;)');
}

// 6 · Lo que falla tiene que DECIR qué falló (en el teléfono no podemos mirar).
{
  let e = null;
  try { await M.abrirFtdi(chipFalso({ tomado: true }).dev, 9600); } catch (x) { e = x; }
  ok(e && e.reclamar && /no suelta el cable/.test(e.message),
     'si el sistema tiene tomado el chip (Mac/Windows), lo dice así', e && e.message);
  e = null;
  try { await M.abrirFtdi(chipFalso({ rechaza: 3 }).dev, 9600); } catch (x) { e = x; }
  ok(e && /velocidad 9600/.test(e.message), 'si el chip rechaza la velocidad, nombra ese paso', e && e.message);
  e = null;
  try { await M.abrirFtdi(chipFalso({ sinSalida: true }).dev, 9600); } catch (x) { e = x; }
  ok(e && /canal de salida/.test(e.message), 'un aparato sin canal de salida no "conecta" en falso');
  e = null;
  const c = chipFalso({ cortaEnvio: 4 });
  const w = await M.abrirFtdi(c.dev, 9600);
  try { await M.enviar(w, M.hpglCuadrado(10, 200, 140), { detener: false }, { pausaMs: 0 }); } catch (x) { e = x; }
  ok(e !== null, 'cable arrancado a media corte: error visible, no "enviado"');
  const c2 = chipFalso({ sinConfig: false });
  await M.abrirFtdi(c2.dev, 9600);
  ok(c2.reclamado, 'funciona también si el aparato ya traía la configuración elegida');
}

// 7 · Qué le dice la página a cada navegador.
{
  const d1 = M.diagnosticoSoporte({ usb: undefined, userAgent: 'Android Chrome' }, false, 'http://192.168.68.109:8000');
  ok(d1 && d1.flags && d1.url === 'http://192.168.68.109:8000', 'Chrome por http en el WiFi → instrucciones de chrome://flags con su dirección');
  const d2 = M.diagnosticoSoporte({ usb: undefined, userAgent: 'iPhone Safari' }, true, '');
  ok(d2 && /iPhone/.test(d2.tit), 'iPhone → dice que ahí no se puede');
  const d3 = M.diagnosticoSoporte({ usb: undefined, userAgent: 'SamsungBrowser Android' }, true, '');
  ok(d3 && /Samsung Internet/.test(d3.txt), 'navegador sin WebUSB → manda a Chrome');
  ok(M.diagnosticoSoporte({ usb: {}, userAgent: '' }, true, '') === null, 'Chrome con WebUSB → sin aviso');
}

// 8 · El filtro de la ventanita solo deja ver chips FTDI.
ok(M.FTDI_VID === 0x0403 && /filters: \[\{ vendorId: FTDI_VID \}\]/.test(html), 'la lista de Chrome solo muestra chips FTDI');

console.log(fallos ? `\n${fallos} FALLA(S)` : '\nTodo OK');
process.exit(fallos ? 1 : 0);
