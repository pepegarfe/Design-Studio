// ¿El navegador le manda al plotter EXACTAMENTE lo mismo que la app de escritorio?
//
// Saca de studio_ui.html el motor (<script id="motor-plotter">) y el conector Web Serial (WSP),
// tal cual, y los corre contra un cable de mentira. Lo que "llega al plotter" se compara byte
// a byte con lo que manda el escritorio (web/bytes_escritorio.py, el PlotterService real).
// También prueba el control de flujo contra un plotter simulado que sí pide pausas.
//
// Uso: node web/test_plotter_web.mjs
import fs from 'fs';
import vm from 'vm';
import path from 'path';
import { execFileSync } from 'child_process';
import { fileURLToPath } from 'url';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(AQUI, '..', 'studio_ui.html'), 'utf8');
const PY = fs.existsSync('/opt/homebrew/bin/python3') ? '/opt/homebrew/bin/python3' : 'python3';
const esc = JSON.parse(execFileSync(PY, [path.join(AQUI, 'bytes_escritorio.py')], { encoding: 'utf8' }));

let fallos = 0;
const ok = (c, msg) => { console.log((c ? 'OK    ' : 'FALLA ') + msg); if (!c) fallos++; };
const dormir = ms => new Promise(r => setTimeout(r, ms));
const txt = b => Buffer.from(b).toString('latin1');

// ── sacar el código de la página ──────────────────────────────────────────────
const motor = html.match(/<script id="motor-plotter">([\s\S]*?)<\/script>/)[1];
const ini = html.indexOf('  var WSP = (function(){');
const fin = html.indexOf('  function ws(){', ini);
ok(ini > 0 && fin > ini, 'encontré el conector Web Serial en studio_ui.html');
const conector = html.slice(ini, fin);

// ── un cable USB de mentira con la forma de Web Serial ────────────────────────
function cableFalso({ vendor = 0x0403 } = {}) {
  const c = { abierto: false, opciones: null, llegado: [], aPagina: null, cerrado: false };
  c.getInfo = () => ({ usbVendorId: vendor });
  c.open = async op => { if (c.abierto) { const e = new Error('ya abierto'); e.name = 'InvalidStateError'; throw e; } c.abierto = true; c.opciones = op; };
  c.close = async () => { c.abierto = false; c.cerrado = true; };
  c.writable = new WritableStream({ write: async ch => { await dormir(0); c.llegado.push(...ch); } });
  c.readable = new ReadableStream({ start: ctrl => { c.aPagina = b => ctrl.enqueue(new Uint8Array(b)); } });
  return c;
}

function montar({ permitidos = [], elegido = null } = {}) {
  const avisos = [], escuchas = {}, llamadas = [], pedidos = [];
  const serial = {
    getPorts: async () => permitidos.slice(),
    requestPort: async op => { pedidos.push(op); if (!elegido) { const e = new Error('nada'); e.name = 'NotFoundError'; throw e; } if (!permitidos.includes(elegido)) permitidos.push(elegido); return elegido; },
    addEventListener: (n, f) => { escuchas[n] = f; },
  };
  const respuesta = r => Promise.resolve(r);
  const ctx = {
    TextEncoder, setTimeout, Date, Promise, Uint8Array, Array, Error, String, parseInt, parseFloat, Math,
    navigator: { serial },
    localStorage: (() => { const m = {}; return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = v; } }; })(),
    portLabels: {},
    ws: () => ctx.WSP,
    setConnUI: c => avisos.push('conn:' + c),
    toast: m => avisos.push('toast:' + m),
    postJSON: (u, b) => { llamadas.push([u, b]); return respuesta(u === '/api/hpgl' ? { ok: true, hpgl: esc.hpgl } : { ok: false }); },
    fetch: u => { llamadas.push([u]); return respuesta({ json: () => (u === '/api/test_square' ? { ok: true, hpgl: esc.test_square_hpgl } : { ok: false }) }); },
  };
  vm.createContext(ctx);
  vm.runInContext(motor + '\n' + conector + '\n;globalThis.WSP = WSP; globalThis.M = PlotterMotor;', ctx);
  return { W: ctx.WSP, M: ctx.M, avisos, escuchas, llamadas, pedidos, permitidos, portLabels: ctx.portLabels };
}

