const fs = require('fs'); const SIM = require('./sim.js');
const net = JSON.parse(fs.readFileSync((process.env.OUTDIR||'../out')+'/egress.json')); const meta = JSON.parse(fs.readFileSync((process.env.OUTDIR||'../out')+'/seats.json'));
const bin = fs.readFileSync((process.env.OUTDIR||'../out')+'/seats.bin'); const N = meta.count;
const buf = bin.buffer.slice(bin.byteOffset, bin.byteOffset + bin.length);
const P = new Float32Array(buf, 0, N * 4), MT = new Uint16Array(buf, N * 16, N * 4), TY = new Uint8Array(buf, N * 28, N);
const eb = fs.readFileSync((process.env.OUTDIR||'../out')+'/egress.bin'); const ebuf = eb.buffer.slice(eb.byteOffset, eb.byteOffset + eb.length);
const entry = new Uint16Array(ebuf, 0, N), rdist = new Uint8Array(ebuf, N * 2, N);
const seats = { N, x: new Float32Array(N), y: new Float32Array(N), z: new Float32Array(N), type: TY, entry, rdist, seg: [], avail: new Uint8Array(N) };
for (let i = 0; i < N; i++) { seats.x[i] = P[i * 4]; seats.y[i] = P[i * 4 + 1]; seats.z[i] = P[i * 4 + 2]; seats.seg[i] = meta.blocks[MT[i * 4]].seg; }
const sim = SIM.create(net, seats);
const scen = process.argv[2] || 'egress';
if (scen === 'fire') {
  const f = JSON.parse(process.argv[3]); const prm = JSON.parse(process.argv[4] || '{}'); sim.params = Object.assign({growth:'fast', peak:5, alarm:60}, prm);
  let fire;
  if (f.interiorSeg) { let best=-1; for (let n=0;n<sim.NN;n++) if (sim.nkind[n]==='conc' && sim.nseg[n]===f.interiorSeg && sim.net.nodes[n][5]===(f.tier||1)) { best=n; break; } fire = sim.makeFire(0,0,0,best); }
  else { const i = f.seat; fire = sim.makeFire(seats.x[i], seats.y[i], seats.z[i]); }
  console.log('fire', JSON.stringify(Object.assign({}, fire, {neigh: fire.neigh})));
  sim.setFire(fire);
}
sim.reset(scen, JSON.parse(process.argv[4] || '{}'));
const t0 = Date.now(); let ticks = 0;
const fmt = (t) => `${Math.floor(t / 60)}:${String(Math.round(t % 60)).padStart(2, '0')}`;
while (!sim.done && sim.t < 2400) { sim.step(0.25); ticks++;
  if (Math.round(sim.t * 4) % 240 === 0) { const c = sim.counts(); let hot = 0, hu = -1; for (let u = 0; u < sim.NU; u++) if (sim.densU[u] > hot) { hot = sim.densU[u]; hu = u; }
    console.log(fmt(sim.t), JSON.stringify(c), 'hot', hot.toFixed(2), hu >= 0 ? sim.net.edges[hu].slice(2).join('/') + ' ' + sim.nkind[sim.net.edges[hu][0]] + '>' + sim.nkind[sim.net.edges[hu][1]] + ' ' + sim.nseg[sim.net.edges[hu][0]] : '', sim.fire ? `Q=${(sim.fire.Q/1000).toFixed(1)}MW depth=${(sim.fire.depth||0).toFixed(2)} unten=${sim.untenNow.reduce((a,b)=>a+b,0)}` : ''); } }
const st = sim.stats;
console.log('agents', sim.agents, 'ms/tick', ((Date.now() - t0) / ticks).toFixed(2), 't99', fmt(st.t99), 't100', fmt(st.t100), 'left99', fmt(st.tLeft99), 'exposed', st.nExposed);
console.log('clear (left seating) per seg', net.segOrder.map((s, i) => s + ' ' + fmt(st.clearT[i])).join(' | '));
console.log('all safe per seg', net.segOrder.map((s, i) => s + ' ' + fmt(st.safeAllT[i])).join(' | '));
console.log('gates', [...sim.gateCount.entries()].sort().map(([k, v]) => k + ':' + v).join(' '));
// diagnostics: re-run and accumulate queue time per node
if (process.argv[5] === 'diag') {
  sim.reset(scen, JSON.parse(process.argv[4] || '{}'));
  const qsec = new Float64Array(sim.NN);
  while (!sim.done && sim.t < 900) { sim.step(0.5);
    for (const node of sim.activeList) for (let c = 0; c < 2; c++) qsec[node] += (sim.nodeQ[c][node].length - sim.qHead[c][node]) * 0.5; }
  const top = [...qsec.keys()].sort((a, b) => qsec[b] - qsec[a]).slice(0, 25);
  for (const n of top) { const outs = sim.outIdx[n].map((e) => `${sim.dK[e]}/${sim.dW[e]}->${sim.nkind[sim.dT[e]]}`).join(','); console.log(sim.nkind[n], sim.nseg[n], 'tier', sim.net.nodes[n][5], 'y', sim.ny[n].toFixed(1), 'queue-s', Math.round(qsec[n]), 'next', sim.nextE[0][n] >= 0 ? `${sim.dK[sim.nextE[0][n]]}/${sim.dW[sim.nextE[0][n]]}->${sim.nkind[sim.dT[sim.nextE[0][n]]]}` : '-', '| outs', outs); }
  const c = sim.counts(); console.log('at 15:00', JSON.stringify(c));
}
