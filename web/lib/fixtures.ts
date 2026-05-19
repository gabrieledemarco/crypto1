// PARETO fixture data — deterministic seeded RNG port from pareto-data.js

// ── TypeScript interfaces ────────────────────────────────────────────────────

export interface EquityPoint {
  i: number;
  v: number;
  bench: number;
  dd: number;
  oos: boolean;
}

export interface Trade {
  n: number;
  idx: number;
  date: number;
  side: "L" | "S";
  entry: number;
  exit: number;
  r: number;
  durH: number;
  pnl: number;
  equity: number;
}

export interface DDPeriod {
  start: number;
  trough: number;
  end: number;
  depth: number;
  length: number;
  recovery: number;
  ongoing?: boolean;
}

export interface RunMetrics {
  sharpe: number;
  sortino: number;
  cagr: number;
  maxDD: number;
  calmar: number;
  finalReturn: number;
  omega?: number;
  ulcer?: number;
  recoveryFactor?: number;
}

export interface Run {
  id: string;
  name: string;
  strategy: string;
  color: string;
  equity: EquityPoint[];
  oosStart: number;
  trades: Trade[];
  params: RunParams;
  dates: RunDates;
  metricsIS: RunMetrics;
  metricsOOS: RunMetrics;
  ddPeriods: DDPeriod[];
  sweep: number[][];
  mc: MCData;
  winRate: number;
  profitFactor: number;
  tradesCount: number;
  avgDur: number;
  exposure: number;
  monthly: MonthlyBucket[];
}

export interface RunParams {
  fastMA: number;
  slowMA: number;
  atrStop: number;
  takeProfit: number;
  riskPerTrade: number;
  fees: number;
  slippage: number;
  funding: boolean;
  universe: string[];
  timeframe: string;
}

export interface RunDates {
  isStart: string;
  isEnd: string;
  oosStart: string;
  oosEnd: string;
}

export interface MCData {
  paths: number[][];
  percentiles: {
    p5: number[];
    p25: number[];
    p50: number[];
    p75: number[];
    p95: number[];
  };
  finals: number[];
  ddFinals: number[];
}

export interface MonthlyBucket {
  idx: number;
  pnl: number;
}

export interface QQPoint {
  theo: number;
  sample: number;
}

export interface AssetStats {
  annMean: number;
  annVol: number;
  sharpe: number;
  sortino: number;
  cagr: number;
  maxDD: number;
  skew: number;
  kurt: number;
  acf1: number;
  acf5: number;
  acf20: number;
  var95: number;
  cvar95: number;
  bestDay: number;
  worstDay: number;
  rollVol: { i: number; v: number }[];
  qq: QQPoint[];
  rets: number[];
}

export interface Asset {
  name: string;
  ticker: string;
  kind: string;
  bars: Bar[];
  basePrice: number;
  stats: AssetStats;
}

export interface Bar {
  i: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
  r: number;
}

export interface LibraryEntry {
  id: string;
  name: string;
  strategy: string;
  author: string;
  created: string;
  tags: string[];
  starred: boolean;
  status: "live" | "research" | "archived";
  metrics: {
    sharpe: number;
    cagr: number;
    maxDD: number;
    pf: number;
    trades: number;
  };
  desc: string;
  runRef?: string;
  sparkline?: number[];
}

export interface ParetoData {
  runs: Run[];
  assets: Asset[];
  library: LibraryEntry[];
  activeRunId: string;
  benchmarks: string[];
}

// ── Seeded RNG ───────────────────────────────────────────────────────────────

