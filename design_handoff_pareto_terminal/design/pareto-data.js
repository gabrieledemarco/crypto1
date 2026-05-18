// PARETO — mock data layer. Seeded RNG for reproducibility.
(function () {
  function mulberry32(a) {
    return function () {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function gauss(rnd) {
    // Box-Muller
    let u = 0, v = 0;
    while (u === 0) u = rnd();
    while (v === 0) v = rnd();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  function genEquity({ seed, n, mu, sigma, oosStart }) {
    const rnd = mulberry32(seed);
    const out = [];
    let v = 1.0;
    let peak = 1.0;
    let bench = 1.0;
    for (let i = 0; i < n; i++) {
      const r = mu / n + (sigma / Math.sqrt(n)) * gauss(rnd);
      v *= 1 + r;
      const br = 0.6 / n + (0.9 / Math.sqrt(n)) * gauss(rnd);
      bench *= 1 + br;
      peak = Math.max(peak, v);
      const dd = (v - peak) / peak;
      out.push({ i, v, bench, dd, oos: i >= oosStart });
    }
    return out;
  }

  function findDDPeriods(equity, k = 5) {
    // simple peak-to-trough segments
    const periods = [];
    let peak = equity[0].v, peakI = 0, trough = equity[0].v, troughI = 0, inDD = false;
    for (let i = 1; i < equity.length; i++) {
      const v = equity[i].v;
      if (v >= peak) {
        if (inDD) {
          const depth = (trough - peak) / peak;
          periods.push({
            start: peakI, trough: troughI, end: i,
            depth, length: i - peakI, recovery: i - troughI
          });
          inDD = false;
        }
        peak = v; peakI = i; trough = v; troughI = i;
      } else if (v < trough) {
        trough = v; troughI = i; inDD = true;
      }
    }
    if (inDD) {
      const depth = (trough - peak) / peak;
      periods.push({
        start: peakI, trough: troughI, end: equity.length - 1,
        depth, length: equity.length - 1 - peakI, recovery: equity.length - 1 - troughI, ongoing: true
      });
    }
    return periods.sort((a, b) => a.depth - b.depth).slice(0, k);
  }

  function genTrades({ seed, equity, n, side }) {
    const rnd = mulberry32(seed);
    const trades = [];
    const step = Math.floor(equity.length / n);
    let eq = 1.0;
    for (let i = 0; i < n; i++) {
      const idx = Math.min(equity.length - 1, i * step + Math.floor(rnd() * step * 0.5));
      const isLong = side === "long" || (side === "mix" && rnd() > 0.45);
      const r = (gauss(rnd) * 0.012 + 0.0035) * (isLong ? 1 : 1);
      const pnl = r;
      eq *= 1 + r;
      const entry = 40000 + gauss(rnd) * 4000 + idx * 30;
      const exit = entry * (1 + (isLong ? r : -r) * 1.0);
      trades.push({
        n: i + 1,
        idx,
        date: idx,
        side: isLong ? "L" : "S",
        entry: Math.round(entry),
        exit: Math.round(exit),
        r: +(gauss(rnd) * 1.4 + (pnl > 0 ? 1.6 : -0.6)).toFixed(2),
        durH: Math.max(1, Math.round(rnd() * 60 + (pnl > 0 ? 12 : 4))),
        pnl: +(pnl * 100).toFixed(2),
        equity: +(eq).toFixed(4)
      });
    }
    return trades;
  }

  function genSweep({ seed, rows = 10, cols = 10, center = [4, 6] }) {
    const rnd = mulberry32(seed);
    const grid = [];
    for (let r = 0; r < rows; r++) {
      const row = [];
      for (let c = 0; c < cols; c++) {
        const dr = r - center[0], dc = c - center[1];
        const dist2 = dr * dr * 0.6 + dc * dc * 0.5;
        const base = 2.6 * Math.exp(-dist2 / 8) - 0.4 + gauss(rnd) * 0.18;
        row.push(+base.toFixed(2));
      }
      grid.push(row);
    }
    return grid;
  }

  function genMC({ seed, n = 1000, steps = 80, mu, sigma }) {
    const rnd = mulberry32(seed);
    const paths = [];
    for (let i = 0; i < 60; i++) { // keep 60 sample paths for display
      const p = [1.0];
      let v = 1.0;
      for (let t = 0; t < steps; t++) {
        v *= 1 + mu / steps + (sigma / Math.sqrt(steps)) * gauss(rnd);
        p.push(v);
      }
      paths.push(p);
    }
    // compute percentiles per timestep over a larger virtual sample
    const sample = [];
    for (let i = 0; i < n; i++) {
      const p = [1.0];
      let v = 1.0;
      for (let t = 0; t < steps; t++) {
        v *= 1 + mu / steps + (sigma / Math.sqrt(steps)) * gauss(rnd);
        p.push(v);
      }
      sample.push(p);
    }
    const percentiles = { p5: [], p25: [], p50: [], p75: [], p95: [] };
    for (let t = 0; t <= steps; t++) {
      const slice = sample.map(p => p[t]).sort((a, b) => a - b);
      const at = (q) => slice[Math.floor((slice.length - 1) * q)];
      percentiles.p5.push(at(0.05));
      percentiles.p25.push(at(0.25));
      percentiles.p50.push(at(0.5));
      percentiles.p75.push(at(0.75));
      percentiles.p95.push(at(0.95));
    }
    // distribution of final and maxDD
    const finals = sample.map(p => p[p.length - 1]).sort((a, b) => a - b);
    const ddFinals = sample.map(p => {
      let pk = p[0], md = 0;
      for (const v of p) { pk = Math.max(pk, v); md = Math.min(md, (v - pk) / pk); }
      return md;
    }).sort((a, b) => a - b);
    return { paths, percentiles, finals, ddFinals };
  }

  function computeMetrics(equity) {
    const n = equity.length;
    const rets = [];
    for (let i = 1; i < n; i++) rets.push(equity[i].v / equity[i - 1].v - 1);
    const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
    const sd = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / rets.length);
    const ann = Math.sqrt(252);
    const sharpe = (mean / sd) * ann;
    const downside = Math.sqrt(rets.filter(r => r < 0).reduce((a, b) => a + b * b, 0) / rets.length);
    const sortino = (mean / downside) * ann;
    let peak = equity[0].v, maxDD = 0;
    for (const e of equity) { peak = Math.max(peak, e.v); maxDD = Math.min(maxDD, (e.v - peak) / peak); }
    const cagr = Math.pow(equity[n - 1].v / equity[0].v, 252 / n) - 1;
    const calmar = cagr / Math.abs(maxDD);
    return {
      sharpe: +sharpe.toFixed(2),
      sortino: +sortino.toFixed(2),
      cagr: +(cagr * 100).toFixed(1),
      maxDD: +(maxDD * 100).toFixed(1),
      calmar: +calmar.toFixed(2),
      finalReturn: +((equity[n - 1].v - 1) * 100).toFixed(1)
    };
  }

  function buildRun({ id, name, strategy, color, seed, mu, sigma }) {
    const n = 800;
    const oosStart = Math.floor(n * 0.7);
    const equity = genEquity({ seed, n, mu, sigma, oosStart });
    const isEq = equity.slice(0, oosStart);
    const oosEq = equity.slice(oosStart);
    const trades = genTrades({ seed: seed + 7, equity, n: 412, side: "mix" });
    const ddPeriods = findDDPeriods(equity, 5);
    const sweep = genSweep({ seed: seed + 11 });
    const mc = genMC({ seed: seed + 13, mu, sigma });
    const metricsIS = computeMetrics(isEq);
    const metricsOOS = computeMetrics(oosEq);
    const wins = trades.filter(t => t.pnl > 0);
    const losers = trades.filter(t => t.pnl < 0);
    const grossWin = wins.reduce((a, t) => a + t.pnl, 0);
    const grossLoss = Math.abs(losers.reduce((a, t) => a + t.pnl, 0));
    const pf = grossLoss > 0 ? grossWin / grossLoss : 0;
    return {
      id, name, strategy, color, seed, mu, sigma,
      equity, oosStart, trades,
      params: {
        fastMA: 12, slowMA: 48, atrStop: 2.5, takeProfit: 4.0,
        riskPerTrade: 1.0, fees: 10, slippage: 3, funding: true,
        universe: ["BTC", "ETH", "SOL"], timeframe: "1h"
      },
      dates: { isStart: "2021-01-01", isEnd: "2023-12-31", oosStart: "2024-01-01", oosEnd: "2025-05-18" },
      metricsIS, metricsOOS, ddPeriods, sweep, mc,
      winRate: +(wins.length / trades.length * 100).toFixed(1),
      profitFactor: +pf.toFixed(2),
      tradesCount: trades.length,
      avgDur: Math.round(trades.reduce((a, t) => a + t.durH, 0) / trades.length),
      exposure: 62
    };
  }

  // Generate monthly P&L from trades — group by month bucket of ~30 trades
  function monthlyPnL(run) {
    const buckets = 24;
    const out = [];
    const step = Math.floor(run.trades.length / buckets);
    for (let i = 0; i < buckets; i++) {
      const slice = run.trades.slice(i * step, (i + 1) * step);
      const pnl = slice.reduce((a, t) => a + t.pnl, 0);
      out.push({ idx: i, pnl: +pnl.toFixed(2) });
    }
    return out;
  }

  const runs = [
    buildRun({ id: "r1", name: "momentum-btc-1h", strategy: "momentum-cross", color: "amber", seed: 42, mu: 0.42, sigma: 0.55 }),
    buildRun({ id: "r2", name: "meanrev-eth-4h", strategy: "mean-reversion", color: "cyan", seed: 91, mu: 0.24, sigma: 0.38 }),
    buildRun({ id: "r3", name: "trend-multi-1d", strategy: "trend-following", color: "green", seed: 17, mu: 0.21, sigma: 0.28 }),
    buildRun({ id: "r4", name: "vol-breakout-15m", strategy: "vol-breakout", color: "coral", seed: 5, mu: 0.36, sigma: 0.62 })
  ];

  runs.forEach(r => { r.monthly = monthlyPnL(r); });

  // ============ ASSETS (historical series + quant stats) ============
  function probit(p) {
    if (p <= 0) p = 1e-9;
    if (p >= 1) p = 1 - 1e-9;
    const t = Math.sqrt(-2 * Math.log(p < 0.5 ? p : 1 - p));
    const c0 = 2.515517, c1 = 0.802853, c2 = 0.010328;
    const d1 = 1.432788, d2 = 0.189269, d3 = 0.001308;
    const x = t - (c0 + c1 * t + c2 * t * t) /
      (1 + d1 * t + d2 * t * t + d3 * t * t * t);
    return p < 0.5 ? -x : x;
  }

  function genAsset({ name, seed, mu, sigma, basePrice, ticker, kind }) {
    const rnd = mulberry32(seed);
    const n = 1000; // ~3y of daily bars
    const bars = [];
    let p = basePrice;
    let lastJump = 0;
    for (let i = 0; i < n; i++) {
      // base GBM with occasional shocks for fat tails
      const shock = (i - lastJump > 80 && rnd() > 0.97) ? (rnd() - 0.5) * 0.18 : 0;
      if (shock !== 0) lastJump = i;
      const r = mu / 252 + (sigma / Math.sqrt(252)) * gauss(rnd) + shock;
      const newP = p * Math.exp(r);
      const high = Math.max(p, newP) * (1 + Math.abs(gauss(rnd)) * 0.005);
      const low = Math.min(p, newP) * (1 - Math.abs(gauss(rnd)) * 0.005);
      bars.push({ i, o: p, h: high, l: low, c: newP, v: 1e6 * (0.8 + rnd() * 0.6), r });
      p = newP;
    }
    return { name, ticker, kind, bars, basePrice };
  }

  function computeAssetStats(asset) {
    const bars = asset.bars;
    const rets = bars.slice(1).map(b => b.r);
    const n = rets.length;
    const mean = rets.reduce((a, b) => a + b, 0) / n;
    const variance = rets.reduce((a, b) => a + (b - mean) ** 2, 0) / n;
    const sd = Math.sqrt(variance);
    // skew/kurt (excess)
    let m3 = 0, m4 = 0;
    for (const r of rets) { m3 += (r - mean) ** 3; m4 += (r - mean) ** 4; }
    m3 /= n; m4 /= n;
    const skew = m3 / Math.pow(variance, 1.5);
    const kurt = m4 / (variance ** 2) - 3;
    // ACF
    function acf(lag) {
      let num = 0, den = 0;
      for (let i = 0; i < n - lag; i++) num += (rets[i] - mean) * (rets[i + lag] - mean);
      for (let i = 0; i < n; i++) den += (rets[i] - mean) ** 2;
      return num / den;
    }
    const acf1 = acf(1), acf5 = acf(5), acf20 = acf(20);
    // rolling volatility (21-day annualized)
    const rollVol = [];
    const window = 21;
    for (let i = 0; i < rets.length; i++) {
      const s = Math.max(0, i - window + 1);
      const slice = rets.slice(s, i + 1);
      const m = slice.reduce((a, b) => a + b, 0) / slice.length;
      const v = slice.reduce((a, b) => a + (b - m) ** 2, 0) / slice.length;
      rollVol.push({ i, v: Math.sqrt(v * 252) });
    }
    // drawdown of price
    let peak = bars[0].c, maxDD = 0;
    bars.forEach(b => { peak = Math.max(peak, b.c); maxDD = Math.min(maxDD, (b.c - peak) / peak); });
    // sortino downside vol
    const downside = Math.sqrt(rets.filter(r => r < 0).reduce((a, b) => a + b * b, 0) / n);
    // CAGR (over data span ~ 4y daily)
    const totalRet = bars[bars.length - 1].c / bars[0].c;
    const years = n / 252;
    const cagr = Math.pow(totalRet, 1 / years) - 1;
    // QQ data: sorted standardized rets vs theoretical normal quantiles
    const sorted = [...rets].sort((a, b) => a - b);
    const qq = sorted.map((r, i) => ({
      theo: probit((i + 0.5) / sorted.length),
      sample: (r - mean) / sd
    }));
    // VaR/CVaR 95%
    const sortedAsc = sorted;
    const varIdx = Math.floor(0.05 * sortedAsc.length);
    const var95 = sortedAsc[varIdx];
    const cvar95 = sortedAsc.slice(0, varIdx + 1).reduce((a, b) => a + b, 0) / (varIdx + 1);
    return {
      annMean: +(mean * 252 * 100).toFixed(1),
      annVol: +(sd * Math.sqrt(252) * 100).toFixed(1),
      sharpe: +((mean / sd) * Math.sqrt(252)).toFixed(2),
      sortino: +((mean / downside) * Math.sqrt(252)).toFixed(2),
      cagr: +(cagr * 100).toFixed(1),
      maxDD: +(maxDD * 100).toFixed(1),
      skew: +skew.toFixed(2),
      kurt: +kurt.toFixed(2),
      acf1: +acf1.toFixed(3),
      acf5: +acf5.toFixed(3),
      acf20: +acf20.toFixed(3),
      var95: +(var95 * 100).toFixed(2),
      cvar95: +(cvar95 * 100).toFixed(2),
      bestDay: +(Math.max(...rets) * 100).toFixed(2),
      worstDay: +(Math.min(...rets) * 100).toFixed(2),
      rollVol,
      qq,
      rets
    };
  }

  const assets = [
    { name: "Bitcoin", ticker: "BTC", kind: "spot", seed: 1, mu: 0.55, sigma: 0.62, basePrice: 16500 },
    { name: "Ethereum", ticker: "ETH", kind: "spot", seed: 2, mu: 0.42, sigma: 0.74, basePrice: 1200 },
    { name: "Solana", ticker: "SOL", kind: "spot", seed: 3, mu: 0.85, sigma: 1.05, basePrice: 11 },
    { name: "Arbitrum", ticker: "ARB", kind: "spot", seed: 4, mu: -0.20, sigma: 0.95, basePrice: 1.8 },
    { name: "Optimism", ticker: "OP", kind: "spot", seed: 5, mu: 0.10, sigma: 1.10, basePrice: 2.6 },
    { name: "BTC Perp", ticker: "BTC-PERP", kind: "perp", seed: 6, mu: 0.50, sigma: 0.65, basePrice: 16500 }
  ].map(a => genAsset(a));

  assets.forEach(a => { a.stats = computeAssetStats(a); });

  // ============ SAVED STRATEGIES LIBRARY ============
  // Build a library from runs + some "archived" entries
  const archivedStrategies = [
    {
      id: "lib-a1", name: "rsi-extremes-1h", strategy: "mean-reversion",
      author: "you", created: "2024-09-12", tags: ["mean-rev", "rsi"],
      starred: true, status: "live",
      metrics: { sharpe: 1.32, cagr: 18.4, maxDD: -8.6, pf: 1.62, trades: 284 },
      desc: "Long su RSI<20, short su RSI>80. Filtro trend EMA200."
    },
    {
      id: "lib-a2", name: "donchian-breakout-4h", strategy: "breakout",
      author: "you", created: "2024-07-22", tags: ["trend", "breakout"],
      starred: false, status: "archived",
      metrics: { sharpe: 1.18, cagr: 14.2, maxDD: -11.4, pf: 1.51, trades: 156 },
      desc: "Breakout dei 20-bar high/low con ATR stop."
    },
    {
      id: "lib-a3", name: "funding-arb-perp", strategy: "carry",
      author: "you", created: "2024-11-03", tags: ["crypto", "funding", "neutral"],
      starred: true, status: "research",
      metrics: { sharpe: 2.21, cagr: 11.8, maxDD: -3.2, pf: 2.84, trades: 624 },
      desc: "Long spot / short perp quando funding > soglia."
    },
    {
      id: "lib-a4", name: "pairs-eth-btc", strategy: "stat-arb",
      author: "team", created: "2024-05-18", tags: ["pairs", "z-score"],
      starred: false, status: "archived",
      metrics: { sharpe: 0.94, cagr: 8.1, maxDD: -6.8, pf: 1.34, trades: 412 },
      desc: "Z-score sullo spread ETH/BTC, entry a ±2σ, exit a 0."
    },
    {
      id: "lib-a5", name: "vol-target-btc", strategy: "vol-target",
      author: "you", created: "2025-01-14", tags: ["risk", "scaling"],
      starred: false, status: "research",
      metrics: { sharpe: 1.08, cagr: 12.5, maxDD: -7.4, pf: 1.42, trades: 88 },
      desc: "Long BTC, esposizione scalata a target vol 15%."
    }
  ];

  // turn current runs into library entries too
  const runLibEntries = runs.map((r, i) => ({
    id: `lib-${r.id}`,
    name: r.name,
    strategy: r.strategy,
    author: "you",
    created: ["2025-03-02", "2025-04-11", "2025-04-28", "2025-05-12"][i] || "2025-05-01",
    tags: [r.strategy.split("-")[0], "active"],
    starred: i === 0,
    status: "live",
    metrics: {
      sharpe: r.metricsOOS.sharpe,
      cagr: r.metricsOOS.cagr,
      maxDD: r.metricsOOS.maxDD,
      pf: r.profitFactor,
      trades: r.tradesCount
    },
    desc: `${r.strategy} on ${r.params.universe.join(", ")} @ ${r.params.timeframe}.`,
    runRef: r.id,
    sparkline: r.equity.filter((_, i) => i % 16 === 0).map(e => e.v)
  }));

  const library = [...runLibEntries, ...archivedStrategies];

  window.ParetoData = {
    runs,
    assets,
    library,
    activeRunId: "r1",
    benchmarks: ["BTC HODL", "60/40", "EQUAL-WEIGHT TOP10"],
    _helpers: { genAsset, computeAssetStats, mulberry32, gauss }
  };
})();
