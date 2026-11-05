// La ESTACIÓN DE CORTE (estacion.html) con su lógica REAL y el motor REAL de la app, contra un
// chip FTDI simulado (Android/WebUSB) y una fila de mentira con las reglas de estacion.py.
// Lo que llega "al plotter" se compara byte a byte con el escritorio (web/bytes_escritorio.py).
// Las reglas de la fila en el servidor de verdad las prueba web/auditar_servidor.py (sección K).
//
// Uso: node web/test_estacion.mjs
import fs from 'fs';
import vm from 'vm';
import path from 'path';
import { execFileSync } from 'child_process';
import { fileURLToPath } from 'url';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const app = fs.readFileSync(path.join(AQUI, '..', 'studio_ui.html'), 'utf8');
const est = fs.readFileSync(path.join(AQUI, '..', 'estacion.html'), 'utf8');
const PY = fs.existsSync('/opt/homebrew/bin/python3') ? '/opt/homebrew/bin/python3' : 'python3';
const esc = JSON.parse(execFileSync(PY, [path.join(AQUI, 'bytes_escritorio.py')], { encoding: 'utf8' }));

let fallos = 0;
const ok = (c, msg, extra = '') => { console.log((c ? 'OK    ' : 'FALLA ') + msg + (!c && extra ? '  — ' + extra : '')); if (!c) fallos++; };
const dormir = ms => new Promise(r => setTimeout(r, ms));
const txt = b => Buffer.from(b).toString('latin1');

const motor = app.match(/<script id="motor-plotter">([\s\S]*?)<\/script>/)[1];
const logica = est.match(/<script id="estacion-logica">([\s\S]*?)<\/script>/)[1];
ok(est.includes('<!--MOTOR-PLOTTER-->') && !/var PlotterMotor/.test(est),
   'estacion.html NO trae una copia propia del motor: el servidor le mete el de la app');

function chipUsb({ vendor = 0x0403, lento = 0 } = {}) {
  const c = { control: [], llegado: [], abierto: false };
  const intf = { interfaceNumber: 0, alternate: { endpoints: [
    { endpointNumber: 1, direction: 'in', type: 'bulk' }, { endpointNumber: 2, direction: 'out', type: 'bulk' }] } };
  c.dev = {
    vendorId: vendor, productId: 0x6001, configuration: null,
    async open() { c.abierto = true; },
    async selectConfiguration() { this.configuration = { interfaces: [intf] }; },
    async claimInterface() {},
    async controlTransferOut(s) { c.control.push([s.request, s.value, s.index]); return { status: 'ok' }; },
    async transferOut(ep, d) { if (!c.abierto) throw Object.assign(new Error('desconectado'), { name: 'NotFoundError' });
      await dormir(lento); c.llegado.push(...d); return { status: 'ok' }; },
    async close() { c.abierto = false; },
  };
  return c;
}

// Una fila de mentira con las mismas reglas que estacion.py (tomar solo si está pendiente, etc.)
function servidorFalso(trabajos = []) {
  const s = { trabajos: trabajos.map(t => ({ estado: 'pendiente', creado: 1, actualizado: 1, ...t })), llamadas: [], caido: false, terminarFalla: false };
  s.pedir = async (url, body) => {
    s.llamadas.push([url, body]);
    if (s.caido) throw new Error('sin red');
    const t = body && s.trabajos.find(x => x.id === body.id);
    if (url === '/api/estacion/fila') return { ok: true, trabajos: s.trabajos.map(({ hpgl, ...x }) => x), ahora: 100 };
    if (url === '/api/estacion/tomar') {
      if (!t || t.estado !== 'pendiente') return { ok: false, error: 'Ese trabajo no está esperando' };
      t.estado = 'cortando'; return { ok: true, hpgl: t.hpgl, trabajo: { id: t.id, nombre: t.nombre } };
    }
    if (url === '/api/estacion/terminar') {
      if (s.terminarFalla) throw new Error('sin red');
      t.estado = body.resultado; t.detalle = body.detalle; return { ok: true };
    }
    if (url === '/api/estacion/quitar') { s.trabajos = s.trabajos.filter(x => x !== t); return { ok: true }; }
    return { ok: false, error: 'ruta desconocida ' + url };
  };
  return s;
}