function mulberry32(seed: number): () => number {
  let s = seed >>> 0;
  return function () {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) >>> 0;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gauss(rng: () => number): number {
  let u = 0,
    v = 0;
  while (u === 0) u = rng();
  while (v === 0) v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// ── Equity curve generator ───────────────────────────────────────────────────

function genEquity(
  rng: () => number,
  n: number,
  drift: number,
  vol: number,
  oosStart: number
): EquityPoint[] {
  const pts: EquityPoint[] = [];
  let v = 1,
    bench = 1,
    peak = 1;
  for (let i = 0; i < n; i++) {
    const r = drift / 252 + (vol / Math.sqrt(252)) * gauss(rng);
    const rb = 0.0003 + 0.018 * gauss(rng);
    v *= 1 + r;
    bench *= 1 + rb;
    if (v > peak) peak = v;
    const dd = (v - peak) / peak;
    pts.push({ i, v, bench, dd, oos: i >= oosStart });
  }
  return pts;
}

// ── Drawdown period finder ───────────────────────────────────────────────────

function findDDPeriods(equity: EquityPoint[]): DDPeriod[] {
  const periods: DDPeriod[] = [];
  let inDD = false;
  let start = 0,
    trough = 0,
    troughVal = 1,
    peak = 1;

  for (let i = 0; i < equity.length; i++) {
    const { v } = equity[i];
    if (v > peak) {
      if (inDD) {
        periods.push({
          start,
          trough,
          end: i,
          depth: (troughVal - peak) / peak,
          length: i - start,
          recovery: i - trough,
        });
        inDD = false;
      }
      peak = v;
    } else if (v < peak * 0.98 && !inDD) {
      inDD = true;
      start = i;
      trough = i;
      troughVal = v;
    } else if (inDD && v < troughVal) {
      trough = i;
      troughVal = v;
    }
  }
  if (inDD) {
    periods.push({
      start,
      trough,
      end: equity.length - 1,
      depth: (troughVal - peak) / peak,
      length: equity.length - 1 - start,
      recovery: 0,
      ongoing: true,
    });
  }
  return periods;
}

// ── Trade list generator ─────────────────────────────────────────────────────

function genTrades(
  rng: () => number,
  equity: EquityPoint[],
  count: number,
  winRate: number,
  avgWin: number,
  avgLoss: number
): Trade[] {
  const trades: Trade[] = [];
  const n = equity.length;
  let eq = 1;
  const startTs = Date.UTC(2019, 0, 1);
  const dayMs = 86400000;

  for (let k = 0; k < count; k++) {
    const idx = Math.floor(rng() * n);
    const win = rng() < winRate;
    const r = win
      ? avgWin * (0.5 + rng())
      : -avgLoss * (0.5 + rng());
    const durH = Math.floor(2 + rng() * 120);
    const entry = 20000 + rng() * 60000;
    const exit = entry * (1 + r * 0.01);
    const pnl = r * 100;
    eq *= 1 + r * 0.01;
    trades.push({
      n: k + 1,
      idx,
      date: startTs + idx * dayMs,
      side: rng() > 0.5 ? "L" : "S",
      entry,
      exit,
      r,
      durH,
      pnl,
      equity: eq,
    });
  }
  return trades.sort((a, b) => a.idx - b.idx).map((t, i) => ({ ...t, n: i + 1 }));
}

// ── Parameter sweep generator ────────────────────────────────────────────────

function genSweep(rng: () => number, rows: number, cols: number): number[][] {
  const grid: number[][] = [];
  for (let r = 0; r < rows; r++) {
    const row: number[] = [];
    for (let c = 0; c < cols; c++) {
      row.push(-0.5 + rng() * 3);
    }
    grid.push(row);
  }
  return grid;
}

// ── Monte Carlo generator ────────────────────────────────────────────────────

function genMC(
  rng: () => number,
  baseTrades: Trade[],
  paths: number,
  steps: number
): MCData {
  const allPaths: number[][] = [];
  const finals: number[] = [];
  const ddFinals: number[] = [];

  const rets = baseTrades.map((t) => t.r * 0.01);
  const n = rets.length;

  for (let p = 0; p < paths; p++) {
    const path: number[] = [1];
    let v = 1,
      peak = 1,
      maxDD = 0;
    for (let s = 0; s < steps; s++) {
      const r = rets[Math.floor(rng() * n)];
      v *= 1 + r;
      if (v > peak) peak = v;
      const dd = (peak - v) / peak;
      if (dd > maxDD) maxDD = dd;
      path.push(v);
    }
    allPaths.push(path);
    finals.push(v);
    ddFinals.push(maxDD);
  }

  // Compute percentiles at each step
  const pctKeys = [0.05, 0.25, 0.5, 0.75, 0.95] as const;
  const pcts: { [k: number]: number[] } = {};
  for (const k of pctKeys) pcts[k] = [];

  for (let s = 0; s <= steps; s++) {
    const vals = allPaths.map((p) => p[s]).sort((a, b) => a - b);
    for (const k of pctKeys) {
      const idx = Math.floor(k * vals.length);
      pcts[k].push(vals[Math.min(idx, vals.length - 1)]);
    }
  }

  return {
    paths: allPaths,
    percentiles: {
      p5: pcts[0.05],
      p25: pcts[0.25],
      p50: pcts[0.5],
      p75: pcts[0.75],
      p95: pcts[0.95],
    },
    finals,
    ddFinals,
  };
}

// ── Metrics computation ──────────────────────────────────────────────────────

function computeMetrics(equity: EquityPoint[]): RunMetrics {
  if (equity.length < 2)
    return {
      sharpe: 0,
      sortino: 0,
      cagr: 0,
      maxDD: 0,
      calmar: 0,
      finalReturn: 0,
    };

  const rets: number[] = [];
  for (let i = 1; i < equity.length; i++) {
    rets.push(equity[i].v / equity[i - 1].v - 1);
  }

  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const variance = rets.reduce((a, r) => a + (r - mean) ** 2, 0) / rets.length;
  const std = Math.sqrt(variance);
  const downRets = rets.filter((r) => r < 0);
  const downVar = downRets.reduce((a, r) => a + r ** 2, 0) / (downRets.length || 1);
  const downStd = Math.sqrt(downVar);

  const sharpe = std > 0 ? (mean / std) * Math.sqrt(252) : 0;
  const sortino = downStd > 0 ? (mean / downStd) * Math.sqrt(252) : 0;
  const years = equity.length / 252;
  const finalVal = equity[equity.length - 1].v;
  const cagr = years > 0 ? Math.pow(finalVal, 1 / years) - 1 : 0;
  const maxDD = Math.min(...equity.map((p) => p.dd));
  const calmar = maxDD !== 0 ? cagr / Math.abs(maxDD) : 0;
  const finalReturn = finalVal - 1;

  return {
    sharpe: +sharpe.toFixed(3),
    sortino: +sortino.toFixed(3),
    cagr: +cagr.toFixed(4),
    maxDD: +maxDD.toFixed(4),
    calmar: +calmar.toFixed(3),
    finalReturn: +finalReturn.toFixed(4),
  };
}

// ── Monthly P&L buckets ──────────────────────────────────────────────────────

function monthlyPnL(equity: EquityPoint[]): MonthlyBucket[] {
  const buckets: MonthlyBucket[] = [];
  const perMonth = Math.floor(equity.length / 48);
  for (let m = 0; m < 48; m++) {
    const start = m * perMonth;
    const end = Math.min(start + perMonth, equity.length - 1);
    if (start >= equity.length) break;
    const pnl = equity[end].v / equity[start].v - 1;
    buckets.push({ idx: m, pnl: +pnl.toFixed(4) });
  }
  return buckets;
}

// ── Probit (inverse normal CDF approx) ──────────────────────────────────────

function probit(p: number): number {
  // Rational approximation (Abramowitz and Stegun)
  const a = [
    -3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2,
    1.38357751867269e2, -3.066479806614716e1, 2.506628277459239,
  ];
  const b = [
    -5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2,
    6.680131188771972e1, -1.328068155288572e1,
  ];
  const c = [
    -7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838,
    -2.549732539343734, 4.374664141464968, 2.938163982698783,
  ];
  const d = [
    7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996,
    3.754408661907416,
  ];
  const pLow = 0.02425;
  const pHigh = 1 - pLow;

  if (p < pLow) {
    const q = Math.sqrt(-2 * Math.log(p));
    return (
      (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
      ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    );
  } else if (p <= pHigh) {
    const q = p - 0.5;
    const r = q * q;
    return (
      ((((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q) /
      (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    );
  } else {
    const q = Math.sqrt(-2 * Math.log(1 - p));
    return -(
      (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
      ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    );
  }
}

// ── Asset generator ──────────────────────────────────────────────────────────

function genAsset(
  rng: () => number,
  name: string,
  ticker: string,
  kind: string,
  basePrice: number,
  annVol: number,
  annDrift: number,
  n: number
): Asset {
  const bars: Bar[] = [];
  let price = basePrice;
  const dailyVol = annVol / Math.sqrt(252);
  const dailyDrift = annDrift / 252;

  for (let i = 0; i < n; i++) {
    const r = dailyDrift + dailyVol * gauss(rng);
    const o = price;
    const c = price * (1 + r);
    const hi = Math.max(o, c) * (1 + Math.abs(gauss(rng)) * dailyVol * 0.5);
    const lo = Math.min(o, c) * (1 - Math.abs(gauss(rng)) * dailyVol * 0.5);
    const v = Math.floor((1e8 + rng() * 9e8) * (1 + Math.abs(r) * 10));
    bars.push({
      i,
      o: +o.toFixed(2),
      h: +hi.toFixed(2),
      l: +lo.toFixed(2),
      c: +c.toFixed(2),
      v,
      r: +r.toFixed(6),
    });
    price = c;
  }

  return { name, ticker, kind, bars, basePrice, stats: computeAssetStats(bars) };
}

// ── Asset stats ──────────────────────────────────────────────────────────────

function computeAssetStats(bars: Bar[]): AssetStats {
  const rets = bars.map((b) => b.r);
  const n = rets.length;

  const mean = rets.reduce((a, b) => a + b, 0) / n;
  const variance = rets.reduce((a, r) => a + (r - mean) ** 2, 0) / n;
  const std = Math.sqrt(variance);

  const annMean = +(mean * 252).toFixed(4);
  const annVol = +(std * Math.sqrt(252)).toFixed(4);
  const sharpe = std > 0 ? +((mean / std) * Math.sqrt(252)).toFixed(3) : 0;

  const downRets = rets.filter((r) => r < 0);
  const downStd = Math.sqrt(
    downRets.reduce((a, r) => a + r ** 2, 0) / (downRets.length || 1)
  );
  const sortino = downStd > 0 ? +((mean / downStd) * Math.sqrt(252)).toFixed(3) : 0;

  // CAGR
  const years = n / 252;
  const totalRet = rets.reduce((a, r) => a * (1 + r), 1);
  const cagr = +(Math.pow(totalRet, 1 / years) - 1).toFixed(4);

  // Max drawdown
  let peak = 1,
    v = 1,
    maxDD = 0;
  for (const r of rets) {
    v *= 1 + r;
    if (v > peak) peak = v;
    const dd = (peak - v) / peak;
    if (dd > maxDD) maxDD = dd;
  }
  maxDD = +(-maxDD).toFixed(4);

  // Skew
  const skew = +(
    rets.reduce((a, r) => a + ((r - mean) / std) ** 3, 0) /
    n
  ).toFixed(4);

  // Kurt
  const kurt = +(
    rets.reduce((a, r) => a + ((r - mean) / std) ** 4, 0) / n - 3
  ).toFixed(4);

  // ACF helper
  function acf(lag: number): number {
    let num = 0,
      den = 0;
    for (let i = lag; i < n; i++) {
      num += (rets[i] - mean) * (rets[i - lag] - mean);
    }
    for (let i = 0; i < n; i++) {
      den += (rets[i] - mean) ** 2;
    }
    return den !== 0 ? +(num / den).toFixed(4) : 0;
  }

  const acf1 = acf(1);
  const acf5 = acf(5);
  const acf20 = acf(20);

  // VaR / CVaR 95%
  const sorted = [...rets].sort((a, b) => a - b);
  const varIdx = Math.floor(0.05 * n);
  const var95 = +(sorted[varIdx] || 0).toFixed(4);
  const cvar95 = +(
    sorted.slice(0, varIdx + 1).reduce((a, b) => a + b, 0) /
    (varIdx + 1)
  ).toFixed(4);

  const bestDay = +(Math.max(...rets)).toFixed(4);
  const worstDay = +(Math.min(...rets)).toFixed(4);

  // Rolling 30-day vol
  const rollVol: { i: number; v: number }[] = [];
  for (let i = 29; i < n; i += 5) {
    const window = rets.slice(i - 29, i + 1);
    const wMean = window.reduce((a, b) => a + b, 0) / window.length;
    const wStd = Math.sqrt(
      window.reduce((a, r) => a + (r - wMean) ** 2, 0) / window.length
    );
    rollVol.push({ i, v: +(wStd * Math.sqrt(252)).toFixed(4) });
  }

  // QQ plot points
  const qq: QQPoint[] = [];
  const sortedForQQ = [...sorted];
  const qqN = Math.min(100, n);
  const step = Math.floor(n / qqN);
  for (let i = 0; i < qqN; i++) {
    const p = (i + 0.5) / qqN;
    qq.push({
      theo: +(mean + std * probit(p)).toFixed(6),
      sample: +(sortedForQQ[i * step] || 0).toFixed(6),
    });
  }

  return {
    annMean,
    annVol,
    sharpe,
    sortino,
    cagr,
    maxDD,
    skew,
    kurt,
    acf1,
    acf5,
    acf20,
    var95,
    cvar95,
    bestDay,
    worstDay,
    rollVol,
    qq,
    rets,
  };
}

// ── Run builder ──────────────────────────────────────────────────────────────

function buildRun(
  seed: number,
  id: string,
  name: string,
  strategy: string,
  color: string,
  drift: number,
  vol: number,
  totalDays: number,
  oosRatio: number,
  tradeCount: number,
  winRate: number,
  params: RunParams
): Run {
  const rng = mulberry32(seed);
  const oosStart = Math.floor(totalDays * (1 - oosRatio));
  const equity = genEquity(rng, totalDays, drift, vol, oosStart);

  const isEquity = equity.slice(0, oosStart);
  const oosEquity = equity.slice(oosStart);

  const metricsIS = computeMetrics(isEquity);
  const metricsOOS = computeMetrics(oosEquity);

  const trades = genTrades(
    mulberry32(seed + 1),
    equity,
    tradeCount,
    winRate,
    2.1,
    1.0
  );

  const winners = trades.filter((t) => t.r > 0);
  const losers = trades.filter((t) => t.r <= 0);
  const grossProfit = winners.reduce((a, t) => a + t.pnl, 0);
  const grossLoss = Math.abs(losers.reduce((a, t) => a + t.pnl, 0));
  const profitFactor = grossLoss > 0 ? +(grossProfit / grossLoss).toFixed(3) : 99;

  const avgDur =
    trades.length > 0
      ? +(trades.reduce((a, t) => a + t.durH, 0) / trades.length).toFixed(1)
      : 0;

  const ddPeriods = findDDPeriods(equity);
  const sweep = genSweep(mulberry32(seed + 2), 12, 12);
  const mc = genMC(mulberry32(seed + 3), trades, 200, 252);
  const monthly = monthlyPnL(equity);

  const startDate = new Date(Date.UTC(2019, 0, 1));
  const oosDate = new Date(startDate.getTime() + oosStart * 86400000);
  const endDate = new Date(startDate.getTime() + totalDays * 86400000);

  const fmt = (d: Date) => d.toISOString().slice(0, 10);

  return {
    id,
    name,
    strategy,
    color,
    equity,
    oosStart,
    trades,
    params,
    dates: {
      isStart: fmt(startDate),
      isEnd: fmt(oosDate),
      oosStart: fmt(oosDate),
      oosEnd: fmt(endDate),
    },
    metricsIS,
    metricsOOS,
    ddPeriods,
    sweep,
    mc,
    winRate,
    profitFactor,
    tradesCount: trades.length,
    avgDur,
    exposure: +(0.3 + (seed % 7) * 0.05).toFixed(2),
    monthly,
  };
}

// ── Library sparkline ────────────────────────────────────────────────────────

function makeSparkline(rng: () => number, n: number): number[] {
  const pts: number[] = [1];
  let v = 1;
  for (let i = 1; i < n; i++) {
    v *= 1 + (gauss(rng) * 0.04 + 0.001);
    pts.push(+v.toFixed(4));
  }
  return pts;
}

// ── Assemble fixture data ────────────────────────────────────────────────────

const baseParams: RunParams = {
  fastMA: 20,
  slowMA: 80,
  atrStop: 2.5,
  takeProfit: 4.0,
  riskPerTrade: 0.01,
  fees: 0.0006,
  slippage: 0.0002,
  funding: true,
  universe: ["BTC", "ETH", "SOL"],
  timeframe: "4h",
};

const runs: Run[] = [
  buildRun(
    42,
    "run-001",
    "Momentum v2.1",
    "MA Crossover + ATR Stop",
    "#ffb53b",
    0.28,
    0.75,
    1826,
    0.25,
    412,
    0.56,
    { ...baseParams, fastMA: 20, slowMA: 80 }
  ),
  buildRun(
    137,
    "run-002",
    "Mean Rev v1.3",
    "Bollinger + RSI",
    "#5cc1ff",
    0.18,
    0.62,
    1826,
    0.25,
    687,
    0.52,
    {
      ...baseParams,
      fastMA: 10,
      slowMA: 50,
      atrStop: 1.8,
      universe: ["BTC", "ETH"],
      timeframe: "1h",
    }
  ),
  buildRun(
    999,
    "run-003",
    "Breakout v3.0",
    "Donchian Channel",
    "#6fd17a",
    0.35,
    0.82,
    1826,
    0.25,
    298,
    0.48,
    {
      ...baseParams,
      fastMA: 5,
      slowMA: 20,
      atrStop: 3.0,
      takeProfit: 6.0,
      universe: ["BTC", "ETH", "SOL", "BNB"],
    }
  ),
  buildRun(
    1337,
    "run-004",
    "Trend v4.2",
    "EMA + MACD",
    "#ff7a55",
    0.22,
    0.7,
    1826,
    0.25,
    523,
    0.54,
    {
      ...baseParams,
      fastMA: 12,
      slowMA: 26,
      timeframe: "1d",
      universe: ["BTC"],
    }
  ),
  buildRun(
    2718,
    "run-005",
    "Carry v1.0",
    "Funding Rate Arb",
    "#ffd84a",
    0.14,
    0.45,
    1826,
    0.25,
    1203,
    0.58,
    {
      ...baseParams,
      fastMA: 3,
      slowMA: 10,
      atrStop: 1.2,
      funding: true,
      universe: ["BTC", "ETH"],
      timeframe: "1h",
    }
  ),
];

const rngAsset = mulberry32(77777);

const assets: Asset[] = [
  genAsset(mulberry32(1001), "Bitcoin", "BTC", "spot", 30000, 0.72, 0.6, 1826),
  genAsset(mulberry32(1002), "Ethereum", "ETH", "spot", 2000, 0.85, 0.55, 1826),
  genAsset(mulberry32(1003), "Solana", "SOL", "spot", 80, 1.1, 0.8, 1826),
  genAsset(mulberry32(1004), "BNB", "BNB", "spot", 300, 0.78, 0.5, 1826),
  genAsset(mulberry32(1005), "Avalanche", "AVAX", "spot", 30, 1.2, 0.7, 1826),
  genAsset(mulberry32(1006), "Chainlink", "LINK", "spot", 15, 0.95, 0.45, 1826),
];

void rngAsset; // suppress unused warning

const libraryRng = mulberry32(55555);

const library: LibraryEntry[] = [
  {
    id: "lib-001",
    name: "Momentum v2.1",
    strategy: "MA Crossover + ATR Stop",
    author: "sys",
    created: "2024-01-15",
    tags: ["momentum", "trend", "btc"],
    starred: true,
    status: "live",
    metrics: { sharpe: 1.82, cagr: 0.312, maxDD: -0.187, pf: 1.94, trades: 412 },
    desc: "Dual MA crossover with dynamic ATR-based stops. Optimized on BTC/ETH 4H.",
    runRef: "run-001",
    sparkline: makeSparkline(mulberry32(10001), 40),
  },
  {
    id: "lib-002",
    name: "Mean Rev v1.3",
    strategy: "Bollinger + RSI",
    author: "sys",
    created: "2024-02-20",
    tags: ["mean-reversion", "oscillator"],
    starred: false,
    status: "research",
    metrics: { sharpe: 1.43, cagr: 0.218, maxDD: -0.142, pf: 1.67, trades: 687 },
    desc: "Bollinger band mean reversion filtered by RSI divergence on 1H.",
    runRef: "run-002",
    sparkline: makeSparkline(mulberry32(10002), 40),
  },
  {
    id: "lib-003",
    name: "Breakout v3.0",
    strategy: "Donchian Channel",
    author: "sys",
    created: "2024-03-10",
    tags: ["breakout", "multi-asset"],
    starred: true,
    status: "research",
    metrics: { sharpe: 1.95, cagr: 0.387, maxDD: -0.223, pf: 2.12, trades: 298 },
    desc: "Donchian channel breakout across 4 assets with portfolio-level sizing.",
    runRef: "run-003",
    sparkline: makeSparkline(mulberry32(10003), 40),
  },
  {
    id: "lib-004",
    name: "Trend v4.2",
    strategy: "EMA + MACD",
    author: "sys",
    created: "2024-04-05",
    tags: ["trend", "daily"],
    starred: false,
    status: "archived",
    metrics: { sharpe: 1.31, cagr: 0.241, maxDD: -0.198, pf: 1.55, trades: 523 },
    desc: "Classic EMA/MACD combo on daily BTC. Simple but battle-tested.",
    runRef: "run-004",
    sparkline: makeSparkline(mulberry32(10004), 40),
  },
  {
    id: "lib-005",
    name: "Carry v1.0",
    strategy: "Funding Rate Arb",
    author: "sys",
    created: "2024-05-12",
    tags: ["carry", "funding", "low-vol"],
    starred: false,
    status: "live",
    metrics: { sharpe: 2.14, cagr: 0.156, maxDD: -0.072, pf: 2.45, trades: 1203 },
    desc: "Funding rate arbitrage capturing persistent positive funding on perps.",
    runRef: "run-005",
    sparkline: makeSparkline(mulberry32(10005), 40),
  },
  {
    id: "lib-006",
    name: "Stat Arb v0.9",
    strategy: "Pair Trading",
    author: "sys",
    created: "2024-06-01",
    tags: ["stat-arb", "pairs", "beta"],
    starred: false,
    status: "research",
    metrics: { sharpe: 1.68, cagr: 0.189, maxDD: -0.108, pf: 1.78, trades: 891 },
    desc: "BTC/ETH spread mean reversion. Cointegration-based entry/exit.",
    runRef: undefined,
    sparkline: makeSparkline(mulberry32(10006), 40),
  },
];

void libraryRng; // suppress unused warning

export const fixtures: ParetoData = {
  runs,
  assets,
  library,
  activeRunId: "run-001",
  benchmarks: ["BTC", "ETH"],
};
