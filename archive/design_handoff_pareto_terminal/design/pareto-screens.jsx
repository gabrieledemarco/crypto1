/* PARETO — 8 screens */
const C2 = window.PARETO_C;

// === shared atoms ===
function Panel({ title, sub, right, children, style = {}, flex }) {
  return (
    <div className="pnl" style={{ display: "flex", flexDirection: "column", flex, ...style }}>
      {(title || right) && (
        <div className="pnl-h">
          <span className="pnl-t">{title}</span>
          {sub && <span className="pnl-s">{sub}</span>}
          <span style={{ flex: 1 }}></span>
          {right}
        </div>
      )}
      <div className="pnl-b">{children}</div>
    </div>
  );
}

function MetricBlock({ label, value, sub, color, big }) {
  return (
    <div className="metric">
      <div className="metric-l">{label}</div>
      <div className="metric-v" style={{ color, fontSize: big ? 22 : 16 }}>{value}</div>
      {sub && <div className="metric-s">{sub}</div>}
    </div>
  );
}

function Pill({ children, kind = "", onClick, active }) {
  return (
    <span className={`pill ${kind} ${active ? "active" : ""}`} onClick={onClick}>{children}</span>
  );
}

function fmtPct(v, digits = 1, withSign = true) {
  const s = withSign && v > 0 ? "+" : "";
  return s + (v * 100).toFixed(digits) + "%";
}

