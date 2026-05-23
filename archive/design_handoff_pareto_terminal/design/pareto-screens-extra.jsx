/* PARETO — Extra screens: Assets, Library, Vibe Trading */
const Cx = window.PARETO_C;

// =================================================================
// ASSETS — historical series + quant statistical analysis
// =================================================================

// Build a deterministic asset spec from a ticker + data source
function buildAssetMeta(ticker, source) {
  // hash ticker to a stable seed
  let h = 0;
  for (let i = 0; i < ticker.length; i++) h = ((h << 5) - h + ticker.charCodeAt(i)) | 0;
  const seed = Math.abs(h) || 1;
  // derive plausible mu/sigma/basePrice from ticker characteristics
  const isCrypto = /(BTC|ETH|SOL|DOGE|AVAX|MATIC|ARB|OP|XRP|ADA|LTC|LINK|BCH)/.test(ticker);
  const isFX = /^[A-Z]{6}$/.test(ticker) || /USD|EUR|JPY|GBP|CHF/.test(ticker) && ticker.length <= 7;
  const isCommodity = /(GLD|SLV|USO|UNG|DBA|XLE|XLU)/.test(ticker);
  const isETF = /(SPY|QQQ|IWM|DIA|TLT|HYG|LQD|VTI|EEM)/.test(ticker);
  const isMega = /(AAPL|MSFT|GOOGL|GOOG|AMZN|META|TSLA|NVDA|MSTR|COIN|SQ)/.test(ticker);
  let mu, sigma, basePrice;
  const rnd01 = (((seed * 9301 + 49297) % 233280) / 233280);
  const rnd02 = (((seed * 1103515 + 12345) % 233280) / 233280);
  if (isCrypto) { mu = 0.3 + rnd01 * 0.6; sigma = 0.6 + rnd02 * 0.5; basePrice = 50 + rnd01 * 4000; }
  else if (isFX) { mu = -0.02 + rnd01 * 0.08; sigma = 0.06 + rnd02 * 0.06; basePrice = 1 + rnd01 * 0.6; }
  else if (isCommodity) { mu = 0.05 + rnd01 * 0.15; sigma = 0.15 + rnd02 * 0.15; basePrice = 30 + rnd01 * 150; }
  else if (isETF) { mu = 0.08 + rnd01 * 0.12; sigma = 0.14 + rnd02 * 0.12; basePrice = 80 + rnd01 * 350; }
  else if (isMega) { mu = 0.18 + rnd01 * 0.35; sigma = 0.28 + rnd02 * 0.25; basePrice = 50 + rnd01 * 400; }
  else { mu = 0.05 + rnd01 * 0.25; sigma = 0.22 + rnd02 * 0.30; basePrice = 20 + rnd01 * 200; }
  return {
    name: ticker, ticker,
    kind: isCrypto ? "spot" : isFX ? "fx" : isETF ? "etf" : isCommodity ? "comm" : "equity",
    seed, mu, sigma, basePrice
  };
}

function hydrateCustomAsset(meta, helpers) {
  const a = helpers.genAsset(meta);
  a.stats = helpers.computeAssetStats(a);
  a.source = meta.source;
  a.seed = meta.seed;
  a.mu = meta.mu;
  a.sigma = meta.sigma;
  a.basePrice = meta.basePrice;
  a.custom = true;
  return a;
}