function montar({ permitidos = [], elegido = null, android = true, conUsb = true, srv = servidorFalso() } = {}) {
  const avisos = [], escuchas = {}, pedidos = [], pinturas = [];
  const usb = {
    getDevices: async () => permitidos.map(c => c.dev),
    requestDevice: async op => { pedidos.push(op); if (!elegido) throw Object.assign(new Error('nada'), { name: 'NotFoundError' });
                                 if (!permitidos.includes(elegido)) permitidos.push(elegido); return elegido.dev; },
    addEventListener: (n, f) => { escuchas[n] = f; },
  };
  const serialPc = { getPorts: async () => [], requestPort: async () => { throw Object.assign(new Error('nada'), { name: 'NotFoundError' }); },
                     addEventListener: () => {} };
  const nav = android ? { userAgent: 'Mozilla/5.0 (Linux; Android 9; SM-J600G) Chrome/142', ...(conUsb ? { usb } : {}), serial: {} }
                      : { userAgent: 'Mozilla/5.0 (Macintosh) Chrome/142', usb, serial: serialPc };
  const ctx = { TextEncoder, setTimeout, Date, Promise, Uint8Array, Array, Error, String, Math, Map, parseInt };
  vm.createContext(ctx);
  vm.runInContext(motor + '\n' + logica + '\n;globalThis.PM = PlotterMotor;', ctx);
  const E = ctx.crearEstacion({ M: ctx.PM, nav, pedir: srv.pedir, avisar: n => avisos.push(n.map(t => t.id)),
                                render: e => pinturas.push(JSON.parse(JSON.stringify(e))), baud: 9600 });
  return { E, srv, avisos, escuchas, pedidos, pinturas, ctx };
}

// 1 · Llega un trabajo: avisa UNA vez, no corta solo
{
  const chip = chipUsb();
  const srv = servidorFalso([{ id: 'aaaaaaaaaaaa', nombre: 'Letrero', hpgl: esc.hpgl }]);
  const { E, avisos } = montar({ permitidos: [chip], srv });
  ok(E.estado.soporte && E.estado.usb, 'Android: la estación usa el cable por WebUSB');
  await E.auto();
  ok(E.estado.conectado && chip.abierto, 'al abrir, con el cable ya permitido, se conecta sola');
  chip.llegado.length = 0;
  await E.revisar(); await E.revisar();
  ok(avisos.length === 1 && avisos[0][0] === 'aaaaaaaaaaaa', 'un trabajo nuevo avisa (vibra/suena) una sola vez, aunque se revise dos veces');
  await dormir(20);
  ok(chip.llegado.length === 0 && srv.trabajos[0].estado === 'pendiente', 'y NO corta solo: espera el toque de "Cortar"');
}

// 2 · Cortar: los mismos bytes que el escritorio, y el servidor queda enterado
{
  const chip = chipUsb();
  const srv = servidorFalso([{ id: 'bbbbbbbbbbbb', nombre: 'Logo', hpgl: esc.hpgl }]);
  const { E, pedidos } = montar({ elegido: chip, srv });
  await E.revisar();
  const r = await E.cortar('bbbbbbbbbbbb');
  ok(r.ok && pedidos.length === 1 && JSON.stringify(pedidos[0].filters) === '[{"vendorId":1027}]',
     'sin conectar: "Cortar" abre la ventanita de Chrome (solo FTDI), conecta y corta');
  ok(JSON.stringify(chip.control.find(c => c[0] === 3)) === JSON.stringify([3, 0x4138, 0]), 'el chip queda a 9600 baudios');
  ok(txt(chip.llegado) === esc.conectar + esc.enviar, 'llega al plotter EXACTAMENTE lo que manda el escritorio al conectar y enviar',
     JSON.stringify(txt(chip.llegado)).slice(0, 160));
  const fin = srv.llamadas.find(l => l[0] === '/api/estacion/terminar');
  ok(fin && fin[1].resultado === 'hecho' && srv.trabajos[0].estado === 'hecho', 'al terminar le avisa al servidor: "hecho"');
  ok(E.estado.mensaje && E.estado.mensaje.tipo === 'ok' && /Logo/.test(E.estado.mensaje.texto), 'y en pantalla: "Logo" enviado entero');
  ok(E.estado.cortando === null, 'la estación queda libre para el siguiente');
}

// 3 · Detener a media corte
{
  const chip = chipUsb({ lento: 2 });
  const srv = servidorFalso([{ id: 'cccccccccccc', nombre: 'Grande', hpgl: esc.hpgl }]);
  const { E } = montar({ permitidos: [chip], srv });
  await E.auto();
  const p = E.cortar('cccccccccccc');
  await dormir(40);
  E.detener();
  const r = await p;
  ok(r.resultado === 'cancelado' && srv.trabajos[0].estado === 'cancelado' && /Detenido en la línea/.test(srv.trabajos[0].detalle),
     'Detener: corta el envío y el servidor lo anota como "detenido" con la línea', srv.trabajos[0].detalle);
  ok(txt(chip.llegado).endsWith('\x1bIN;\n'), 'y manda el mismo paro que el escritorio (ESC + IN;)');
}