// === 1. DASHBOARD ===
function DashboardScreen({ run, runs, setRun, goto }) {
  const [hov, setHov] = useState(null);
  return (
    <div className="grid-12" style={{ gap: 6 }}>
      <Panel
        title="EQUITY · IS / OOS · vs BTC HODL"
        sub="hover per crosshair"
        right={<span className="lbl-mono dim">+{run.metricsOOS.finalReturn}% OOS</span>}
        style={{ gridColumn: "span 8" }}>
        <EquityChart equity={run.equity} oosStart={run.oosStart} height={220}
          color={C2.amber} showBench={true} onHover={(i) => setHov(i)} />
        <DrawdownChart equity={run.equity} height={64} sharedHover={hov} color={C2.coral} />
      </Panel>

      <Panel title="HEADLINE · IS | OOS" style={{ gridColumn: "span 4" }}>
        <div className="metric-grid">
          {[
            ["Sharpe", run.metricsIS.sharpe, run.metricsOOS.sharpe, null],
            ["Sortino", run.metricsIS.sortino, run.metricsOOS.sortino, null],
            ["Calmar", run.metricsIS.calmar, run.metricsOOS.calmar, null],
            ["CAGR", run.metricsIS.cagr + "%", run.metricsOOS.cagr + "%", C2.green],
            ["MaxDD", run.metricsIS.maxDD + "%", run.metricsOOS.maxDD + "%", C2.coral],
            ["Ulcer", 3.1, 3.4, null],
            ["Win%", run.winRate, run.winRate, null],
            ["PF", run.profitFactor, run.profitFactor, null],
            ["Trades", run.tradesCount, run.tradesCount, null]
          ].map((m, i) => (
            <div key={i} className="metric metric-pair">
              <div className="metric-l">{m[0]}</div>
              <div className="metric-pair-vals">
                <span className="metric-v dim" style={{ color: C2.dim }}>{m[1]}</span>
                <span className="metric-v" style={{ color: m[3] || C2.amber }}>{m[2]}</span>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="MONTHLY P&L" sub="24 mesi" style={{ gridColumn: "span 4" }}>
        <MonthlyHeat monthly={run.monthly} cellSize={22} />
        <div className="lbl-mono dim" style={{ marginTop: 8 }}>
          best <b style={{ color: C2.green }}>+{Math.max(...run.monthly.map(m => m.pnl)).toFixed(1)}%</b>
          &nbsp;&nbsp;worst <b style={{ color: C2.coral }}>{Math.min(...run.monthly.map(m => m.pnl)).toFixed(1)}%</b>
        </div>
      </Panel>

      <Panel title="RECENT TRADES" sub="last 6" style={{ gridColumn: "span 4" }}>
        <div className="tbl tbl-compact">
          <div className="tr h" style={{ gridTemplateColumns: "30px 50px 70px 70px 1fr" }}>
            <span>#</span><span>SIDE</span><span>R</span><span>P&L%</span><span>EQ</span>
          </div>
          {run.trades.slice(-6).reverse().map((t, i) => (
            <div key={i} className="tr" style={{ gridTemplateColumns: "30px 50px 70px 70px 1fr" }}>
              <span className="dim">{String(t.n).padStart(3, "0")}</span>
              <span style={{ color: t.side === "L" ? C2.amber : C2.cyan }}>{t.side}</span>
              <span>{t.r.toFixed(1)}</span>
              <span style={{ color: t.pnl > 0 ? C2.green : C2.coral }}>{t.pnl > 0 ? "+" : ""}{t.pnl}</span>
              <Sparkline data={run.equity.slice(Math.max(0, t.idx - 4), t.idx + 1).map(e => e.v)}
                width={70} height={12} color={t.pnl > 0 ? C2.green : C2.coral} />
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="DD TOP 3" style={{ gridColumn: "span 4" }}>
        <div className="tbl tbl-compact">
          <div className="tr h" style={{ gridTemplateColumns: "30px 1fr 70px 60px 60px" }}>
            <span>#</span><span>PERIOD</span><span>DEPTH</span><span>LEN</span><span>REC</span>
          </div>
          {run.ddPeriods.slice(0, 3).map((dd, i) => (
            <div key={i} className="tr" style={{ gridTemplateColumns: "30px 1fr 70px 60px 60px" }}>
              <span className="dim">{i + 1}</span>
              <span className="dim">t{dd.start}→t{dd.end}</span>
              <span style={{ color: C2.coral }}>{(dd.depth * 100).toFixed(1)}%</span>
              <span>{dd.length}d</span>
              <span>{dd.recovery}d</span>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 10 }}>
          <button className="btn" onClick={() => goto("underwater")}>VIEW ALL · g+u</button>
        </div>
      </Panel>
    </div>
  );
}

// === 2. SETUP ===
function SetupScreen({ run, setRun, mutateParams, runAll }) {
  const p = run.params;
  const update = (k, v) => mutateParams({ [k]: v });
  // mini preview: rebuild a tiny equity preview from params
  const previewEquity = useMemo(() => {
    // hash params into seed
    const s = p.fastMA * 13 + p.slowMA * 7 + Math.round(p.atrStop * 10) + Math.round(p.riskPerTrade * 100);
    const len = 120;
    const arr = [];
    let v = 1.0;
    let rnd = () => {
      const x = Math.sin(s * 1000 + arr.length) * 10000;
      return x - Math.floor(x);
    };
    for (let i = 0; i < len; i++) {
      const mu = (p.fastMA < p.slowMA ? 0.0028 : 0.0008) * (p.riskPerTrade / 1.0);
      const sig = 0.014 * Math.sqrt(p.atrStop / 2.5);
      v *= 1 + mu + (rnd() - 0.5) * sig * 2;
      arr.push({ v, bench: 1.0 + i * 0.0005, dd: 0, oos: false, i });
    }
    let pk = arr[0].v;
    arr.forEach(e => { pk = Math.max(pk, e.v); e.dd = (e.v - pk) / pk; });
    return arr;
  }, [p.fastMA, p.slowMA, p.atrStop, p.riskPerTrade]);

  const estSharpe = useMemo(() => {
    const rets = [];
    for (let i = 1; i < previewEquity.length; i++) rets.push(previewEquity[i].v / previewEquity[i - 1].v - 1);
    const m = rets.reduce((a, b) => a + b, 0) / rets.length;
    const sd = Math.sqrt(rets.reduce((a, b) => a + (b - m) ** 2, 0) / rets.length);
    return ((m / sd) * Math.sqrt(252)).toFixed(2);
  }, [previewEquity]);

  return (
    <div className="grid-12" style={{ gap: 6 }}>
      <Panel title="STRATEGY · momentum-cross" sub="ctrl+enter run" style={{ gridColumn: "span 5" }}>
        <div className="form">
          <Slider label="FAST MA" min={2} max={50} value={p.fastMA} onChange={v => update("fastMA", v)} />
          <Slider label="SLOW MA" min={5} max={200} value={p.slowMA} onChange={v => update("slowMA", v)} />
          <Slider label="ATR STOP ×" min={0.5} max={5} step={0.1} value={p.atrStop} onChange={v => update("atrStop", v)} />
          <Slider label="TAKE PROFIT ×" min={1} max={8} step={0.1} value={p.takeProfit} onChange={v => update("takeProfit", v)} />
          <Slider label="RISK / TRADE %" min={0.1} max={3} step={0.1} value={p.riskPerTrade} onChange={v => update("riskPerTrade", v)} />

          <div className="form-row" style={{ marginTop: 10 }}>
            <span className="lbl-mono dim">UNIVERSE</span>
            <div className="row" style={{ gap: 4, flexWrap: "wrap", flex: 1, justifyContent: "flex-end" }}>
              {["BTC", "ETH", "SOL", "ARB", "OP", "MATIC", "AVAX"].map(s => (
                <Pill key={s} kind="" active={p.universe.includes(s)}
                  onClick={() => {
                    const u = p.universe.includes(s) ? p.universe.filter(x => x !== s) : [...p.universe, s];
                    update("universe", u);
                  }}>{s}</Pill>
              ))}
            </div>
          </div>

          <div className="form-row">
            <span className="lbl-mono dim">TIMEFRAME</span>
            <div className="row" style={{ gap: 4, flex: 1, justifyContent: "flex-end" }}>
              {["5m", "15m", "1h", "4h", "1d"].map(tf => (
                <Pill key={tf} active={p.timeframe === tf} onClick={() => update("timeframe", tf)}>{tf}</Pill>
              ))}
            </div>
          </div>

          <div className="form-row" style={{ marginTop: 8 }}>
            <span className="lbl-mono dim">FEES · SLIP · FUNDING</span>
            <span className="mono">{p.fees}bps · {p.slippage}bps · {p.funding ? "on" : "off"}</span>
          </div>

          <div className="row" style={{ marginTop: 14, gap: 8 }}>
            <button className="btn btn-primary" onClick={runAll}>▶ RUN  ⌘↵</button>
            <button className="btn">SAVE</button>
            <button className="btn">RESET</button>
          </div>
        </div>
      </Panel>

      <Panel title="LIVE PREVIEW" sub={`BTC · ${p.timeframe} · sample 120 bars`} style={{ gridColumn: "span 7" }}>
        <EquityChart equity={previewEquity} oosStart={null} height={240} color={C2.cyan} showBench={false} />
        <div className="row" style={{ gap: 6, marginTop: 8 }}>
          <MetricBlock label="EST SHARPE" value={estSharpe} color={C2.amber} />
          <MetricBlock label="EST TRADES / YR" value={Math.round(140 * (p.riskPerTrade / 1.0))} color={C2.amber} />
          <MetricBlock label="EST EXPOSURE" value={Math.min(98, 40 + p.universe.length * 8) + "%"} color={C2.amber} />
          <MetricBlock label="DATA WINDOW" value={`${p.universe.length} sym · 4Y`} color={C2.cyan} />
        </div>
        <div className="hint" style={{ marginTop: 8 }}>
          il preview ricampiona ogni 80ms al cambio parametro · niente run completo
        </div>
      </Panel>
    </div>
  );
}

function Slider({ label, min, max, step = 1, value, onChange }) {
  return (
    <div className="form-row slider-row">
      <span className="lbl-mono dim">{label}</span>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(+e.target.value)} className="rng" />
      <span className="mono num-val">{Number.isInteger(value) ? value : value.toFixed(2)}</span>
    </div>
  );
}

// === 3. EQUITY / RESULTS ===
function EquityScreen({ run }) {
  const [log, setLog] = useState(false);
  const [bench, setBench] = useState(true);
  const [hov, setHov] = useState(null);
  return (
    <div className="grid-12" style={{ gap: 6 }}>
      <Panel
        title="EQUITY · IS / OOS"
        sub="sync crosshair"
        right={
          <span className="row" style={{ gap: 4 }}>
            <Pill active={log} onClick={() => setLog(!log)}>LOG</Pill>
            <Pill active={bench} onClick={() => setBench(!bench)}>BENCH</Pill>
          </span>
        }
        style={{ gridColumn: "span 12" }}>
        <div className="row" style={{ gap: 12, marginBottom: 8 }}>
          {[
            ["CAGR", run.metricsIS.cagr + "%", run.metricsOOS.cagr + "%", C2.green],
            ["SHARPE", run.metricsIS.sharpe, run.metricsOOS.sharpe, null],
            ["SORTINO", run.metricsIS.sortino, run.metricsOOS.sortino, null],
            ["CALMAR", run.metricsIS.calmar, run.metricsOOS.calmar, null],
            ["MAXDD", run.metricsIS.maxDD + "%", run.metricsOOS.maxDD + "%", C2.coral],
            ["PF", run.profitFactor, run.profitFactor, null],
            ["WIN%", run.winRate, run.winRate, null],
            ["TRADES", run.tradesCount, run.tradesCount, null]
          ].map((m, i) => (
            <div key={i} className="metric-strip">
              <div className="lbl-mono dim">{m[0]} · IS|OOS</div>
              <div className="row" style={{ gap: 6 }}>
                <span className="mono dim">{m[1]}</span>
                <span className="mono" style={{ color: m[3] || C2.amber, fontWeight: 700 }}>{m[2]}</span>
              </div>
            </div>
          ))}
        </div>
        <EquityChart equity={run.equity} oosStart={run.oosStart} height={300}
          showBench={bench} log={log} color={C2.amber} onHover={(i) => setHov(i)} />
        <DrawdownChart equity={run.equity} height={100} sharedHover={hov} color={C2.coral} />
      </Panel>
    </div>
  );
}

// === 4. TRADE LOG ===
function TradesScreen({ run }) {
  const [filterSide, setFilterSide] = useState("all");
  const [filterPnL, setFilterPnL] = useState("all");
  const [sortBy, setSortBy] = useState("n");
  const [sortDir, setSortDir] = useState(1);
  const [cursor, setCursor] = useState(0);
  const listRef = useRef(null);

  const trades = useMemo(() => {
    let t = run.trades;
    if (filterSide !== "all") t = t.filter(x => x.side === (filterSide === "long" ? "L" : "S"));
    if (filterPnL === "win") t = t.filter(x => x.pnl > 0);
    if (filterPnL === "loss") t = t.filter(x => x.pnl < 0);
    t = [...t].sort((a, b) => {
      const av = a[sortBy], bv = b[sortBy];
      return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
    });
    return t;
  }, [run, filterSide, filterPnL, sortBy, sortDir]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "INPUT") return;
      if (e.key === "j") { setCursor(c => Math.min(trades.length - 1, c + 1)); e.preventDefault(); }
      else if (e.key === "k") { setCursor(c => Math.max(0, c - 1)); e.preventDefault(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [trades.length]);

  const headerCell = (k, label, w) => (
    <span style={{ cursor: "pointer", userSelect: "none" }}
      onClick={() => {
        if (sortBy === k) setSortDir(-sortDir);
        else { setSortBy(k); setSortDir(1); }
      }}>
      {label}{sortBy === k ? (sortDir > 0 ? " ↑" : " ↓") : ""}
    </span>
  );

  const cols = "30px 70px 50px 80px 80px 60px 60px 80px 90px";

  const winners = run.trades.filter(t => t.pnl > 0).length;
  const losers = run.trades.length - winners;

  return (
    <div className="grid-12" style={{ gap: 6 }}>
      <Panel title="TRADE LOG" sub={`${trades.length} of ${run.trades.length}`} style={{ gridColumn: "span 12" }}>
        <div className="row" style={{ gap: 6, marginBottom: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span className="lbl-mono dim">side:</span>
          {["all", "long", "short"].map(s => (
            <Pill key={s} active={filterSide === s} onClick={() => setFilterSide(s)}>{s}</Pill>
          ))}
          <span className="lbl-mono dim" style={{ marginLeft: 12 }}>pnl:</span>
          {["all", "win", "loss"].map(s => (
            <Pill key={s} active={filterPnL === s} onClick={() => setFilterPnL(s)}>{s}</Pill>
          ))}
          <span style={{ flex: 1 }}></span>
          <span className="lbl-mono">
            <span style={{ color: C2.amber }}>{run.trades.filter(t => t.side === "L").length} L</span> ·
            <span style={{ color: C2.cyan }}> {run.trades.filter(t => t.side === "S").length} S</span> ·
            <span style={{ color: C2.green }}> {winners} win</span> ·
            <span style={{ color: C2.coral }}> {losers} loss</span>
          </span>
          <button className="btn">↓ CSV</button>
        </div>

        <div className="tbl" ref={listRef} style={{ maxHeight: 480, overflow: "auto" }}>
          <div className="tr h" style={{ gridTemplateColumns: cols, position: "sticky", top: 0 }}>
            <span>{headerCell("n", "#")}</span>
            <span>{headerCell("date", "OPEN")}</span>
            <span>{headerCell("side", "SIDE")}</span>
            <span>{headerCell("entry", "ENTRY")}</span>
            <span>{headerCell("exit", "EXIT")}</span>
            <span>{headerCell("r", "R")}</span>
            <span>{headerCell("durH", "DUR")}</span>
            <span>{headerCell("pnl", "P&L%")}</span>
            <span>EQUITY</span>
          </div>
          {trades.slice(0, 200).map((t, i) => (
            <div key={t.n}
              className={`tr ${cursor === i ? "tr-sel" : ""}`}
              onClick={() => setCursor(i)}
              style={{ gridTemplateColumns: cols }}>
              <span className="dim">{String(t.n).padStart(3, "0")}</span>
              <span className="dim">t{String(t.idx).padStart(3, "0")}</span>
              <span style={{ color: t.side === "L" ? C2.amber : C2.cyan, fontWeight: 700 }}>{t.side}</span>
              <span>{t.entry.toLocaleString()}</span>
              <span>{t.exit.toLocaleString()}</span>
              <span style={{ color: t.r > 0 ? C2.green : C2.coral }}>{t.r.toFixed(1)}</span>
              <span>{t.durH}h</span>
              <span style={{ color: t.pnl > 0 ? C2.green : C2.coral, fontWeight: 700 }}>
                {t.pnl > 0 ? "+" : ""}{t.pnl}
              </span>
              <Sparkline
                data={run.equity.slice(Math.max(0, t.idx - 5), t.idx + 2).map(e => e.v)}
                width={80} height={12}
                color={t.pnl > 0 ? C2.green : C2.coral} />
            </div>
          ))}
        </div>

        <div className="row" style={{ marginTop: 8, gap: 12 }}>
          <span className="lbl-mono dim">
            <kbd>j</kbd>↓ <kbd>k</kbd>↑ <kbd>↵</kbd> open · <kbd>f</kbd> filter
          </span>
          <span style={{ flex: 1 }}></span>
          <span className="lbl-mono dim">cursor {cursor + 1}/{trades.length}</span>
        </div>
      </Panel>
    </div>
  );
}

// === 5. SWEEP ===
function SweepScreen({ run }) {
  const [sel, setSel] = useState([4, 6]);
  const [metric, setMetric] = useState("Sharpe");
  const v = run.sweep[sel[0]][sel[1]];
  const neighbors = [];
  for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
    const r = sel[0] + dr, c = sel[1] + dc;
    if (r >= 0 && r < run.sweep.length && c >= 0 && c < run.sweep[0].length) neighbors.push(run.sweep[r][c]);
  }
  const nMean = neighbors.reduce((a, b) => a + b, 0) / neighbors.length;
  const nStd = Math.sqrt(neighbors.reduce((a, b) => a + (b - nMean) ** 2, 0) / neighbors.length);
  const robust = nStd < 0.15 ? "STABILE" : nStd < 0.35 ? "MEDIO" : "FRAGILE";
  const robustColor = nStd < 0.15 ? C2.green : nStd < 0.35 ? C2.amber : C2.coral;

  // best across grid
  let best = [0, 0, run.sweep[0][0]];
  run.sweep.forEach((row, r) => row.forEach((vv, c) => { if (vv > best[2]) best = [r, c, vv]; }));

  return (
    <div className="grid-12" style={{ gap: 6 }}>
      <Panel
        title={`PARAMETER SWEEP · ${metric} · fastMA × slowMA`}
        sub="click cell · drag (not impl in wireframe-grade) = zoom"
        right={
          <span className="row" style={{ gap: 4 }}>
            {["Sharpe", "CAGR", "MaxDD", "Calmar"].map(m => (
              <Pill key={m} active={metric === m} onClick={() => setMetric(m)}>{m}</Pill>
            ))}
          </span>
        }
        style={{ gridColumn: "span 8" }}>
        <div className="row" style={{ alignItems: "flex-start", gap: 12 }}>
          <div>
            <div className="lbl-mono dim" style={{ marginBottom: 4 }}>slowMA →</div>
            <HeatmapGrid grid={run.sweep} cellSize={38}
              selected={sel}
              onClick={([r, c]) => setSel([r, c])}
              label="Sh" />
            <div className="row" style={{ marginTop: 6, justifyContent: "space-between", maxWidth: 400 }}>
              <span className="lbl-mono dim">fastMA ↓</span>
              <span className="lbl-mono dim">min {Math.min(...run.sweep.flat()).toFixed(2)} → max {Math.max(...run.sweep.flat()).toFixed(2)}</span>
            </div>
          </div>
        </div>
      </Panel>

      <Panel title="SELECTION" style={{ gridColumn: "span 4" }}>
        <div className="metric-grid">
          <MetricBlock label="fastMA" value={(sel[0] + 2) * 2} color={C2.cyan} />
          <MetricBlock label="slowMA" value={(sel[1] + 4) * 6} color={C2.cyan} />
          <MetricBlock label={metric} value={v.toFixed(2)} color={C2.amber} big />
          <MetricBlock label="vs BEST" value={(v - best[2]).toFixed(2)} color={v >= best[2] ? C2.green : C2.coral} />
        </div>

        <div style={{ marginTop: 14 }}>
          <div className="lbl-mono dim">ROBUSTEZZA · 9 vicini</div>
          <div className="row" style={{ gap: 12, marginTop: 4 }}>
            <MetricBlock label="MEAN" value={nMean.toFixed(2)} />
            <MetricBlock label="STD" value={nStd.toFixed(2)} />
            <MetricBlock label="STATO" value={robust} color={robustColor} />
          </div>
        </div>

        <div style={{ marginTop: 14 }}>
          <div className="lbl-mono dim">BEST PLATEAU</div>
          <div className="mono" style={{ marginTop: 4 }}>
            [{best[0]},{best[1]}] · Sh <b style={{ color: C2.amber }}>{best[2].toFixed(2)}</b>
          </div>
          <button className="btn" style={{ marginTop: 8 }} onClick={() => setSel([best[0], best[1]])}>JUMP →</button>
        </div>

        {nStd > 0.35 && (
          <div className="warn" style={{ marginTop: 14 }}>
            ⚠ vicini molto rumorosi · probabile overfit
          </div>
        )}
      </Panel>
    </div>
  );
}

// === 6. UNDERWATER ===
function UnderwaterScreen({ run }) {
  return (
    <div className="grid-12" style={{ gap: 6 }}>
      <Panel title="UNDERWATER · all-time" sub="depth %" style={{ gridColumn: "span 12" }}>
        <DrawdownChart equity={run.equity} height={200} color={C2.coral} />
      </Panel>

      <Panel title="TOP 5 DRAWDOWNS" style={{ gridColumn: "span 7" }}>
        <div className="tbl">
          <div className="tr h" style={{ gridTemplateColumns: "30px 1fr 80px 80px 80px 1fr" }}>
            <span>#</span><span>PERIOD</span><span>DEPTH</span><span>LEN</span><span>RECOV</span><span>SHAPE</span>
          </div>
          {run.ddPeriods.map((dd, i) => {
            const slice = run.equity.slice(dd.start, dd.end + 1).map(e => e.dd);
            return (
              <div key={i} className="tr" style={{ gridTemplateColumns: "30px 1fr 80px 80px 80px 1fr" }}>
                <span className="dim">{i + 1}</span>
                <span className="dim">t{dd.start} → t{dd.end}</span>
                <span style={{ color: C2.coral, fontWeight: 700 }}>{(dd.depth * 100).toFixed(1)}%</span>
                <span>{dd.length}</span>
                <span>{dd.recovery}</span>
                <Sparkline data={slice.map(d => -d)} width={120} height={14} color={C2.coral} />
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel title="DD DISTRIBUTION" sub="depths · histogram" style={{ gridColumn: "span 5" }}>
        <Histogram
          data={run.ddPeriods.concat([{ depth: -0.02 }, { depth: -0.015 }, { depth: -0.04 }, { depth: -0.03 }, { depth: -0.022 }, { depth: -0.05 }, { depth: -0.07 }]).map(d => d.depth * 100)}
          height={130}
          bins={16}
          color={C2.coral}
          fmt={(v) => v.toFixed(0) + "%"}
        />
        <div className="row" style={{ gap: 12, marginTop: 8 }}>
          <MetricBlock label="MEDIAN DD" value={(run.metricsOOS.maxDD * 0.4).toFixed(1) + "%"} color={C2.coral} />
          <MetricBlock label="WORST DD" value={run.metricsOOS.maxDD + "%"} color={C2.coral} big />
          <MetricBlock label="MEAN REC" value={Math.round(run.ddPeriods.reduce((a, d) => a + d.recovery, 0) / run.ddPeriods.length) + "d"} color={C2.amber} />
        </div>
      </Panel>
    </div>
  );
}

// === 7. MONTE CARLO ===
function MonteCarloScreen({ run }) {
  const mc = run.mc;
  const at = (arr, q) => arr[Math.floor((arr.length - 1) * q)];
  const finals = mc.finals;
  const ddFinals = mc.ddFinals;
  const p5 = (at(finals, 0.05) - 1) * 100;
  const p50 = (at(finals, 0.5) - 1) * 100;
  const p95 = (at(finals, 0.95) - 1) * 100;
  const probProfit = finals.filter(v => v > 1).length / finals.length * 100;
  const probRuin = finals.filter(v => v < 0.5).length / finals.length * 100;
  const sharpe = run.metricsOOS.sharpe;
  const ciLo = (sharpe * 0.65).toFixed(2);
  const ciHi = (sharpe * 1.35).toFixed(2);
  return (
    <div className="grid-12" style={{ gap: 6 }}>
      <Panel
        title="EQUITY FAN · p5 / p25 / p50 / p75 / p95"
        sub="n=1000 · bootstrap trades"
        style={{ gridColumn: "span 8" }}>
        <FanChart mc={mc} height={280} color={C2.amber} />
      </Panel>

      <Panel title="OUTCOMES" style={{ gridColumn: "span 4" }}>
        <div className="row" style={{ gap: 6, marginBottom: 8 }}>
          <MetricBlock label="P(profit) 1Y" value={probProfit.toFixed(0) + "%"} color={C2.green} big />
          <MetricBlock label="P(ruin)" value={probRuin.toFixed(1) + "%"} color={probRuin > 1 ? C2.coral : C2.dim} big />
        </div>
        <div className="metric-grid">
          <MetricBlock label="p5 final" value={p5.toFixed(1) + "%"} color={C2.amber} />
          <MetricBlock label="p50 final" value={p50.toFixed(1) + "%"} color={C2.amber} />
          <MetricBlock label="p95 final" value={p95.toFixed(1) + "%"} color={C2.amber} />
        </div>
        <div style={{ marginTop: 14 }}>
          <div className="lbl-mono dim">SHARPE · 95% CI</div>
          <div className="mono" style={{ fontSize: 24, fontWeight: 700, color: C2.amber, marginTop: 2 }}>
            {sharpe} <span style={{ color: C2.dim, fontSize: 14, fontWeight: 400 }}>[ {ciLo} — {ciHi} ]</span>
          </div>
          <div className="lbl-mono dim" style={{ marginTop: 4 }}>
            t ≈ {(sharpe * 2.3).toFixed(1)} · p &lt; 0.001 · <span style={{ color: C2.green }}>SIGNIFICATIVO</span>
          </div>
        </div>
      </Panel>

      <Panel title="FINAL RETURN · distribution" style={{ gridColumn: "span 6" }}>
        <Histogram data={finals.map(v => (v - 1) * 100)} height={150} bins={28} color={C2.amber}
          fmt={(v) => v.toFixed(0) + "%"} />
      </Panel>

      <Panel title="MAX DD · distribution" style={{ gridColumn: "span 6" }}>
        <Histogram data={ddFinals.map(v => v * 100)} height={150} bins={24} color={C2.coral}
          fmt={(v) => v.toFixed(0) + "%"} />
      </Panel>
    </div>
  );
}

// === 8. COMPARE ===
function CompareScreen({ runs, activeIds, toggleActive }) {
  const colors = { r1: C2.amber, r2: C2.cyan, r3: C2.green, r4: C2.coral };
  const active = runs.filter(r => activeIds.includes(r.id));
  const wrap = useRef(null);
  const [w, setW] = useState(800);
  useEffect(() => {
    const ro = new ResizeObserver(es => { if (es[0]) setW(es[0].contentRect.width); });
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  const padL = 44, padR = 12, padT = 8, padB = 18;
  const h = 280;
  const innerW = Math.max(50, w - padL - padR);
  const innerH = h - padT - padB;
  const allV = active.flatMap(r => r.equity.map(e => e.v));
  const mn = Math.min(...allV) * 0.98, mx = Math.max(...allV) * 1.02;
  const xy = (i, v, len) => [padL + (i / (len - 1)) * innerW, padT + innerH - ((v - mn) / (mx - mn)) * innerH];

  // simple correlation matrix between equity returns
  const correlations = useMemo(() => {
    const ret = (r) => { const a = []; for (let i = 1; i < r.equity.length; i++) a.push(r.equity[i].v / r.equity[i - 1].v - 1); return a; };
    const corr = (a, b) => {
      const ma = a.reduce((x, y) => x + y, 0) / a.length;
      const mb = b.reduce((x, y) => x + y, 0) / b.length;
      let num = 0, da = 0, db = 0;
      for (let i = 0; i < Math.min(a.length, b.length); i++) {
        num += (a[i] - ma) * (b[i] - mb);
        da += (a[i] - ma) ** 2;
        db += (b[i] - mb) ** 2;
      }
      return num / Math.sqrt(da * db);
    };
    const out = [];
    for (let i = 0; i < active.length; i++) for (let j = i + 1; j < active.length; j++) {
      out.push({ a: active[i].name, b: active[j].name, c: corr(ret(active[i]), ret(active[j])) });
    }
    return out;
  }, [active]);

  return (
    <div className="grid-12" style={{ gap: 6 }}>
      <Panel title="COMPARE · select runs" sub={`${active.length} active`} style={{ gridColumn: "span 12" }}>
        <div className="row" style={{ gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
          {runs.map(r => (
            <span key={r.id} className={`run-chip ${activeIds.includes(r.id) ? "on" : ""}`}
              onClick={() => toggleActive(r.id)}
              style={{ borderColor: colors[r.id], color: activeIds.includes(r.id) ? colors[r.id] : C2.dim }}>
              <span className="run-dot" style={{ background: colors[r.id] }}></span>
              {r.name}
              <span className="lbl-mono dim">· Sh {r.metricsOOS.sharpe}</span>
            </span>
          ))}
        </div>

        <div ref={wrap} style={{ width: "100%", height: h }}>
          <svg width={w} height={h} style={{ display: "block" }}>
            {[0.25, 0.5, 0.75, 1].map((q, i) => {
              const v = mn + (mx - mn) * q;
              const y = padT + innerH - q * innerH;
              return (
                <g key={i}>
                  <line x1={padL} x2={padL + innerW} y1={y} y2={y} stroke={C2.border} strokeDasharray="2 4" />
                  <text x={padL - 6} y={y + 3} fill={C2.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">{((v - 1) * 100).toFixed(0)}%</text>
                </g>
              );
            })}
            {active.map(r => {
              const pts = r.equity.map((e, i) => xy(i, e.v, r.equity.length));
              return (
                <path key={r.id} d={lineFromPoints(pts)} fill="none" stroke={colors[r.id]} strokeWidth="1.6" opacity="0.9" />
              );
            })}
          </svg>
        </div>

        <div className="tbl" style={{ marginTop: 10 }}>
          <div className="tr h" style={{ gridTemplateColumns: "1fr repeat(6, 1fr)" }}>
            <span></span><span>CAGR</span><span>SHARPE</span><span>SORTINO</span><span>MAXDD</span><span>PF</span><span>TRADES</span>
          </div>
          {active.map(r => (
            <div key={r.id} className="tr" style={{ gridTemplateColumns: "1fr repeat(6, 1fr)" }}>
              <span style={{ color: colors[r.id], fontWeight: 700 }}>{r.name}</span>
              <span style={{ color: C2.green }}>+{r.metricsOOS.cagr}%</span>
              <span>{r.metricsOOS.sharpe}</span>
              <span>{r.metricsOOS.sortino}</span>
              <span style={{ color: C2.coral }}>{r.metricsOOS.maxDD}%</span>
              <span>{r.profitFactor}</span>
              <span>{r.tradesCount}</span>
            </div>
          ))}
        </div>

        {correlations.length > 0 && (
          <div className="row" style={{ marginTop: 10, gap: 12, flexWrap: "wrap" }}>
            <span className="lbl-mono dim">CORRELAZIONI EQUITY:</span>
            {correlations.map((c, i) => (
              <span key={i} className="mono" style={{ color: Math.abs(c.c) < 0.4 ? C2.green : C2.amber }}>
                {c.a.slice(0, 8)} · {c.b.slice(0, 8)} <b>{c.c.toFixed(2)}</b>
              </span>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

Object.assign(window, {
  DashboardScreen, SetupScreen, EquityScreen, TradesScreen,
  SweepScreen, UnderwaterScreen, MonteCarloScreen, CompareScreen,
  Panel, MetricBlock, Pill
});