function AssetsScreen() {
  const baseAssets = window.ParetoData.assets;
  const helpers = window.ParetoData._helpers;
  const [customAssets, setCustomAssets] = useState(() => {
    try {
      const raw = localStorage.getItem("pareto-custom-assets");
      if (!raw) return [];
      const meta = JSON.parse(raw);
      return meta.map(m => hydrateCustomAsset(m, helpers));
    } catch (e) { return []; }
  });
  const assets = useMemo(() => [...baseAssets, ...customAssets], [baseAssets, customAssets]);
  const [selId, setSelId] = useState(assets[0].ticker);
  const asset = assets.find(a => a.ticker === selId) || assets[0];
  const stats = asset.stats;
  const [view, setView] = useState("price");

  const [addOpen, setAddOpen] = useState(false);
  const [addTicker, setAddTicker] = useState("");
  const [addSource, setAddSource] = useState("yfinance");
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState(null);

  const persistCustom = (next) => {
    setCustomAssets(next);
    try {
      const meta = next.map(a => ({ ticker: a.ticker, name: a.name, source: a.source, kind: a.kind, seed: a.seed, mu: a.mu, sigma: a.sigma, basePrice: a.basePrice }));
      localStorage.setItem("pareto-custom-assets", JSON.stringify(meta));
    } catch (e) {}
  };

  const removeCustom = (ticker) => {
    const next = customAssets.filter(a => a.ticker !== ticker);
    persistCustom(next);
    if (selId === ticker) setSelId(baseAssets[0].ticker);
  };

  const doFetch = async (rawTicker, source) => {
    const ticker = rawTicker.trim().toUpperCase();
    if (!ticker) return;
    if (assets.some(a => a.ticker === ticker)) {
      setAddError("ticker già presente");
      return;
    }
    setAddLoading(true);
    setAddError(null);
    // mock network latency
    await new Promise(r => setTimeout(r, 700 + Math.random() * 500));
    const meta = buildAssetMeta(ticker, source);
    const generated = helpers.genAsset(meta);
    generated.stats = helpers.computeAssetStats(generated);
    generated.source = source;
    generated.seed = meta.seed;
    generated.mu = meta.mu;
    generated.sigma = meta.sigma;
    generated.basePrice = meta.basePrice;
    generated.custom = true;
    const next = [...customAssets, generated];
    persistCustom(next);
    setAddLoading(false);
    setAddTicker("");
    setAddOpen(false);
    setSelId(ticker);
  };

  const quickPicks = ["AAPL", "TSLA", "SPY", "NVDA", "GLD", "EURUSD", "TLT", "QQQ", "MSTR"];

  // y values for chart
  const priceSeries = useMemo(() => asset.bars.map(b => ({ i: b.i, v: b.c, bench: asset.bars[0].c, dd: 0, oos: false })), [asset]);
  const retSeries = useMemo(() => asset.bars.slice(1).map((b, i) => ({ i, v: 1 + b.r, bench: 1, dd: 0, oos: false })), [asset]);

  return (
    <div className="grid-12" style={{ gap: 6 }}>
      {/* Top selector strip */}
      <Panel title="UNIVERSE" sub="select asset · add yfinance / alpaca" style={{ gridColumn: "span 12" }}>
        <div className="row" style={{ gap: 6, flexWrap: "wrap", alignItems: "stretch" }}>
          {assets.map(a => (
            <button key={a.ticker}
              className={`asset-card ${selId === a.ticker ? "on" : ""} ${a.custom ? "asset-custom" : ""}`}
              onClick={() => setSelId(a.ticker)}>
              <div className="row" style={{ alignItems: "baseline", gap: 6, width: "100%" }}>
                <span className="asset-ticker">{a.ticker}</span>
                {a.source && <span className="asset-source">{a.source}</span>}
                {a.custom && (
                  <span className="asset-x" title="rimuovi"
                    onClick={(e) => { e.stopPropagation(); removeCustom(a.ticker); }}>×</span>
                )}
              </div>
              <span className="asset-name lbl-mono dim">{a.name}</span>
              <span className="row" style={{ gap: 6 }}>
                <span className="mono" style={{ color: a.stats.cagr > 0 ? Cx.green : Cx.coral, fontWeight: 700 }}>
                  {a.stats.cagr > 0 ? "+" : ""}{a.stats.cagr}%
                </span>
                <span className="mono dim">σ {a.stats.annVol}%</span>
              </span>
              <Sparkline data={a.bars.filter((_, i) => i % 12 === 0).map(b => b.c)} width={80} height={18}
                color={a.stats.cagr > 0 ? Cx.green : Cx.coral} />
            </button>
          ))}
          <button
            className={`asset-add ${addOpen ? "on" : ""}`}
            onClick={() => setAddOpen(o => !o)}>
            <span className="asset-add-plus">+</span>
            <span className="asset-add-lbl">ADD ASSET</span>
            <span className="lbl-mono dim">yfinance · alpaca</span>
          </button>
        </div>

        {addOpen && (
          <div className="asset-add-form">
            <div className="row" style={{ gap: 6, alignItems: "center" }}>
              <span className="lbl-mono dim">source:</span>
              {["yfinance", "alpaca", "binance"].map(s => (
                <Pill key={s} active={addSource === s} onClick={() => setAddSource(s)}>{s}</Pill>
              ))}
              <span style={{ width: 12 }}></span>
              <input
                className="asset-add-input"
                placeholder="ticker · es. AAPL, TSLA, EURUSD, BTC"
                value={addTicker}
                onChange={e => { setAddTicker(e.target.value); setAddError(null); }}
                onKeyDown={e => { if (e.key === "Enter" && !addLoading) doFetch(addTicker, addSource); }}
                autoFocus
              />
              <button className="btn btn-primary"
                disabled={addLoading || !addTicker.trim()}
                onClick={() => doFetch(addTicker, addSource)}>
                {addLoading ? "FETCH…" : "▸ FETCH"}
              </button>
              <button className="btn" onClick={() => { setAddOpen(false); setAddError(null); }}>esc</button>
            </div>
            {addError && (
              <div className="warn" style={{ marginTop: 8 }}>⚠ {addError}</div>
            )}
            <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
              <span className="lbl-mono dim">quick:</span>
              {quickPicks.map(t => (
                <Pill key={t} onClick={() => doFetch(t, addSource)}>{t}</Pill>
              ))}
            </div>
            <div className="lbl-mono dim" style={{ marginTop: 8, fontStyle: "italic" }}>
              mock client-side · genera serie deterministica dal ticker. in produzione: chiama l'endpoint del provider scelto.
            </div>
          </div>
        )}
      </Panel>

      {/* Price/returns time-series */}
      <Panel
        title={view === "price" ? `${asset.ticker} · PRICE` : `${asset.ticker} · LOG RETURNS`}
        sub={`${asset.bars.length} daily bars`}
        right={
          <span className="row" style={{ gap: 4 }}>
            <Pill active={view === "price"} onClick={() => setView("price")}>PRICE</Pill>
            <Pill active={view === "logret"} onClick={() => setView("logret")}>LOG-RET</Pill>
          </span>
        }
        style={{ gridColumn: "span 8" }}>
        {view === "price" ? (
          <PriceChart bars={asset.bars} height={220} />
        ) : (
          <ReturnsChart rets={stats.rets} height={220} />
        )}
        <div className="lbl-mono dim" style={{ marginTop: 6 }}>
          last close <b className="mono" style={{ color: Cx.amber }}>{asset.bars[asset.bars.length - 1].c.toFixed(2)}</b>
          &nbsp;·&nbsp; range&nbsp;
          <span className="mono" style={{ color: Cx.coral }}>{Math.min(...asset.bars.map(b => b.l)).toFixed(2)}</span> →
          <span className="mono" style={{ color: Cx.green }}> {Math.max(...asset.bars.map(b => b.h)).toFixed(2)}</span>
        </div>
      </Panel>

      {/* Headline stats */}
      <Panel title="QUANT STATS" sub="annualized" style={{ gridColumn: "span 4" }}>
        <div className="metric-grid">
          <MetricBlock label="CAGR" value={(stats.cagr > 0 ? "+" : "") + stats.cagr + "%"} color={stats.cagr > 0 ? Cx.green : Cx.coral} big />
          <MetricBlock label="VOL" value={stats.annVol + "%"} color={Cx.amber} big />
          <MetricBlock label="SHARPE" value={stats.sharpe} color={Cx.amber} big />
          <MetricBlock label="MAX DD" value={stats.maxDD + "%"} color={Cx.coral} />
          <MetricBlock label="SKEW" value={stats.skew} color={Math.abs(stats.skew) > 0.5 ? Cx.coral : Cx.dim}
            sub={stats.skew < -0.3 ? "left-tailed" : stats.skew > 0.3 ? "right-tailed" : "near-symm"} />
          <MetricBlock label="EXC KURT" value={stats.kurt} color={stats.kurt > 2 ? Cx.coral : Cx.dim}
            sub={stats.kurt > 3 ? "fat tails" : "normal-ish"} />
          <MetricBlock label="VaR 95" value={stats.var95 + "%"} color={Cx.coral} />
          <MetricBlock label="CVaR 95" value={stats.cvar95 + "%"} color={Cx.coral} />
          <MetricBlock label="BEST DAY" value={"+" + stats.bestDay + "%"} color={Cx.green} />
        </div>
      </Panel>

      {/* Return distribution */}
      <Panel title="LOG-RETURN DISTRIBUTION" sub="vs normal overlay" style={{ gridColumn: "span 5" }}>
        <ReturnHistogram rets={stats.rets} height={160} />
        <div className="row" style={{ gap: 12, marginTop: 8, flexWrap: "wrap" }}>
          <span className="lbl-mono">
            <span className="dim">skew </span><b style={{ color: Cx.amber }}>{stats.skew}</b>
          </span>
          <span className="lbl-mono">
            <span className="dim">kurt+3 </span><b style={{ color: Cx.amber }}>{(stats.kurt + 3).toFixed(2)}</b>
          </span>
          <span className="lbl-mono">
            <span className="dim">N(0,σ²) </span><span style={{ color: Cx.coral }}>—— overlay tratteggiato</span>
          </span>
        </div>
        {stats.kurt > 2 && (
          <div className="warn" style={{ marginTop: 8 }}>
            ⚠ kurtosi alta · code grasse · attenzione a leverage e stop ravvicinati
          </div>
        )}
      </Panel>

      {/* QQ plot */}
      <Panel title="QQ PLOT · vs normal" sub="quantili sample vs teorici" style={{ gridColumn: "span 4" }}>
        <QQPlot qq={stats.qq} height={200} />
        <div className="lbl-mono dim" style={{ marginTop: 6 }}>
          punti che curvano alle estremità → code non-normali
        </div>
      </Panel>

      {/* ACF */}
      <Panel title="ACF · autocorrelazione" sub="lags 1..30" style={{ gridColumn: "span 3" }}>
        <ACFChart rets={stats.rets} height={200} maxLag={30} n={stats.rets.length} />
        <div className="lbl-mono dim" style={{ marginTop: 6 }}>
          fuori dalle bande ≈ ±2/√n → memoria
        </div>
      </Panel>

      {/* Rolling volatility */}
      <Panel title="ROLLING VOL · 21-day annualized" sub={`mean ${stats.annVol}%`} style={{ gridColumn: "span 12" }}>
        <RollingVolChart rollVol={stats.rollVol} height={140} mean={stats.annVol} />
      </Panel>
    </div>
  );
}

