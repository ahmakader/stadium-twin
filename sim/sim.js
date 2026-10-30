/* Standpoint egress + fire engine.
   Movement: network (coarse) model with SFPE speed–density on every link (S = k(1 − 0.266·D), k = 1.40 level,
   1.08 stepped; free-flow below 0.54 p/m²; minimum 15 % of free speed) and Green Guide rates of passage as link
   capacities (82 p/m/min level and gates, 66 p/m/min stepped). A link only accepts people while its density is
   below 3.55 p/m² (queues spill back upstream). Routing: congestion-aware shortest time to a place of safety,
   recomputed every few seconds; links into untenable nodes are closed.
   Fire: t² growth (PD 7974-1 / NFPA α values), Heskestad flame height and plume, point-source radiation
   (χr = 0.3) against a 2.5 kW/m² limit, a one-zone smoke reservoir under the roof spilling over the open roof
   front, and an Alpert ceiling-jet front along enclosed concourses. Smoke-logged when the clear height falls
   below 2.5 m. This is a design-guideline approximation, not CFD (FDS) or a certified egress tool. */
const SIM = (() => {
  const RATE = { 0: 82 / 60, 1: 66 / 60, 2: 82 / 60, 3: 1 / 40, 4: 66 / 60 };    // persons per metre per second (lift: per lift)
  const KTERR = { 0: 1.40, 1: 1.08, 2: 1.40, 3: 1.0, 4: 1.08 };
  const DMAX = 3.55, WHEEL_V = 0.8;
  const ALPHA = { slow: 0.00293, medium: 0.01172, fast: 0.0469, ultrafast: 0.1876 };
  const SAFE_KIND = { out: 1, pitch: 2 };

  function mulberry(a) { return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  function lognormal(rnd, median, sigma) { const u = Math.max(1e-9, rnd()), v = rnd(); const z = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); return median * Math.exp(sigma * z); }

  class Heap { constructor() { this.k = []; this.v = []; }
    push(key, val) { const k = this.k, v = this.v; let i = k.length; k.push(key); v.push(val); while (i > 0) { const p = (i - 1) >> 1; if (k[p] <= key) break; k[i] = k[p]; v[i] = v[p]; i = p; } k[i] = key; v[i] = val; }
    pop() { const k = this.k, v = this.v, rk = k[0], rv = v[0], lk = k.pop(), lv = v.pop(); const n = k.length; if (n) { let i = 0; for (;;) { let c = 2 * i + 1; if (c >= n) break; if (c + 1 < n && k[c + 1] < k[c]) c++; if (k[c] >= lk) break; k[i] = k[c]; v[i] = v[c]; i = c; } k[i] = lk; v[i] = lv; } this.top = rk; return rv; }
    get size() { return this.k.length; } }

  function create(net, seats) {
    const NN = net.nodes.length;
    const nx = new Float32Array(NN), ny = new Float32Array(NN), nz = new Float32Array(NN);
    const nkind = net.nodes.map((n) => n[3]), nseg = net.nodes.map((n) => n[4]), nlabel = net.nodes.map((n) => n[6]);
    net.nodes.forEach((n, i) => { nx[i] = n[0]; ny[i] = n[1]; nz[i] = n[2]; });
    const roofUnder = Float32Array.from(net.roofUnder);
    // directed links
    const dF = [], dT = [], dK = [], dW = [], dL = [], dU = [];
    net.edges.forEach(([a, b, k, w, L], u) => {
      const add = (f, t) => { dF.push(f); dT.push(t); dK.push(k); dW.push(w); dL.push(L); dU.push(u); };
      add(a, b); if (k === 0 || k === 1) add(b, a);
    });
    const NE = dF.length, NU = net.edges.length;
    const cap = new Float32Array(NE), vfree = new Float32Array(NE), maxCnt = new Float32Array(NE), tokens = new Float32Array(NE);
    for (let e = 0; e < NE; e++) {
      cap[e] = dK[e] === 3 ? RATE[3] : RATE[dK[e]] * dW[e];
      vfree[e] = dK[e] === 3 ? 1.0 : KTERR[dK[e]] * (1 - 0.266 * 0.54);
      maxCnt[e] = dK[e] === 3 ? 4 : Math.max(2, dL[e] * dW[e] * DMAX);
    }
    const outIdx = Array.from({ length: NN }, () => []); for (let e = 0; e < NE; e++) outIdx[dF[e]].push(e);
    const inIdx = Array.from({ length: NN }, () => []); for (let e = 0; e < NE; e++) inIdx[dT[e]].push(e);
    const uArea = new Float32Array(NU); net.edges.forEach(([a, b, k, w, L], u) => (uArea[u] = Math.max(0.5, w * L)));
    const cntD = new Float32Array(NE), cntU = new Float32Array(NU), vU = new Float32Array(NU * 1), densU = new Float32Array(NU), peakDens = new Float32Array(NU);
    const enclosed = (k) => k === 'conc' || k === 'ground' || k === 'vom' || k === 'land' || k === 'half';

    const S = {
      net, NN, NE, NU, nx, ny, nz, nkind, nseg, nlabel, dF, dT, dK, dW, dL, dU, cap, densU, peakDens, cntU,
      t: 0, running: false, done: false, scenario: 'egress', params: {}, agents: 0,
      untenT: new Float32Array(NN).fill(Infinity), untenNow: new Uint8Array(NN), edgeBlocked: new Uint8Array(NE), edgeSmoke: new Uint8Array(NE),
      fire: null, curve: [], gateCount: new Map(), gateRecent: new Map(), log: [],
    };

    /* ---------------- routing */
    const nextE = [new Int32Array(NN).fill(-1), new Int32Array(NN).fill(-1)];
    const dist = [new Float64Array(NN), new Float64Array(NN)];
    let queuedOn = new Float32Array(NE);
    function allowed(e, cls) {
      const k = dK[e];
      if (S.edgeBlocked[e]) return false;
      if (k === 4 && !S.params.pitch) return false;
      if (cls === 0) return k !== 3;
      if (k === 1 || k === 4) return false;
      if (k === 3 && S.t < S.liftStart) return false;
      return true;
    }
    function route() {
      for (let cls = 0; cls < 2; cls++) {
        const D = dist[cls], nxt = nextE[cls]; D.fill(Infinity); nxt.fill(-1);
        const h = new Heap();
        let nsrc = 0;
        for (let i = 0; i < NN; i++) if (nkind[i] === 'out' || (nkind[i] === 'pitch' && S.params.pitch)) { if (!S.untenNow[i]) { D[i] = 0; h.push(0, i); nsrc++; } }
        if (!nsrc) for (let i = 0; i < NN; i++) if (nkind[i] === 'out' && S.untenNow[i] !== 2) { D[i] = 0; h.push(0, i); }
        while (h.size) {
          const dk = h.k[0]; const v = h.pop(); if (dk > D[v]) continue;
          for (const e of inIdx[v]) {
            if (!allowed(e, cls)) continue;
            const u = dF[e];
            const c = dL[e] / (cls ? Math.min(WHEEL_V, vfree[e]) : vfree[e]) + queuedOn[e] / Math.max(0.05, cap[e]) * 0.8 + cntU[dU[e]] / Math.max(0.05, cap[e]) * 0.25 + (S.edgeSmoke[e] ? 600 : 0);
            const nd = dk + c;
            if (nd < D[u]) { D[u] = nd; nxt[u] = e; h.push(nd, u); }
          }
        }
      }
    }

    /* ---------------- agents */
    let A = null;
    function reset(scenario, params) {
      S.scenario = scenario; S.params = Object.assign({ occupancy: 'full', pitch: false, seed: 7, alarm: 60, peak: 5, growth: 'fast', target: 6 }, params);
      S.t = scenario === 'egress' ? -300 : 0; S.done = false; S.running = false; graphDist = null;
      if (S.fire) { S.fire.depth = 0; S.fire.rf = 0; S.fire.Q = 0; S.fire.vis = 99; S.fire.Tl = 293; }
      S.liftStart = scenario === 'fire' ? S.params.alarm + 90 : -1e9;
      S.untenT.fill(Infinity); S.untenNow.fill(0); S.edgeBlocked.fill(0); S.edgeSmoke.fill(0); peakDens.fill(0); cntU.fill(0); cntD.fill(0); tokens.fill(0); queuedOn.fill(0);
      S.curve = []; S.gateCount = new Map(); S.gateRecent = new Map(); S.firstUntenable = null; S.log = [];
      const rnd = mulberry(S.params.seed);
      const idx = [];
      const zoneSegs = (scenario === 'fire' && S.params.strategy === 'zone' && S.fire && S.fire.seg) ? new Set([S.fire.seg, ...(S.fire.neigh || neighbours(S.fire.seg))]) : null;
      for (let i = 0; i < seats.N; i++) {
        const occupied = S.params.occupancy === 'full' ? true : !seats.avail[i];
        if (occupied) idx.push(i);
      }
      S.zoneSegs = zoneSegs;
      const n = idx.length; S.agents = n;
      A = { seat: Int32Array.from(idx), cls: new Uint8Array(n), st: new Uint8Array(n), e: new Int32Array(n).fill(-1), s: new Float32Array(n), t0: new Float32Array(n),
        row: new Float32Array(n), rowT: new Float32Array(n), lat: new Float32Array(n), safeT: new Float32Array(n).fill(NaN), leftT: new Float32Array(n).fill(NaN),
        node: new Int32Array(n), exposed: new Uint8Array(n), seg: new Uint8Array(n), out: new Int32Array(n).fill(-1), stay: new Uint8Array(n) };
      S.A = A;
      const segIx = net.segOrder;
      // fire-specific: who can see the flames
      const f = S.fire;
      for (let k = 0; k < n; k++) {
        const i = idx[k];
        A.cls[k] = seats.type[i] === 1 ? 1 : 0;
        A.node[k] = seats.entry[i];
        A.row[k] = seats.rdist[i] / 10;
        A.rowT[k] = A.cls[k] ? A.row[k] / WHEEL_V + 2 : A.row[k] / 0.47 + 1.0;      // ~1 s per seat passed in the row
        A.lat[k] = rnd();
        A.seg[k] = segIx.indexOf(seats.seg[i]);
        if (scenario === 'egress') {
          const r = rnd();
          A.t0[k] = r < 0.08 ? -300 * rnd() : r < 0.9 ? Math.min(360, lognormal(rnd, 70, 0.75)) : 180 + 420 * rnd();
        } else {
          let t = S.params.alarm + lognormal(rnd, 45, 0.6);
          if (f) {
            const dx = seats.x[i] - f.x, dy = seats.y[i] - f.y, dz = seats.z[i] - f.z;
            const d = Math.hypot(dx, dy, dz);
            if (f.where !== 'interior' && d < 30) t = Math.min(t, 10 + 20 * rnd() + d * 0.5);       // sees the fire
          }
          A.t0[k] = t;
        }
        A.st[k] = 0;
        if (zoneSegs && !zoneSegs.has(seats.seg[i])) { A.stay[k] = 1; A.t0[k] = Infinity; }
      }
      S.movers = 0; for (let k = 0; k < n; k++) if (!A.stay[k]) S.movers++;
      updateHazards(0.0001); route();
      S.nodeQ = [Array.from({ length: NN }, () => []), Array.from({ length: NN }, () => [])];
      S.qHead = [new Int32Array(NN), new Int32Array(NN)];
      S.active = new Uint8Array(NN); S.activeList = [];
      S.stats = makeStats();
      S.routeT = 0; S.hazT = 0;
    }

    function makeStats() {
      const segs = net.segOrder.length;
      const tot = new Int32Array(segs), safe = new Int32Array(segs), left = new Int32Array(segs);
      for (let k = 0; k < S.agents; k++) if (!A.stay[k]) tot[A.seg[k]]++;
      return { tot, safe, left, clearT: new Float32Array(segs).fill(NaN), safeAllT: new Float32Array(segs).fill(NaN), nSafe: 0, nLeft: 0, nExposed: 0, t99: NaN, t100: NaN, tLeft99: NaN };
    }

    /* ---------------- fire + hazards */
    function setFire(f) { S.fire = f ? Object.assign({ depth: 0, rf: 0, Q: 0 }, f) : null; }
    function Qat(t) { const f = S.fire; if (!f || t <= 0) return 0; return Math.min(ALPHA[S.params.growth] * t * t, S.params.peak * 1000); }
    function flame(Q) { const D = Math.sqrt(4 * (Math.max(Q, 1) / 500) / Math.PI); const L = Math.max(0.3, 0.235 * Math.pow(Q, 0.4) - 1.02 * D); return { D, L }; }
    S.Qat = Qat; S.flame = flame; S.ALPHA = ALPHA;
    function plume(Qc, z, L) { if (z <= L) return 0.0056 * Qc * z / Math.max(L, 0.1); return 0.071 * Math.pow(Qc, 1 / 3) * Math.pow(z, 5 / 3) + 0.0018 * Qc; }
    let graphDist = null;
    function interiorDistances(src) {
      const D = new Float64Array(NN).fill(Infinity); const h = new Heap(); D[src] = 0; h.push(0, src);
      while (h.size) { const dk = h.k[0]; const v = h.pop(); if (dk > D[v]) continue;
        for (const e of outIdx[v]) { const u = dT[e]; if (dK[e] !== 0) continue; if (nkind[u] !== nkind[src] && nkind[u] !== 'vom') continue; const nd = dk + dL[e]; if (nd < D[u]) { D[u] = nd; h.push(nd, u); } } }
      return D;
    }
    function updateHazards(dt) {
      const f = S.fire; if (!f || S.scenario !== 'fire') return false;
      const t = S.t, Q = Qat(t); f.Q = Q; const { D, L } = flame(Q); f.D = D; f.L = L;
      const Qc = 0.7 * Q;
      if (f.where === 'roof' && Q > 0) {
        const T0 = 293, A_ = f.area, W = f.frontLen;
        let d = f.depth;
        const sub = Math.max(1, Math.ceil(dt / 0.25)), h = dt / sub;
        for (let i = 0; i < sub; i++) {
          const z = Math.max(0.5, f.ceil - d - f.y);
          const mi = plume(Qc, z, L);
          const Tl = Math.min(1100, T0 + Qc / Math.max(mi, 0.01));
          const rho = 353 / Tl;
          const mo = 0.4 * 1.2 * W * Math.sqrt(Math.max(0, 2 * 9.81 * d * d * d * (Tl - T0) * T0 / (Tl * Tl)));
          d = Math.min(Math.max(0, d + (mi - mo) / (rho * A_) * h), Math.max(0, f.ceil - f.y));
          f.Tl = Tl;
          // visibility: soot yield 0.05 kg/kg, heat of combustion 25 MJ/kg, specific extinction 8.7 m²/g, S = 3 / K
          const soot = 0.05 * Q / 25000, conc = soot / Math.max(0.1, mi / rho);
          f.vis = Math.min(99, 3 / Math.max(1e-6, 8700 * conc));
        }
        f.depth = d;
      }
      if (f.where === 'interior' && Q > 0) {
        if (!graphDist) graphDist = interiorDistances(f.node);
        const H = 4.5, r = Math.max(f.rf, 0.01);
        const U = r < 0.15 * H ? 0.96 * Math.pow(Q / H, 1 / 3) : 0.195 * Math.pow(Q, 1 / 3) * Math.sqrt(H) / Math.pow(r, 5 / 6);
        if (Q > 100) f.rf = Math.min(f.rf + U * dt, 40 + Q / 100);     // smoke reach limited by venting to the bowl
      }
      let changed = false;
      const fy = f.y + L / 2;
      for (let n = 0; n < NN; n++) {
        let bad = false, lvl = 0;
        const k = nkind[n];
        const sameSpace = f.where === 'interior' ? enclosed(k) : !enclosed(k);
        if (sameSpace && Q > 0) {
          const r = Math.max(0.5, Math.hypot(nx[n] - f.x, ny[n] + 1.5 - fy, nz[n] - f.z));
          const q = 0.3 * Q / (4 * Math.PI * r * r);
          if (q > 2.5) bad = true;
          if (q > 10 || r < D / 2 + 1) lvl = 2;          // flame zone: impassable
        }
        if (!bad && f.where === 'roof' && roofUnder[n] > 0 && (k === 'aisle')) {
          const segN = nseg[n];
          const dep = segN === f.seg ? f.depth : f.neigh.includes(segN) ? f.depth * 0.6 : 0;
          if (dep > 0 && roofUnder[n] - dep < ny[n] + 2.5 && (f.vis || 99) < 10) bad = true;
        }
        if (!bad && f.where === 'interior' && enclosed(k) && graphDist && graphDist[n] <= f.rf && Q > 300) bad = true;
        // hot smoke layer: above ~200 °C its radiation alone is untenable (SFPE upper-layer criterion), near the fire
        if (!bad && f.where === 'roof' && k === 'aisle' && roofUnder[n] > 0 && (f.Tl || 293) - 293 > 180 && Math.hypot(nx[n] - f.x, nz[n] - f.z) < 15 && Math.abs(roofUnder[n] - f.ceil) < 4) bad = true;
        const nl = lvl === 2 ? 2 : bad ? 1 : 0;
        if (nl !== S.untenNow[n]) { S.untenNow[n] = nl; changed = true; }
        if (bad && S.untenT[n] === Infinity) { S.untenT[n] = t; if (!S.firstUntenable) S.firstUntenable = { t, node: n }; }
      }
      if (changed) for (let e = 0; e < NE; e++) { S.edgeBlocked[e] = S.untenNow[dT[e]] === 2 ? 1 : 0; S.edgeSmoke[e] = S.untenNow[dT[e]] === 1 ? 1 : 0; }
      return changed;
    }

    /* ---------------- step */
    // queues form at link entries (node queues), so inside a link density is taken up to the SFPE optimum (1.88 p/m²)
    function speed(u, k) { const D = Math.min(densU[u], 1.88); const kk = KTERR[k]; if (D <= 0.54) return kk * (1 - 0.266 * 0.54); return kk * (1 - 0.266 * D); }
    function pushQ(cls, node, a) { S.nodeQ[cls][node].push(a); if (!S.active[node]) { S.active[node] = 1; S.activeList.push(node); } }
    function arriveSafe(a, node, e) {
      A.st[a] = 5; A.safeT[a] = S.t; A.out[a] = node; S.stats.nSafe++; S.stats.safe[A.seg[a]]++;
      if (S.stats.safe[A.seg[a]] === S.stats.tot[A.seg[a]]) S.stats.safeAllT[A.seg[a]] = S.t;
      const lbl = nkind[node] === 'pitch' ? 'Pitch' : nlabel[node];
      S.gateCount.set(lbl, (S.gateCount.get(lbl) || 0) + 1);
      const r = S.gateRecent.get(lbl) || []; r.push(S.t); S.gateRecent.set(lbl, r);
      if (S.stats.nSafe >= 0.99 * S.movers && isNaN(S.stats.t99)) S.stats.t99 = S.t;
      if (S.stats.nSafe >= S.movers) { S.stats.t100 = S.t; S.done = true; }
    }
    function markLeft(a) {
      if (!isNaN(A.leftT[a])) return; A.leftT[a] = S.t; const sg = A.seg[a]; S.stats.left[sg]++; S.stats.nLeft++;
      if (S.stats.left[sg] === S.stats.tot[sg]) S.stats.clearT[sg] = S.t;
      if (S.stats.nLeft >= 0.99 * S.movers && isNaN(S.stats.tLeft99)) S.stats.tLeft99 = S.t;
    }
    function step(dt) {
      if (S.done) return;
      S.t += dt;
      // hazards and routing
      S.hazT -= dt; let ch = false;
      if (S.hazT <= 0) { ch = updateHazards(Math.max(dt, 1)); S.hazT = 1; }
      S.routeT -= dt;
      if (ch || S.routeT <= 0) {
        queuedOn.fill(0);
        for (const node of S.activeList) for (let c = 0; c < 2; c++) { const q = S.nodeQ[c][node], h = S.qHead[c][node]; const m = q.length - h; if (m > 0) { const e = nextE[c][node]; if (e >= 0) queuedOn[e] += m; } }
        route(); S.routeT = 4;
      }
      for (let e = 0; e < NE; e++) tokens[e] = Math.min(tokens[e] + cap[e] * dt, cap[e] * dt + 1);
      for (let u = 0; u < NU; u++) { densU[u] = cntU[u] / uArea[u]; if (densU[u] > peakDens[u]) peakDens[u] = densU[u]; }
      const n = S.agents, t = S.t, st = A.st;
      for (let a = 0; a < n; a++) {
        const s_ = st[a];
        if (s_ === 0) { if (t >= A.t0[a]) st[a] = 1; }
        else if (s_ === 1) { A.rowT[a] -= dt; if (A.rowT[a] <= 0) { st[a] = 2; pushQ(A.cls[a], A.node[a], a); } }
        else if (s_ === 3) {
          const e = A.e[a], u = dU[e];
          let v = speed(u, dK[e]); if (A.cls[a]) v = Math.min(v, dK[e] === 3 ? 1.0 : WHEEL_V);
          if (dK[e] === 3) v = 1.0;
          A.s[a] += v * dt;
          if (A.s[a] >= dL[e]) {
            A.s[a] = dL[e]; const to = dT[e];
            if (S.untenNow[to] && !A.exposed[a]) { A.exposed[a] = 1; S.stats.nExposed++; }
            if (nkind[to] !== 'aisle') markLeft(a);
            if (SAFE_KIND[nkind[to]] && (nkind[to] === 'out' || S.params.pitch) && S.untenNow[to] !== 2) { cntU[u]--; cntD[e]--; arriveSafe(a, to, e); }
            else { st[a] = 4; A.node[a] = to; pushQ(A.cls[a], to, a); }
          }
        }
      }
      // transfers out of node queues (FIFO per class)
      const list = S.activeList; let w = 0;
      for (let li = 0; li < list.length; li++) {
        const node = list[li]; let alive = false;
        for (let c = 0; c < 2; c++) {
          const q = S.nodeQ[c][node]; let h = S.qHead[c][node];
          while (h < q.length) {
            const a = q[h]; const e = nextE[c][node];
            if (e < 0) break;
            if (tokens[e] < 1 || cntD[e] >= maxCnt[e]) break;
            tokens[e] -= 1; h++;
            if (A.e[a] >= 0 && st[a] === 4) { cntU[dU[A.e[a]]]--; cntD[A.e[a]]--; }
            A.e[a] = e; A.s[a] = 0; st[a] = 3; cntU[dU[e]]++; cntD[e]++;
          }
          if (h > 512 && h * 2 > q.length) { q.splice(0, h); h = 0; }
          S.qHead[c][node] = h;
          if (h < q.length) alive = true;
        }
        if (alive) list[w++] = node; else S.active[node] = 0;
      }
      list.length = w;
      if (Math.floor(t / 5) !== Math.floor((t - dt) / 5)) S.curve.push([t, S.stats.nSafe / Math.max(1, S.movers), S.fire ? S.fire.Q : 0]);
    }

    function counts() {
      let waiting = 0, moving = 0, queued = 0, refuge = 0, safe = 0;
      const st = A.st;
      let staying = 0;
      for (let a = 0; a < S.agents; a++) {
        const s_ = st[a];
        if (A.stay[a]) { staying++; continue; }
        if (s_ === 0) waiting++; else if (s_ === 5) safe++;
        else if (s_ === 3) { const u = dU[A.e[a]]; (densU[u] > 2.0 ? queued++ : moving++); }
        else if (s_ === 2 || s_ === 4) { if (A.cls[a] && nextE[1][A.node[a]] < 0) refuge++; else queued++; }
        else moving++;
      }
      return { waiting, moving, queued, refuge, safe, staying, inside: S.movers - safe };
    }
    function gateFlows(window = 30) {
      const out = [];
      for (const [k, arr] of S.gateRecent) { while (arr.length && arr[0] < S.t - window) arr.shift(); out.push([k, arr.length * 60 / window, S.gateCount.get(k)]); }
      return out;
    }
    function neighbours(seg) { const o = net.segOrder, i = o.indexOf(seg); return [o[(i + o.length - 1) % o.length], o[(i + 1) % o.length]]; }
    /* describe a fire from a clicked point: open air, under a stand roof (smoke reservoir), or inside a concourse */
    function indoorLabel(n) {
      const k = nkind[n], st = net.stands[nseg[n]];
      if (k === 'ground') return st + ' ground-floor concourse';
      if (k === 'land' || k === 'half') return st + ', stair core ' + nlabel[n];
      if (k === 'vom') return st + ', vomitory, tier ' + net.nodes[n][5];
      return st + ' concourse, tier ' + net.nodes[n][5];
    }
    function makeFire(x, y, z, interiorNode) {
      if (interiorNode !== undefined && interiorNode >= 0) {
        const n = interiorNode;
        return { x: nx[n], y: ny[n], z: nz[n], where: 'interior', node: n, seg: nseg[n], neigh: neighbours(nseg[n]), label: indoorLabel(n) };
      }
      if (interiorNode === -2) {      // a point on an interior floor: the nearest indoor node on that floor
        let best = -1, bd = Infinity;
        // the concourse on that floor first (rooms open onto it); stair cores are separate fire compartments
        for (const pass of [['conc', 'ground'], ['conc', 'ground', 'vom', 'land', 'half']]) {
          for (let n = 0; n < NN; n++) { if (!pass.includes(nkind[n]) || (pass.length === 2 && Math.abs(ny[n] - y) > 2)) continue; const d = (nx[n] - x) ** 2 + (ny[n] - y) ** 2 * 25 + (nz[n] - z) ** 2; if (d < bd) { bd = d; best = n; } }
          if (best >= 0) break;
        }
        if (best >= 0) return { x, y, z, where: 'interior', node: best, seg: nseg[best], neigh: neighbours(nseg[best]), label: indoorLabel(best) };
      }
      let best = -1, bd = Infinity;
      for (let n = 0; n < NN; n++) { const d = (nx[n] - x) ** 2 + (ny[n] - y) ** 2 * 4 + (nz[n] - z) ** 2; if (d < bd) { bd = d; best = n; } }
      const n = best, seg = nseg[n], k = nkind[n];
      const near = Math.sqrt(bd) < 14;
      if (near && k === 'aisle' && roofUnder[n] > 0) {
        const order = net.segOrder, i = order.indexOf(seg);
        const r = net.roofs[seg];
        const ceil = roofUnder[n] + (ny[n] - y) * 0 ;
        const neigh = [order[(i + order.length - 1) % order.length], order[(i + 1) % order.length]];
        const area = r.area + neigh.reduce((a, s_) => a + net.roofs[s_].area, 0), frontLen = r.front_len + neigh.reduce((a, s_) => a + net.roofs[s_].front_len, 0);
        return { x, y, z, where: 'roof', seg, node: n, ceil: Math.max(y + 3, roofUnder[n]), area, frontLen, neigh, label: net.stands[seg] + ' seating, under the roof' };
      }
      return { x, y, z, where: 'open', seg: near ? seg : '', neigh: near ? neighbours(seg) : [], node: n, label: near && k === 'aisle' ? net.stands[seg] + ' seating, open air' : 'Open air' };
    }
    Object.assign(S, { reset, step, setFire, counts, gateFlows, nextE, outIdx, route, updateHazards, makeFire });
    return S;
  }
  return { create, ALPHA };
})();
if (typeof module !== 'undefined') module.exports = SIM;