async function hastaTerminar(W) {
  for (let i = 0; i < 2000; i++) { const p = await W.progress(); if (!p.active) return p; await dormir(5); }
  throw new Error('el envío nunca terminó');
}

// ── 1. sin permisos previos: la lista ofrece "Buscar el plotter…" ─────────────
{
  const { W } = montar();
  const r = await W.ports();
  ok(r.ok && r.items.length === 1 && r.items[0].port === 'ws:nuevo' && /Buscar el plotter/.test(r.items[0].label),
     'sin permisos: la lista solo ofrece "Buscar el plotter…"');
  const s = await W.connect('ws:nuevo', 9600);
  ok(s.ok === false && /^No elegiste ningún cable\. Si no aparecía.*encendido/.test(s.error), 'cerrar la ventanita de Chrome sin elegir → mensaje claro: ' + s.error);
  const g = await W.jog('right', 1);
  ok(g.ok === false && g.error === 'Plotter no conectado', 'mover sin conectar → "Plotter no conectado", como el escritorio');
}

// ── 2. conectar y comparar cada comando con el escritorio ────────────────────
{
  const cable = cableFalso();
  const { W, portLabels } = montar({ elegido: cable });
  const s = await W.connect('ws:nuevo', 9600);
  ok(s.ok && s.connected && s.port === 'ws:0', 'conectar eligiendo el cable en la ventanita de Chrome');
  ok(JSON.stringify(cable.opciones) === JSON.stringify({ baudRate: 9600, dataBits: 8, parity: 'none', stopBits: 1, flowControl: 'none' }),
     'abre el cable a 9600 8N1 (lo que funcionó con el 721 real)');
  ok(portLabels['ws:0'] === 'Cable USB — FTDI', 'el cable sale como "Cable USB — FTDI", no como un código');
}
{
  const cable = cableFalso();
  const { W, llamadas } = montar({ elegido: cable });
  await W.connect('ws:nuevo', 9600);
  await dormir(5);
  ok(txt(cable.llegado) === esc.conectar, `conectar: manda ${JSON.stringify(esc.conectar)} como el escritorio`);
  const casos = [
    ['jog_der_2.5', () => W.jog('right', 2.5)], ['jog_abajo_0.33', () => W.jog('down', 0.33)],
    ['jog_izq_10', () => W.jog('left', 10)], ['jog_arriba_1', () => W.jog('up', 1)],
    ['pluma_abajo', () => W.pen(true)], ['pluma_arriba', () => W.pen(false)],
    ['origen', () => W.command('origin')], ['casa', () => W.command('home')],
    ['enviar', () => W.send(esc.diseno)], ['test_corte', () => W.testcut()], ['cancelar', () => W.cancel()],
  ];
  for (const [nombre, accion] of casos) {
    cable.llegado.length = 0;
    const r = await accion();
    if (r && r.total !== undefined) await hastaTerminar(W);
    await dormir(5);
    const igual = txt(cable.llegado) === esc[nombre];
    ok(igual, `${nombre}: mismos bytes que el escritorio (${cable.llegado.length} bytes)` +
       (igual ? '' : `\n        navegador:  ${JSON.stringify(txt(cable.llegado)).slice(0, 200)}\n        escritorio: ${JSON.stringify(esc[nombre]).slice(0, 200)}`));
  }
  const pedido = llamadas.find(l => l[0] === '/api/hpgl');
  ok(pedido && JSON.stringify(pedido[1]) === JSON.stringify(esc.diseno), 'el diseño se manda tal cual al servidor para armar el HPGL');
  ok(llamadas.some(l => l[0] === '/api/test_square'), 'el test de corte pide el cuadrado al servidor (el mismo del escritorio)');
  const p = await W.progress();
  ok(p.done && !p.active && !p.error && p.sent === p.total, `progreso al terminar: ${p.sent}/${p.total}, sin error`);

  const d = await W.disconnect();
  ok(!d.connected && cable.cerrado, 'desconectar cierra el cable');
  const r = await W.send(esc.diseno);
  ok(r.ok === false && r.error === 'Plotter no conectado', 'enviar ya desconectado → "Plotter no conectado"');
}