// Sub-charts for assets screen
function PriceChart({ bars, height = 200 }) {
  const wrap = useRef(null);
  const [w, setW] = useState(800);
  const [hover, setHover] = useState(null);
  useEffect(() => {
    const ro = new ResizeObserver(es => { if (es[0]) setW(es[0].contentRect.width); });
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  const padL = 52, padR = 12, padT = 8, padB = 18;
  const innerW = Math.max(50, w - padL - padR);
  const innerH = height - padT - padB;
  const vs = bars.map(b => b.c);
  const lows = bars.map(b => b.l);
  const highs = bars.map(b => b.h);
  const mn = Math.min(...lows) * 0.98;
  const mx = Math.max(...highs) * 1.02;
  const lmn = Math.log(mn), lmx = Math.log(mx);
  const yScale = (v) => padT + innerH - ((Math.log(v) - lmn) / (lmx - lmn)) * innerH;
  const xScale = (i) => padL + (i / (bars.length - 1)) * innerW;
  const pts = bars.map(b => [xScale(b.i), yScale(b.c)]);
  const handleMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const i = clamp(Math.round((x - padL) / (innerW / (bars.length - 1))), 0, bars.length - 1);
    setHover({ i, x: xScale(i), y: yScale(bars[i].c), bar: bars[i] });
  };
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(q => Math.exp(lmn + (lmx - lmn) * q));
  return (
    <div ref={wrap} style={{ position: "relative", width: "100%", height }}>
      <svg width={w} height={height} onMouseMove={handleMove} onMouseLeave={() => setHover(null)}
        style={{ display: "block", cursor: "crosshair" }}>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={padL + innerW} y1={yScale(t)} y2={yScale(t)} stroke={Cx.border} strokeDasharray="2 4" />
            <text x={padL - 6} y={yScale(t) + 3} fill={Cx.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">
              {t > 1000 ? (t / 1000).toFixed(1) + "k" : t.toFixed(2)}
            </text>
          </g>
        ))}
        <path d={lineFromPoints(pts)} fill="none" stroke={Cx.amber} strokeWidth="1.6" />
        {hover && (
          <g pointerEvents="none">
            <line x1={hover.x} x2={hover.x} y1={padT} y2={padT + innerH} stroke={Cx.borderL} strokeDasharray="3 3" />
            <circle cx={hover.x} cy={hover.y} r="3" fill={Cx.amber} stroke={Cx.bg} strokeWidth="1.5" />
          </g>
        )}
      </svg>
      {hover && (
        <div style={{
          position: "absolute", left: clamp(hover.x + 10, 8, w - 150), top: clamp(hover.y - 40, 8, height - 60),
          background: Cx.panel2, border: `1px solid ${Cx.borderL}`,
          padding: "4px 8px", font: "11px JetBrains Mono", color: Cx.text, pointerEvents: "none", lineHeight: 1.4
        }}>
          <div style={{ color: Cx.faint }}>t {hover.i}</div>
          <div style={{ color: Cx.amber }}>close <b>{hover.bar.c.toFixed(2)}</b></div>
          <div style={{ color: hover.bar.r > 0 ? Cx.green : Cx.coral }}>ret <b>{(hover.bar.r * 100).toFixed(2)}%</b></div>
        </div>
      )}
    </div>
  );
}

