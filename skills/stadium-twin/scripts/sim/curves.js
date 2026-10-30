const fs = require('fs'); const SIM = require('./sim.js');
const D = process.env.OUTDIR || '../out';
const net = JSON.parse(fs.readFileSync(D + '/egress.json')); const meta = JSON.parse(fs.readFileSync(D + '/seats.json'));
const bin = fs.readFileSync(D + '/seats.bin'); const N = meta.count; const buf = bin.buffer.slice(bin.byteOffset, bin.byteOffset + bin.length);
const P = new Float32Array(buf, 0, N * 4), MT = new Uint16Array(buf, N * 16, N * 4), TY = new Uint8Array(buf, N * 28, N);
const eb = fs.readFileSync(D + '/egress.bin'); const ebuf = eb.buffer.slice(eb.byteOffset, eb.byteOffset + eb.length);
const seats = { N, x: new Float32Array(N), y: new Float32Array(N), z: new Float32Array(N), type: TY, entry: new Uint16Array(ebuf, 0, N), rdist: new Uint8Array(ebuf, N * 2, N), seg: [], avail: new Uint8Array(N) };
for (let i = 0; i < N; i++) { seats.x[i] = P[i * 4]; seats.y[i] = P[i * 4 + 1]; seats.z[i] = P[i * 4 + 2]; seats.seg[i] = meta.blocks[MT[i * 4]].seg; }
function run(name, scen, prm, fireSpec) {
  const sim = SIM.create(net, seats);
  if (fireSpec) { sim.params = Object.assign({ growth: 'fast', peak: 10, alarm: 60 }, prm); let best = -1; for (let n = 0; n < sim.NN; n++) if (sim.nkind[n] === 'conc' && sim.nseg[n] === fireSpec.seg && sim.net.nodes[n][5] === fireSpec.tier) { best = n; break; } const f = sim.makeFire(0, 0, 0, best); sim.setFire(f); console.error(name, 'fire at', f.label); }
  sim.reset(scen, prm);
  const pts = []; let first = true;
  while (!sim.done && sim.t < 2400) { sim.step(0.25); if (Math.abs(sim.t % 10) < 0.01) { const c = sim.counts(); pts.push([sim.t, c]); if (first) { console.error(JSON.stringify(c)); first = false; } } }
  console.error(name, 't99', sim.stats.t99, 't100', sim.stats.t100);
  return { name, t99: sim.stats.t99, pts };
}
const out = [run('Full house', 'egress', { occupancy: 'full', seed: 7 }), run('Fire · East Stand concourse · 10 MW', 'fire', { occupancy: 'full', peak: 10, growth: 'ultra', alarm: 60, strategy: 'neighbours', seed: 7, target: 8 }, { seg: 'E', tier: 2 })];
fs.writeFileSync(process.env.CURVES_OUT || 'curves.json', JSON.stringify(out));