// ── 3. la segunda vez el cable ya aparece en la lista, sin ventanita ─────────
{
  const cable = cableFalso();
  const { W } = montar({ permitidos: [cable] });
  const r = await W.ports();
  ok(r.items[0].port === 'ws:0' && r.items[0].kind === 'usb' && r.items[1].port === 'ws:nuevo',
     'con permiso previo: el cable sale primero en "Cables USB" y "Otro cable…" al final');
  const s = await W.connect('ws:0', 9600);
  ok(s.ok && s.connected, 'conectar al cable de la lista, sin ventanita');
  const otra = montar({ permitidos: [cable] }).W;   // otra pestaña: primero lista, como la app
  await otra.ports();
  const s2 = await otra.connect('ws:0', 9600);
  ok(s2.ok === false && /ya está abierto/.test(s2.error), 'el mismo cable abierto en otra pestaña → ' + s2.error);
  ok((await W.status()).last_baud === 9600, 'recuerda la velocidad (baudios) para la próxima vez');
}

// ── 4. no envía dos cortes a la vez; cancelar a medias ───────────────────────
{
  const cable = cableFalso();
  const { W } = montar({ elegido: cable });
  await W.connect('ws:nuevo', 9600);
  const r1 = await W.send(esc.diseno);
  const r2 = await W.send(esc.diseno);
  ok(r1.ok && r2.ok === false && r2.error === 'Ya hay un envío en curso', 'un segundo envío mientras corre → "Ya hay un envío en curso"');
  await dormir(30);
  await W.cancel();
  const p = await hastaTerminar(W);
  ok(p.cancelled && p.sent < p.total, `cancelar a medias: se detuvo en la línea ${p.sent} de ${p.total}`);
  ok(txt(cable.llegado).endsWith('\x1bIN;\n'), 'y lo último que recibe el plotter es ESC + IN; (el aborto del escritorio)');
}

// ── 5. desenchufar el cable avisa en pantalla ────────────────────────────────
{
  const cable = cableFalso();
  const { W, escuchas, avisos } = montar({ elegido: cable });
  await W.connect('ws:nuevo', 9600);
  escuchas.disconnect({ target: cable });
  ok(avisos.includes('conn:false') && avisos.some(a => /Se desconectó/.test(a)), 'desenchufar → la píldora pasa a "Desconectado" y avisa');
  ok((await W.status()).connected === false, 'y el estado queda desconectado');
}

// ── 6. control de flujo: si un plotter pide pausa, se espera (motor) ──────────
{
  const { M } = montar();
  const st = M.nuevoFlujo();
  const lineas = Array.from({ length: 1500 }, (_, i) => `PU${(i * 37) % 800},${i % 2 ? 800 : 0};`);
  const CAP = 512, ALTO = 384, BAJO = 128;
  let buf = 0, desborde = 0, pausado = false;
  const tick = setInterval(() => { buf = Math.max(0, buf - 40); if (pausado && buf < BAJO) { pausado = false; setTimeout(() => M.alRecibir(st, [M.XON]), 2); } }, 5);
  const escribir = async d => { await dormir(Math.max(1, Math.round(d.length * 0.1))); buf += d.length; if (buf > CAP) { desborde += buf - CAP; buf = CAP; } if (!pausado && buf > ALTO) { pausado = true; setTimeout(() => M.alRecibir(st, [M.XOFF]), 2); } };
  const r = await M.enviar(escribir, lineas, st, { pausaMs: 0 });
  clearInterval(tick);
  ok(r.completo && st.xoffs > 0 && desborde === 0, `plotter que pide pausas: ${st.xoffs} pausas, ${desborde} bytes perdidos`);
}
{
  const { M } = montar();
  const st = M.nuevoFlujo();
  M.alRecibir(st, [M.XOFF]);
  let err = null;
  try { await M.enviar(async () => {}, ['PU0,0;'], st, { maxEsperaMs: 100 }); } catch (e) { err = e; }
  ok(err && /no reanudó/.test(err.message), 'plotter que dice "espera" y nunca "sigue" → error visible, no cuelgue');
}