function ReturnsChart({ rets, height = 200 }) {
  const wrap = useRef(null);
  const [w, setW] = useState(800);
  useEffect(() => {
    const ro = new ResizeObserver(es => { if (es[0]) setW(es[0].contentRect.width); });
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  const padL = 44, padR = 12, padT = 8, padB = 18;
  const innerW = Math.max(50, w - padL - padR);
  const innerH = height - padT - padB;
  const absMax = Math.max(...rets.map(r => Math.abs(r))) * 1.05;
  const yScale = (v) => padT + innerH / 2 - (v / absMax) * (innerH / 2);
  const xScale = (i) => padL + (i / (rets.length - 1)) * innerW;
  return (
    <div ref={wrap} style={{ width: "100%", height }}>
      <svg width={w} height={height} style={{ display: "block" }}>
        <line x1={padL} x2={padL + innerW} y1={padT + innerH / 2} y2={padT + innerH / 2} stroke={Cx.borderL} />
        <text x={padL - 6} y={padT + 4} fill={Cx.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">+{(absMax * 100).toFixed(1)}%</text>
        <text x={padL - 6} y={padT + innerH + 2} fill={Cx.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">-{(absMax * 100).toFixed(1)}%</text>
        {rets.map((r, i) => (
          <line key={i} x1={xScale(i)} x2={xScale(i)}
            y1={padT + innerH / 2} y2={yScale(r)}
            stroke={r >= 0 ? Cx.green : Cx.coral} strokeWidth={Math.max(0.5, innerW / rets.length * 0.7)} opacity="0.8" />
        ))}
      </svg>
    </div>
  );
}

function ReturnHistogram({ rets, height = 160 }) {
  const wrap = useRef(null);
  const [w, setW] = useState(800);
  useEffect(() => {
    const ro = new ResizeObserver(es => { if (es[0]) setW(es[0].contentRect.width); });
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  const padL = 6, padR = 6, padT = 8, padB = 16;
  const innerW = Math.max(40, w - padL - padR);
  const innerH = height - padT - padB;
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const sd = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / rets.length);
  const absMax = Math.max(...rets.map(r => Math.abs(r))) * 1.05;
  const mn = -absMax, mx = absMax;
  const bins = 50;
  const buckets = new Array(bins).fill(0);
  rets.forEach(v => {
    const t = clamp(Math.floor(((v - mn) / (mx - mn)) * bins), 0, bins - 1);
    buckets[t]++;
  });
  const maxC = Math.max(...buckets);
  const bw = innerW / bins;
  // normal pdf overlay
  const pdf = (x) => (1 / (sd * Math.sqrt(2 * Math.PI))) * Math.exp(-((x - mean) ** 2) / (2 * sd * sd));
  // scale pdf to match histogram peak (approximately)
  const peakPdf = pdf(mean);
  // hist peak count / bin width = density estimate; align peaks
  const histPeakDensity = maxC / (rets.length * (mx - mn) / bins);
  const scale = peakPdf > 0 ? histPeakDensity / peakPdf : 1;
  const overlayPts = [];
  for (let i = 0; i <= 120; i++) {
    const x = mn + (mx - mn) * (i / 120);
    const y = padT + innerH - (pdf(x) * scale / histPeakDensity) * innerH;
    overlayPts.push([padL + (i / 120) * innerW, y]);
  }
  return (
    <div ref={wrap} style={{ width: "100%", height }}>
      <svg width={w} height={height} style={{ display: "block" }}>
        {/* zero baseline */}
        <line x1={padL + innerW / 2} x2={padL + innerW / 2} y1={padT} y2={padT + innerH} stroke={Cx.borderL} strokeDasharray="2 4" />
        {buckets.map((c, i) => {
          const bh = (c / maxC) * innerH;
          const cx = mn + (mx - mn) * ((i + 0.5) / bins);
          const color = cx >= 0 ? Cx.green : Cx.coral;
          return <rect key={i} x={padL + i * bw + 0.5} y={padT + innerH - bh}
            width={bw - 1} height={bh} fill={color} opacity={0.5 + (c / maxC) * 0.4} />;
        })}
        {/* normal overlay */}
        <path d={lineFromPoints(overlayPts)} fill="none" stroke={Cx.amber} strokeWidth="1.4" strokeDasharray="4 3" />
        {/* axis labels */}
        <text x={padL} y={height - 2} fill={Cx.faint} fontSize="9.5" fontFamily="JetBrains Mono">{(mn * 100).toFixed(1)}%</text>
        <text x={padL + innerW / 2} y={height - 2} fill={Cx.faint} fontSize="9.5" textAnchor="middle" fontFamily="JetBrains Mono">0</text>
        <text x={padL + innerW} y={height - 2} fill={Cx.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">+{(mx * 100).toFixed(1)}%</text>
      </svg>
    </div>
  );
}

function QQPlot({ qq, height = 200 }) {
  const wrap = useRef(null);
  const [w, setW] = useState(300);
  useEffect(() => {
    const ro = new ResizeObserver(es => { if (es[0]) setW(es[0].contentRect.width); });
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  const padL = 36, padR = 10, padT = 8, padB = 18;
  const innerW = Math.max(40, w - padL - padR);
  const innerH = height - padT - padB;
  const xs = qq.map(p => p.theo);
  const ys = qq.map(p => p.sample);
  const mn = Math.min(Math.min(...xs), Math.min(...ys)) * 1.05;
  const mx = Math.max(Math.max(...xs), Math.max(...ys)) * 1.05;
  const sx = (v) => padL + ((v - mn) / (mx - mn)) * innerW;
  const sy = (v) => padT + innerH - ((v - mn) / (mx - mn)) * innerH;
  // sample down to ~120 points to keep render light
  const step = Math.max(1, Math.floor(qq.length / 120));
  const sample = qq.filter((_, i) => i % step === 0);
  return (
    <div ref={wrap} style={{ width: "100%", height }}>
      <svg width={w} height={height} style={{ display: "block" }}>
        {/* diagonal y=x */}
        <line x1={sx(mn)} y1={sy(mn)} x2={sx(mx)} y2={sy(mx)} stroke={Cx.cyan} strokeDasharray="3 3" />
        {/* axes */}
        <line x1={padL} y1={padT + innerH} x2={padL + innerW} y2={padT + innerH} stroke={Cx.border} />
        <line x1={padL} y1={padT} x2={padL} y2={padT + innerH} stroke={Cx.border} />
        {sample.map((p, i) => {
          // color outliers
          const dev = Math.abs(p.sample - p.theo);
          const c = dev > 1 ? Cx.coral : Cx.amber;
          return <circle key={i} cx={sx(p.theo)} cy={sy(p.sample)} r="1.6" fill={c} opacity="0.85" />;
        })}
        <text x={padL + innerW} y={padT + innerH + 14} fill={Cx.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">theo →</text>
        <text x={padL - 4} y={padT + 8} fill={Cx.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">↑sample</text>
      </svg>
    </div>
  );
}

function ACFChart({ rets, height = 200, maxLag = 30, n }) {
  const wrap = useRef(null);
  const [w, setW] = useState(220);
  useEffect(() => {
    const ro = new ResizeObserver(es => { if (es[0]) setW(es[0].contentRect.width); });
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  const acfs = useMemo(() => {
    const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
    const den = rets.reduce((a, b) => a + (b - mean) ** 2, 0);
    const out = [];
    for (let lag = 1; lag <= maxLag; lag++) {
      let num = 0;
      for (let i = 0; i < rets.length - lag; i++) num += (rets[i] - mean) * (rets[i + lag] - mean);
      out.push(num / den);
    }
    return out;
  }, [rets, maxLag]);
  const padL = 28, padR = 8, padT = 6, padB = 18;
  const innerW = Math.max(40, w - padL - padR);
  const innerH = height - padT - padB;
  const band = 2 / Math.sqrt(n);
  const yMax = Math.max(0.1, Math.max(...acfs.map(a => Math.abs(a)), band) * 1.2);
  const yScale = (v) => padT + innerH / 2 - (v / yMax) * (innerH / 2);
  const xScale = (i) => padL + (i / (maxLag - 1)) * innerW;
  return (
    <div ref={wrap} style={{ width: "100%", height }}>
      <svg width={w} height={height} style={{ display: "block" }}>
        {/* confidence band */}
        <rect x={padL} y={yScale(band)} width={innerW} height={yScale(-band) - yScale(band)}
          fill={Cx.cyan} opacity="0.08" />
        <line x1={padL} x2={padL + innerW} y1={padT + innerH / 2} y2={padT + innerH / 2} stroke={Cx.borderL} />
        <text x={padL - 4} y={padT + 4} fill={Cx.faint} fontSize="9" textAnchor="end" fontFamily="JetBrains Mono">+{yMax.toFixed(2)}</text>
        <text x={padL - 4} y={padT + innerH} fill={Cx.faint} fontSize="9" textAnchor="end" fontFamily="JetBrains Mono">-{yMax.toFixed(2)}</text>
        {acfs.map((v, i) => {
          const x = xScale(i);
          const yz = padT + innerH / 2;
          const yv = yScale(v);
          const outside = Math.abs(v) > band;
          return (
            <g key={i}>
              <line x1={x} x2={x} y1={yz} y2={yv} stroke={outside ? Cx.amber : Cx.dim} strokeWidth="1.5" />
              <circle cx={x} cy={yv} r="1.5" fill={outside ? Cx.amber : Cx.dim} />
            </g>
          );
        })}
        <text x={padL} y={height - 2} fill={Cx.faint} fontSize="9" fontFamily="JetBrains Mono">lag 1</text>
        <text x={padL + innerW} y={height - 2} fill={Cx.faint} fontSize="9" textAnchor="end" fontFamily="JetBrains Mono">{maxLag}</text>
      </svg>
    </div>
  );
}

function RollingVolChart({ rollVol, height = 140, mean }) {
  const wrap = useRef(null);
  const [w, setW] = useState(800);
  useEffect(() => {
    const ro = new ResizeObserver(es => { if (es[0]) setW(es[0].contentRect.width); });
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  const padL = 44, padR = 12, padT = 8, padB = 18;
  const innerW = Math.max(50, w - padL - padR);
  const innerH = height - padT - padB;
  const vs = rollVol.map(p => p.v * 100);
  const mn = Math.min(...vs) * 0.9;
  const mx = Math.max(...vs) * 1.05;
  const yScale = (v) => padT + innerH - ((v - mn) / (mx - mn)) * innerH;
  const xScale = (i) => padL + (i / (rollVol.length - 1)) * innerW;
  const pts = rollVol.map(p => [xScale(p.i), yScale(p.v * 100)]);
  // average line
  const meanY = yScale(mean);
  return (
    <div ref={wrap} style={{ width: "100%", height }}>
      <svg width={w} height={height} style={{ display: "block" }}>
        {[0, 0.5, 1].map((q, i) => {
          const v = mn + (mx - mn) * q;
          const y = padT + innerH - q * innerH;
          return (
            <g key={i}>
              <line x1={padL} x2={padL + innerW} y1={y} y2={y} stroke={Cx.border} strokeDasharray="2 4" />
              <text x={padL - 6} y={y + 3} fill={Cx.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">{v.toFixed(0)}%</text>
            </g>
          );
        })}
        <line x1={padL} x2={padL + innerW} y1={meanY} y2={meanY} stroke={Cx.cyan} strokeDasharray="6 3" />
        <text x={padL + innerW - 4} y={meanY - 3} fill={Cx.cyan} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">avg {mean}%</text>
        <path d={lineFromPoints(pts)} fill="none" stroke={Cx.amber} strokeWidth="1.4" />
      </svg>
    </div>
  );
}

// =================================================================
// LIBRARY — saved strategies
// =================================================================
function LibraryScreen({ goto, setRunId, runs, savedStrategies, setSavedStrategies }) {
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("sharpe");
  const [search, setSearch] = useState("");
  const filtered = useMemo(() => {
    let l = savedStrategies;
    if (filter !== "all") l = l.filter(s => s.status === filter);
    if (search) l = l.filter(s => s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.strategy.toLowerCase().includes(search.toLowerCase()) ||
      s.tags.join(" ").toLowerCase().includes(search.toLowerCase()));
    l = [...l].sort((a, b) => {
      if (sort === "sharpe") return b.metrics.sharpe - a.metrics.sharpe;
      if (sort === "cagr") return b.metrics.cagr - a.metrics.cagr;
      if (sort === "dd") return a.metrics.maxDD - b.metrics.maxDD;
      if (sort === "date") return b.created.localeCompare(a.created);
      return 0;
    });
    return l;
  }, [savedStrategies, filter, sort, search]);

  const openStrategy = (s) => {
    if (s.runRef) {
      setRunId(s.runRef);
      goto("equity");
    }
  };

  const toggleStar = (id) => {
    setSavedStrategies(ss => ss.map(s => s.id === id ? { ...s, starred: !s.starred } : s));
  };

  return (
    <div className="grid-12" style={{ gap: 6 }}>
      <Panel title="STRATEGY LIBRARY" sub={`${filtered.length}/${savedStrategies.length}`}
        right={
          <div className="row" style={{ gap: 6 }}>
            <input className="lib-search" placeholder="cerca · nome, tag…"
              value={search} onChange={e => setSearch(e.target.value)} />
            <span className="lbl-mono dim">status:</span>
            {["all", "live", "research", "archived"].map(s => (
              <Pill key={s} active={filter === s} onClick={() => setFilter(s)}>{s}</Pill>
            ))}
            <span className="lbl-mono dim" style={{ marginLeft: 6 }}>sort:</span>
            {[["sharpe", "Sh"], ["cagr", "CAGR"], ["dd", "DD"], ["date", "Recent"]].map(([k, l]) => (
              <Pill key={k} active={sort === k} onClick={() => setSort(k)}>{l}</Pill>
            ))}
          </div>
        }
        style={{ gridColumn: "span 12" }}>

        <div className="lib-grid">
          {filtered.map(s => (
            <div key={s.id} className={`lib-card lib-${s.status}`} onClick={() => openStrategy(s)}>
              <div className="lib-card-head">
                <span className={`lib-star ${s.starred ? "on" : ""}`}
                  onClick={e => { e.stopPropagation(); toggleStar(s.id); }}>★</span>
                <span className="lib-name">{s.name}</span>
                <span className={`lib-status lib-status-${s.status}`}>{s.status}</span>
              </div>
              <div className="lib-card-meta">
                <span className="lbl-mono dim">{s.strategy}</span>
                <span className="lbl-mono dim">· {s.author}</span>
                <span className="lbl-mono dim">· {s.created}</span>
              </div>
              <div className="lib-desc">{s.desc}</div>
              <div className="lib-tags">
                {s.tags.map(t => <span key={t} className="lib-tag">#{t}</span>)}
              </div>
              <div className="lib-metrics">
                <div className="lib-met">
                  <span className="lbl-mono dim">SHARPE</span>
                  <span className="mono lib-met-v">{s.metrics.sharpe}</span>
                </div>
                <div className="lib-met">
                  <span className="lbl-mono dim">CAGR</span>
                  <span className="mono lib-met-v" style={{ color: s.metrics.cagr > 0 ? Cx.green : Cx.coral }}>
                    {s.metrics.cagr > 0 ? "+" : ""}{s.metrics.cagr}%
                  </span>
                </div>
                <div className="lib-met">
                  <span className="lbl-mono dim">MAXDD</span>
                  <span className="mono lib-met-v" style={{ color: Cx.coral }}>{s.metrics.maxDD}%</span>
                </div>
                <div className="lib-met">
                  <span className="lbl-mono dim">PF</span>
                  <span className="mono lib-met-v">{s.metrics.pf}</span>
                </div>
                <div className="lib-met">
                  <span className="lbl-mono dim">TR</span>
                  <span className="mono lib-met-v">{s.metrics.trades}</span>
                </div>
              </div>
              {s.sparkline && (
                <div className="lib-spark">
                  <Sparkline data={s.sparkline} width={220} height={28}
                    color={s.metrics.cagr > 0 ? Cx.green : Cx.coral} />
                </div>
              )}
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="lib-empty">nessuna strategia trovata</div>
          )}
        </div>
      </Panel>
    </div>
  );
}

// =================================================================
// VIBE TRADING — natural-language strategy designer
// =================================================================
function VibeScreen({ savedStrategies, setSavedStrategies, goto, showToast }) {
  const [prompt, setPrompt] = useState("");
  const [history, setHistory] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [latest, setLatest] = useState(null);
  const [code, setCode] = useState(defaultStrategyCode());
  const [view, setView] = useState("vibe"); // vibe | code | templates

  const send = async (text) => {
    if (!text.trim() || generating) return;
    setGenerating(true);
    const userMsg = { role: "user", text };
    setHistory(h => [...h, userMsg]);
    setPrompt("");
    try {
      const system = `Sei un quant strategy designer. Dato il prompt utente in linguaggio naturale, restituisci SOLO un oggetto JSON valido (nessun markdown, nessuna prosa, nessun commento) con questa schema esatta:
{
 "name": "kebab-case-name",
 "description": "1-2 frasi descrizione concisa",
 "strategy_type": "momentum"|"mean-reversion"|"trend-following"|"breakout"|"stat-arb"|"carry"|"vol-target"|"other",
 "universe": ["BTC","ETH",...],
 "timeframe": "5m"|"15m"|"1h"|"4h"|"1d",
 "long_when": ["condizione 1","condizione 2"],
 "short_when": ["condizione 1"],
 "exit_when": ["condizione"],
 "risk": {"per_trade_pct": 1.0, "stop":"2.5*ATR", "take_profit":"4*ATR", "max_positions": 3},
 "expected_metrics": {"sharpe_est": 1.5, "cagr_est": 20, "max_dd_est": -15}
}
Tutte le stringhe in italiano. SOLO JSON, niente altro.`;
      const reply = await window.claude.complete({
        messages: [
          { role: "user", content: system + "\n\nUSER PROMPT:\n" + text }
        ]
      });
      let json = null;
      try {
        // try to extract JSON from possible code fence
        const cleaned = reply.trim().replace(/^```(?:json)?/, "").replace(/```$/, "").trim();
        json = JSON.parse(cleaned);
      } catch (e) {
        // try locating { ... }
        const m = reply.match(/\{[\s\S]*\}/);
        if (m) try { json = JSON.parse(m[0]); } catch (e2) { }
      }
      if (!json) throw new Error("invalid JSON");
      json._raw = reply;
      json._timestamp = new Date().toLocaleTimeString();
      setLatest(json);
      setCode(strategyToCode(json));
      setHistory(h => [...h, { role: "agent", text: json.description, json }]);
    } catch (e) {
      setHistory(h => [...h, { role: "agent", text: "⚠ errore nel parsing della risposta", error: true }]);
    } finally {
      setGenerating(false);
    }
  };

  const saveToLibrary = () => {
    if (!latest) return;
    const newEntry = {
      id: "lib-vibe-" + Date.now(),
      name: latest.name,
      strategy: latest.strategy_type,
      author: "vibe-agent",
      created: new Date().toISOString().slice(0, 10),
      tags: ["vibe", latest.strategy_type, ...(latest.universe || []).slice(0, 2).map(u => u.toLowerCase())],
      starred: false,
      status: "research",
      metrics: {
        sharpe: latest.expected_metrics?.sharpe_est || 1.0,
        cagr: latest.expected_metrics?.cagr_est || 10,
        maxDD: latest.expected_metrics?.max_dd_est || -10,
        pf: 1.5,
        trades: 200
      },
      desc: latest.description
    };
    setSavedStrategies(ss => [newEntry, ...ss]);
    showToast("salvata in LIBRARY");
  };

  const templates = [
    { name: "Momentum cross", prompt: "Long quando EMA(12) > EMA(48) e RSI(14) > 50 su BTC ed ETH, timeframe 1h. Stop 2.5×ATR, TP 4×ATR." },
    { name: "Mean reversion bands", prompt: "Mean reversion su ETH 4h: long quando il prezzo scende sotto la Bollinger inferiore con RSI<30, exit al ritorno alla media. Stop 2×ATR." },
    { name: "Donchian breakout", prompt: "Breakout dei massimi a 20 giorni su un paniere multi-crypto (BTC, ETH, SOL). Trailing stop 3×ATR." },
    { name: "Funding arb", prompt: "Long spot / short perp BTC quando il funding rate medio settimanale supera 0.03%. Chiusura quando il funding rientra sotto 0.005%." },
    { name: "Vol targeting", prompt: "Long BTC con esposizione scalata a target di volatilità annua del 15%. Rebilancia ogni venerdì." }
  ];

  return (
    <div className="vibe-screen">
      <div className="vibe-tabs">
        <button className={`vibe-tab ${view === "vibe" ? "on" : ""}`} onClick={() => setView("vibe")}>
          <span className="vibe-tab-icon">◊</span> VIBE · agent
        </button>
        <button className={`vibe-tab ${view === "code" ? "on" : ""}`} onClick={() => setView("code")}>
          <span className="vibe-tab-icon">›_</span> CODE · DSL
        </button>
        <button className={`vibe-tab ${view === "templates" ? "on" : ""}`} onClick={() => setView("templates")}>
          <span className="vibe-tab-icon">⊞</span> TEMPLATES
        </button>
        <div style={{ flex: 1 }}></div>
        <button className="btn btn-primary" disabled={!latest} onClick={saveToLibrary}>+ SAVE TO LIBRARY</button>
        <button className="btn" disabled={!latest} onClick={() => showToast("▶ backtest simulato")}>▶ BACKTEST</button>
      </div>

      {view === "vibe" && (
        <div className="vibe-split">
          {/* LEFT: agent chat */}
          <div className="vibe-chat-pane">
            <div className="vibe-chat-head">
              <span className="lbl-mono">AGENT · vibe-trading</span>
              <span className="lbl-mono dim">claude-haiku-4-5</span>
            </div>
            <div className="vibe-chat-body">
              {history.length === 0 && (
                <div className="vibe-greeting">
                  <div className="vibe-glow">◊</div>
                  <div className="vibe-greeting-h">descrivi una strategia.</div>
                  <div className="vibe-greeting-p">in italiano, in inglese, frammenti, idee. l'agent struttura, parametra, suggerisce.</div>
                  <div className="vibe-examples">
                    {templates.slice(0, 3).map((t, i) => (
                      <button key={i} className="vibe-example" onClick={() => send(t.prompt)}>
                        <span className="lbl-mono dim">{t.name}</span>
                        <span className="vibe-example-text">{t.prompt}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {history.map((m, i) => (
                <div key={i} className={`vibe-msg vibe-${m.role}`}>
                  <div className="vibe-msg-head">
                    <span className="lbl-mono">{m.role === "user" ? "you" : "agent"}</span>
                  </div>
                  <div className="vibe-msg-body">
                    {m.error ? <span style={{ color: Cx.coral }}>{m.text}</span> : m.text}
                  </div>
                  {m.json && <StrategyCard spec={m.json} compact />}
                </div>
              ))}
              {generating && (
                <div className="vibe-msg vibe-agent">
                  <div className="vibe-msg-head"><span className="lbl-mono">agent</span></div>
                  <div className="vibe-typing">
                    <span></span><span></span><span></span>
                  </div>
                </div>
              )}
            </div>
            <div className="vibe-input-row">
              <textarea
                className="vibe-input"
                placeholder="descrivi la strategia… es: long BTC quando RSI > 70 e volume > 1.5×media"
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    send(prompt);
                  }
                }}
                rows={2}
              />
              <button className="btn btn-primary" disabled={!prompt.trim() || generating}
                onClick={() => send(prompt)}>
                {generating ? "..." : "▸ SEND"}
              </button>
            </div>
            <div className="lbl-mono dim" style={{ padding: "4px 12px" }}>
              <kbd>⌘↵</kbd> invia
            </div>
          </div>

          {/* RIGHT: spec preview */}
          <div className="vibe-spec-pane">
            <div className="vibe-chat-head">
              <span className="lbl-mono">STRATEGY SPEC</span>
              <span className="lbl-mono dim">{latest ? latest._timestamp : "no spec yet"}</span>
            </div>
            <div className="vibe-spec-body">
              {latest ? (
                <StrategyCard spec={latest} />
              ) : (
                <div className="vibe-empty">
                  <div className="vibe-empty-icon">◌</div>
                  <div>nessuna strategia generata</div>
                  <div className="lbl-mono dim">manda un prompt per cominciare</div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {view === "code" && (
        <div className="vibe-code-pane">
          <div className="vibe-chat-head">
            <span className="lbl-mono">STRATEGY DSL · pareto-lang</span>
            <span className="lbl-mono dim">monospace · editabile</span>
          </div>
          <textarea
            className="vibe-code"
            value={code}
            onChange={e => setCode(e.target.value)}
            spellCheck="false"
          />
          <div className="vibe-code-foot lbl-mono dim">
            righe: {code.split("\n").length} · caratteri: {code.length} · ⌘↵ valida
          </div>
        </div>
      )}

      {view === "templates" && (
        <div className="vibe-templates">
          <Panel title="TEMPLATES · starter strategies" style={{ gridColumn: "span 12" }}>
            <div className="vibe-tmpl-grid">
              {templates.map((t, i) => (
                <div key={i} className="vibe-tmpl-card" onClick={() => { setView("vibe"); send(t.prompt); }}>
                  <div className="vibe-tmpl-name">{t.name}</div>
                  <div className="vibe-tmpl-prompt">{t.prompt}</div>
                  <div className="row" style={{ marginTop: 10 }}>
                    <span className="lbl-mono dim">click → genera</span>
                    <span style={{ flex: 1 }}></span>
                    <span className="lbl-mono" style={{ color: Cx.cyan }}>USE →</span>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}

function StrategyCard({ spec, compact }) {
  return (
    <div className={`strat-card ${compact ? "strat-compact" : ""}`}>
      <div className="strat-head">
        <span className="strat-name">{spec.name}</span>
        <span className="strat-type">{spec.strategy_type}</span>
      </div>
      <div className="strat-desc">{spec.description}</div>

      <div className="strat-section">
        <div className="lbl-mono dim">UNIVERSE · TIMEFRAME</div>
        <div className="row" style={{ gap: 6, marginTop: 4, flexWrap: "wrap" }}>
          {(spec.universe || []).map(u => <span key={u} className="pill active">{u}</span>)}
          <span className="pill">{spec.timeframe}</span>
        </div>
      </div>

      {spec.long_when?.length > 0 && (
        <div className="strat-section">
          <div className="lbl-mono" style={{ color: Cx.green }}>LONG WHEN</div>
          <ul className="strat-list">{spec.long_when.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </div>
      )}
      {spec.short_when?.length > 0 && (
        <div className="strat-section">
          <div className="lbl-mono" style={{ color: Cx.coral }}>SHORT WHEN</div>
          <ul className="strat-list">{spec.short_when.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </div>
      )}
      {spec.exit_when?.length > 0 && (
        <div className="strat-section">
          <div className="lbl-mono" style={{ color: Cx.cyan }}>EXIT WHEN</div>
          <ul className="strat-list">{spec.exit_when.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </div>
      )}

      {spec.risk && (
        <div className="strat-section">
          <div className="lbl-mono dim">RISK</div>
          <div className="row" style={{ gap: 12, marginTop: 4, flexWrap: "wrap" }}>
            <span className="mono">risk · <b style={{ color: Cx.amber }}>{spec.risk.per_trade_pct}%</b></span>
            <span className="mono">stop · <b style={{ color: Cx.amber }}>{spec.risk.stop}</b></span>
            <span className="mono">TP · <b style={{ color: Cx.amber }}>{spec.risk.take_profit}</b></span>
            <span className="mono">max-pos · <b style={{ color: Cx.amber }}>{spec.risk.max_positions}</b></span>
          </div>
        </div>
      )}

      {spec.expected_metrics && (
        <div className="strat-section">
          <div className="lbl-mono dim">EXPECTED · stima del modello (non backtest)</div>
          <div className="row" style={{ gap: 10, marginTop: 4 }}>
            <MetricBlock label="Sharpe~" value={spec.expected_metrics.sharpe_est} color={Cx.amber} />
            <MetricBlock label="CAGR~" value={spec.expected_metrics.cagr_est + "%"} color={Cx.green} />
            <MetricBlock label="MaxDD~" value={spec.expected_metrics.max_dd_est + "%"} color={Cx.coral} />
          </div>
        </div>
      )}
    </div>
  );
}

function defaultStrategyCode() {
  return `# pareto-lang · strategy definition
strategy momentum_cross {
  universe: [BTC, ETH, SOL]
  timeframe: 1h
  is_window: 2021-01 .. 2023-12
  oos_window: 2024-01 .. now

  # signals
  signal long when {
    ema(close, 12) > ema(close, 48)
    rsi(close, 14) > 50
    volume > sma(volume, 20) * 1.2
  }

  signal short when {
    ema(close, 12) < ema(close, 48)
    rsi(close, 14) < 50
  }

  exit when {
    bars_in_trade > 96
    crossing(ema(close, 12), ema(close, 48))
  }

  # risk
  risk {
    per_trade: 1.0%
    stop: 2.5 * atr(14)
    take_profit: 4.0 * atr(14)
    max_positions: 3
  }

  # frictions
  frictions {
    fees: 10bps
    slippage: 3bps
    funding: include
  }
}`;
}

function strategyToCode(spec) {
  const lines = [];
  lines.push("# generated by vibe-agent · " + new Date().toLocaleString());
  lines.push(`strategy ${(spec.name || "untitled").replace(/-/g, "_")} {`);
  lines.push(`  universe: [${(spec.universe || []).join(", ")}]`);
  lines.push(`  timeframe: ${spec.timeframe || "1h"}`);
  lines.push("");
  if (spec.long_when?.length) {
    lines.push("  signal long when {");
    spec.long_when.forEach(c => lines.push(`    # ${c}`));
    lines.push("  }");
    lines.push("");
  }
  if (spec.short_when?.length) {
    lines.push("  signal short when {");
    spec.short_when.forEach(c => lines.push(`    # ${c}`));
    lines.push("  }");
    lines.push("");
  }
  if (spec.exit_when?.length) {
    lines.push("  exit when {");
    spec.exit_when.forEach(c => lines.push(`    # ${c}`));
    lines.push("  }");
    lines.push("");
  }
  if (spec.risk) {
    lines.push("  risk {");
    lines.push(`    per_trade: ${spec.risk.per_trade_pct}%`);
    lines.push(`    stop: ${spec.risk.stop}`);
    lines.push(`    take_profit: ${spec.risk.take_profit}`);
    lines.push(`    max_positions: ${spec.risk.max_positions}`);
    lines.push("  }");
  }
  lines.push("}");
  return lines.join("\n");
}

Object.assign(window, {
  AssetsScreen, LibraryScreen, VibeScreen,
  PriceChart, ReturnsChart, ReturnHistogram, QQPlot, ACFChart, RollingVolChart,
  StrategyCard
});
