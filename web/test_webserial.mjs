// Prueba el <script id="motor"> REAL de web/prueba_webserial.html contra un plotter simulado.
import fs from 'fs';
import vm from 'vm';

const html = fs.readFileSync(process.argv[2], 'utf8');
const src = html.match(/<script id="motor">([\s\S]*?)<\/script>/)[1];
const ctx = { TextEncoder, setTimeout, Date, Promise, Uint8Array, Error };
vm.createContext(ctx);
vm.runInContext(src + '\n;globalThis.M={hpglCuadrado,hpglFlujo,nuevoFlujo,alRecibir,enviar,bytesAbortar,XOFF,XON};', ctx);
const M = ctx.M;

let fallos = 0;
const ok = (c, msg) => { console.log((c ? 'OK   ' : 'FALLA') + ' ' + msg); if (!c) fallos++; };

// Plotter simulado: memoria de CAP bytes que se vacía a RITMO bytes cada 5 ms. Manda XOFF al
// pasar ALTO y XON al bajar de BAJO, con LAT ms de retraso (el cable no es instantáneo).
function plotter(st, { CAP = 512, ALTO = 384, BAJO = 128, RITMO = 40, LAT = 2, mudo = false, BYTE_MS = 0.1 } = {}) {
  const p = { buf: 0, max: 0, desborde: 0, recibido: [], xoffEnviado: false };
  const avisar = b => setTimeout(() => M.alRecibir(st, [b]), LAT);
  const tick = setInterval(() => {
    p.buf = Math.max(0, p.buf - RITMO);
    if (p.xoffEnviado && p.buf < BAJO && !mudo) { p.xoffEnviado = false; avisar(M.XON); }
  }, 5);
  p.escribir = async datos => {
    // a 9600 baudios cada byte tarda ~1 ms en el cable: el envío NO es instantáneo
    await new Promise(r => setTimeout(r, Math.max(1, Math.round(datos.length * BYTE_MS))));
    p.recibido.push(...datos);
    p.buf += datos.length;
    if (p.buf > CAP) { p.desborde += p.buf - CAP; p.buf = CAP; }
    p.max = Math.max(p.max, p.buf);
    if (!p.xoffEnviado && p.buf > ALTO) { p.xoffEnviado = true; avisar(M.XOFF); }
  };
  p.parar = () => clearInterval(tick);
  return p;
}

// 1. El cuadrado es byte a byte el del motor Python.
const py = 'IN;\nPA;\nSP1;\nVS200;\nFS140;\nPU0,0;\nPD400,0,400,400,0,400,0,0;\nPU;\nPU0,0;\nSP0;';
ok(M.hpglCuadrado(10, 200, 140).join('\n') === py, 'cuadrado 10 mm idéntico al de HPGLConverter.test_square()');

// 2. Flujo: la página respeta las pausas → cero desborde, todo en orden.
{
  const st = M.nuevoFlujo(), lineas = M.hpglFlujo(2000), p = plotter(st);
  const r = await M.enviar(p.escribir, lineas, st, { pausaMs: 0 });
  p.parar();
  const esperado = new TextEncoder().encode(lineas.map(l => l + '\n').join(''));
  ok(r.completo && r.enviadas === lineas.length, `envío completo (${r.enviadas} líneas, ${r.bytes} bytes)`);
  ok(st.xoffs > 0, `el plotter pidió esperar ${st.xoffs} veces`);
  ok(p.desborde === 0, `cero bytes desbordados (memoria máx usada ${p.max} de 512)`);
  ok(Buffer.from(p.recibido).equals(Buffer.from(esperado)), 'el plotter recibió exactamente los bytes, en orden');
}

// 3. CONTROL: el mismo envío ignorando las pausas TIENE que desbordar, o la prueba 2 no vale nada.
{
  const st = M.nuevoFlujo(), p = plotter(st);
  const sordo = { ...st, get pausado() { return false; }, set pausado(v) {} };
  const r = await M.enviar(p.escribir, M.hpglFlujo(2000), sordo, { pausaMs: 0 });
  p.parar();
  ok(r.completo && p.desborde > 0, `sin control de flujo SÍ desborda (${p.desborde} bytes perdidos): el simulador detecta el fallo`);
}

// 4. XOFF sin XON nunca → error claro, no un cuelgue callado.
{
  const st = M.nuevoFlujo(), p = plotter(st, { mudo: true });
  let err = null;
  try { await M.enviar(p.escribir, M.hpglFlujo(2000), st, { pausaMs: 0, maxEsperaMs: 300 }); }
  catch (e) { err = e; }
  p.parar();
  ok(err && /no reanudó/.test(err.message), 'plotter que nunca dice "sigue" → error visible: ' + (err && err.message));
}

// 5. Detener a media prueba (también estando en pausa).
{
  const st = M.nuevoFlujo(), p = plotter(st);
  setTimeout(() => { st.detener = true; }, 40);
  const r = await M.enviar(p.escribir, M.hpglFlujo(2000), st, { pausaMs: 0 });
  p.parar();
  ok(!r.completo && r.enviadas > 0 && r.enviadas < 2004, `Detener corta el envío (en la línea ${r.enviadas})`);
}

// 6. Abortar = ESC + IN;\n, como PlotterController.abort().
// 5b. Con la pausa REAL de la página (10 ms) y un plotter lento, también obedece.
{
  const st = M.nuevoFlujo(), lineas = M.hpglFlujo(400), p = plotter(st, { RITMO: 2 });
  const r = await M.enviar(p.escribir, lineas, st);
  p.parar();
  ok(r.completo && st.xoffs > 0 && p.desborde === 0, `pausa real de 10 ms + plotter lento: ${st.xoffs} pausas, ${p.desborde} bytes desbordados`);
}

ok(Buffer.from(M.bytesAbortar()).equals(Buffer.from('\x1bIN;\n')), 'abortar manda ESC + "IN;"');

// 7. La prueba de flujo nunca baja la cuchilla y queda dentro de 20 mm.
{
  const L = M.hpglFlujo(2000);
  const sinPD = !L.some(l => l.startsWith('PD') || l.startsWith('SP1'));
  const dentro = L.filter(l => /^PU\d/.test(l)).every(l => l.slice(2, -1).split(',').every(v => +v >= 0 && +v <= 800));
  ok(sinPD && dentro, 'prueba de flujo: cuchilla siempre ARRIBA y dentro del recuadro de 20 mm');
}

console.log(fallos ? `\n${fallos} FALLA(S)` : '\nTodo OK');
process.exit(fallos ? 1 : 0);