// ── 7. conexión de un clic (rápida) y automática ─────────────────────────────
{
  const FILTRO = '[{"usbVendorId":1027},{"usbVendorId":6790},{"usbVendorId":1659},{"usbVendorId":4292}]';
  const cable = cableFalso();
  const { W, pedidos } = montar({ elegido: cable });
  const s = await W.rapido(false);
  ok(s.ok && s.connected && pedidos.length === 1 && JSON.stringify(pedidos[0].filters) === FILTRO,
     'primera vez: un clic abre la ventanita de Chrome FILTRADA a cables de plotter (FTDI, CH340, Prolific, Silicon Labs)');
  await W.disconnect();
  const s2 = await W.rapido(false);
  ok(s2.ok && s2.connected && pedidos.length === 1, 'segunda vez: conecta directo, SIN ventanita');
}
{
  const { W, pedidos } = montar({ elegido: cableFalso({ vendor: 0x1234 }) });
  const s = await W.rapido(true);
  ok(s.ok && pedidos.length === 1 && pedidos[0] === undefined, '"Mostrar todos los cables" abre la ventanita SIN filtro');
}
{
  const ftdi = cableFalso(), otro = cableFalso({ vendor: 0x05ac });
  const { W, pedidos } = montar({ permitidos: [otro, ftdi] });
  const s = await W.rapido(false);
  ok(s.ok && ftdi.abierto && !otro.abierto && pedidos.length === 0, 'con 2 cables permitidos elige solo el que tiene chip de plotter');
}
{
  const a = cableFalso(), b = cableFalso();
  const { W, pedidos } = montar({ permitidos: [a, b], elegido: b });
  await W.rapido(false);
  ok(pedidos.length === 1 && b.abierto && !a.abierto, 'con 2 cables de plotter no adivina: pregunta cuál');
}
{
  const { W, avisos } = montar();
  const s = await W.auto();
  ok(s === null && avisos.length === 0, 'al abrir la página sin permisos: no hace nada ni molesta con avisos');
}
{
  const cable = cableFalso();
  const { W, avisos, pedidos } = montar({ permitidos: [cable] });
  const s = await W.auto();
  ok(s && s.ok && cable.abierto && pedidos.length === 0 && avisos.includes('conn:true') && avisos.some(x => /Plotter conectado/.test(x)),
     'al abrir la página con el plotter ya permitido y enchufado: se conecta solo y avisa');
  await dormir(5);
  ok(txt(cable.llegado) === esc.conectar, 'y manda el mismo IN; de arranque que el escritorio');
}
{
  const cable = cableFalso();
  const { W, escuchas, avisos } = montar({ permitidos: [cable] });
  escuchas.connect({ target: cable });
  await dormir(10);
  ok(cable.abierto && (await W.status()).connected && avisos.some(x => /Plotter conectado/.test(x)),
     'enchufar el cable con la página abierta: se conecta solo');
}
{
  const cable = cableFalso();
  await montar({ permitidos: [cable] }).W.auto();
  const { W, avisos } = montar({ permitidos: [cable] });
  const s = await W.auto();
  ok(s && !s.ok && avisos.some(x => /ya está abierto/.test(x)), 'si el cable lo tiene otra pestaña, avisa en vez de quedarse callado');
}
{
  const cable = cableFalso();
  const { W, pedidos } = montar({ elegido: cable });
  await W.rapido(false);
  const s = await W.rapido(false);
  ok(s.connected && pedidos.length === 1, 'clic de conectar estando ya conectado: no vuelve a abrir nada');
}

console.log(fallos ? `\n${fallos} FALLA(S)` : '\nTodo OK');
process.exit(fallos ? 1 : 0);