// 4 · Desenchufar a media corte: error visible, sin fingir que terminó
{
  const chip = chipUsb({ lento: 2 });
  const srv = servidorFalso([{ id: 'dddddddddddd', nombre: 'Corte', hpgl: esc.hpgl }]);
  const { E, escuchas } = montar({ permitidos: [chip], srv });
  await E.auto();
  const p = E.cortar('dddddddddddd');
  await dormir(40);
  chip.abierto = false; escuchas.disconnect({ device: chip.dev });
  const r = await p;
  ok(r.resultado === 'error' && srv.trabajos[0].estado === 'error' && /desconectó/.test(srv.trabajos[0].detalle),
     'desenchufar a media corte → "Falló: se desconectó el cable", nunca "hecho"', srv.trabajos[0].detalle);
  ok(!E.estado.conectado, 'y la estación queda desconectada');
  escuchas.connect({ device: chip.dev });
  await dormir(10);
  ok(E.estado.conectado, 'al volver a enchufar, se reconecta sola');
}

// 5 · Otra estación lo tomó primero
{
  const chip = chipUsb();
  const srv = servidorFalso([{ id: 'eeeeeeeeeeee', nombre: 'X', hpgl: esc.hpgl, estado: 'cortando' }]);
  const { E } = montar({ permitidos: [chip], srv });
  await E.auto(); chip.llegado.length = 0;
  const r = await E.cortar('eeeeeeeeeeee');
  ok(!r.ok && chip.llegado.length === 0 && /no está esperando/.test(E.estado.mensaje.texto), 'si otra estación ya lo tomó: lo dice y no manda nada al plotter');
}

// 6 · Cortó, pero el servidor no contestó al final
{
  const chip = chipUsb();
  const srv = servidorFalso([{ id: 'ffffffffffff', nombre: 'Y', hpgl: esc.test_square_hpgl }]);
  const { E } = montar({ permitidos: [chip], srv });
  await E.auto();
  srv.terminarFalla = true;
  const r = await E.cortar('ffffffffffff');
  ok(r.ok && /no pude avisarle al servidor/.test(E.estado.mensaje.texto), 'si al final no hay red: avisa que quedará en "¿Se terminaron?"');
  srv.terminarFalla = false;
}

// 7 · Uno a la vez
{
  const chip = chipUsb({ lento: 2 });
  const srv = servidorFalso([{ id: '111111111111', nombre: 'A', hpgl: esc.hpgl }, { id: '222222222222', nombre: 'B', hpgl: esc.hpgl }]);
  const { E } = montar({ permitidos: [chip], srv });
  await E.auto();
  const p = E.cortar('111111111111');
  await dormir(10);
  const r2 = await E.cortar('222222222222');
  ok(r2.ok === false && srv.trabajos[1].estado === 'pendiente', 'mientras corta uno, "Cortar" en otro no hace nada');
  await p;
}

// 8 · Los que quedaron "cortando" y "Cortar otra vez"
{
  const chip = chipUsb();
  const srv = servidorFalso([{ id: '333333333333', nombre: 'Viejo', hpgl: esc.hpgl, estado: 'cortando' }]);
  const { E } = montar({ permitidos: [chip], srv });
  await E.marcar('333333333333', 'pendiente');
  ok(srv.trabajos[0].estado === 'pendiente', '"No, volver a la fila" lo deja listo para cortar de nuevo');
  await E.quitar('333333333333');
  ok(srv.trabajos.length === 0, '"Descartar" lo quita');
}

// 9 · Navegadores
{
  const { E } = montar({ android: false });
  ok(E.estado.soporte && !E.estado.usb, 'en computadora la estación usa Web Serial, no WebUSB');
  const sin = montar({ conUsb: false });
  ok(!sin.E.estado.soporte, 'Android sin WebUSB (http, otro navegador): lo sabe');
  const r = await sin.E.cortar('aaaaaaaaaaaa');
  ok(!r.ok && /Google Chrome/.test(sin.E.estado.mensaje.texto), 'y al tocar Cortar dice que se abra en Chrome, sin tomar el trabajo');
  ok(!sin.srv.llamadas.some(l => l[0] === '/api/estacion/tomar'), 'el trabajo sigue esperando en el servidor');
}
{
  const srv = servidorFalso(); srv.caido = true;
  const { E } = montar({ srv });
  await E.revisar();
  ok(E.estado.servidor === false, 'sin red: lo marca ("reintentando") en vez de borrar la lista');
}
{
  const { ctx } = montar();
  ok(ctx.haceCuanto(20) === 'hace un momento' && ctx.haceCuanto(300) === 'hace 5 min' && ctx.haceCuanto(7200) === 'hace 2 h', '"hace cuánto" legible');
}

console.log(fallos ? `\n${fallos} FALLA(S)` : '\nTodo OK');
process.exit(fallos ? 1 : 0);
