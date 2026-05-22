/* PARETO — shell: topbar, sidebar, command palette, hotkeys */
const Cs = window.PARETO_C;

const SCREENS = [
  { id: "dashboard", label: "DASHBOARD", letter: "d", num: 1, group: "WORKSPACE" },
  { id: "assets", label: "ASSETS", letter: "a", num: 2, group: "DATA" },
  { id: "library", label: "LIBRARY", letter: "l", num: 3, group: "DATA" },
  { id: "vibe", label: "VIBE TRADING", letter: "v", num: 4, group: "BUILD" },
  { id: "setup", label: "SETUP", letter: "s", num: 5, group: "BUILD" },
  { id: "equity", label: "EQUITY", letter: "e", num: 6, group: "ANALYZE" },
  { id: "trades", label: "TRADES", letter: "t", num: 7, group: "ANALYZE" },
  { id: "sweep", label: "PARAM SWEEP", letter: "p", num: 8, group: "ANALYZE" },
  { id: "underwater", label: "UNDERWATER", letter: "u", num: 9, group: "ANALYZE" },
  { id: "mc", label: "MONTE CARLO", letter: "m", num: 0, group: "ANALYZE" },
  { id: "compare", label: "COMPARE", letter: "c", num: null, group: "ANALYZE" }
];

function TopBar({ run, runs, setRunId, openPalette, screenLabel }) {
  return (
    <div className="topbar">
      <div className="brand">
        <span className="brand-mark"></span>
        <span className="brand-name">PARETO</span>
        <span className="brand-sub">backtest terminal</span>
      </div>
      <div className="crumb">
        <span className="dim">RUNS /</span>
        <select className="run-select"
          value={run.id} onChange={e => setRunId(e.target.value)}>
          {runs.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        <span className="dim"> / </span>
        <span className="crumb-active">{screenLabel}</span>
      </div>
      <div className="ribbon">
        <RibbonStat label="CAGR" v={`+${run.metricsOOS.cagr}%`} color={Cs.green} />
        <RibbonStat label="SHARPE" v={run.metricsOOS.sharpe} />
        <RibbonStat label="MAXDD" v={`${run.metricsOOS.maxDD}%`} color={Cs.coral} />
        <RibbonStat label="PF" v={run.profitFactor} />
        <RibbonStat label="TRADES" v={run.tradesCount} />
      </div>
      <button className="palette-btn" onClick={openPalette}>
        <span className="lbl-mono">⌘K</span>
      </button>
    </div>
  );
}

function RibbonStat({ label, v, color }) {
  return (
    <div className="ribbon-stat">
      <span className="lbl-mono dim">{label}</span>
      <span className="mono" style={{ color: color || Cs.amber, fontWeight: 700 }}>{v}</span>
    </div>
  );
}

function Sidebar({ active, goto }) {
  const groups = [];
  SCREENS.forEach(s => {
    let g = groups.find(x => x.name === s.group);
    if (!g) { g = { name: s.group, items: [] }; groups.push(g); }
    g.items.push(s);
  });
  return (
    <nav className="sidebar">
      {groups.map(g => (
        <div key={g.name} className="side-group">
          <div className="side-group-h">{g.name}</div>
          {g.items.map(s => (
            <button
              key={s.id}
              className={`side-item ${active === s.id ? "on" : ""}`}
              onClick={() => goto(s.id)}>
              <span className="side-num">{s.num != null ? "F" + s.num : "··"}</span>
              <span className="side-lbl">{s.label}</span>
              <span className="side-hk">g·{s.letter}</span>
            </button>
          ))}
        </div>
      ))}
      <div className="side-foot">
        <div className="lbl-mono dim">HOTKEYS</div>
        <div className="hk-row"><kbd>⌘K</kbd><span>palette</span></div>
        <div className="hk-row"><kbd>g</kbd>+<kbd>x</kbd><span>go to</span></div>
        <div className="hk-row"><kbd>1</kbd>…<kbd>8</kbd><span>screen</span></div>
        <div className="hk-row"><kbd>j</kbd>/<kbd>k</kbd><span>nav rows</span></div>
        <div className="hk-row"><kbd>r</kbd><span>re-run</span></div>
        <div className="hk-row"><kbd>?</kbd><span>help</span></div>
      </div>
    </nav>
  );
}

function Palette({ open, close, actions }) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const inputRef = useRef(null);
  useEffect(() => { if (open) { setQ(""); setIdx(0); setTimeout(() => inputRef.current?.focus(), 20); } }, [open]);
  const filtered = actions.filter(a => a.label.toLowerCase().includes(q.toLowerCase()) || (a.hint || "").toLowerCase().includes(q.toLowerCase()));
  useEffect(() => { setIdx(0); }, [q]);
  const onKey = (e) => {
    if (e.key === "ArrowDown") { setIdx(i => Math.min(filtered.length - 1, i + 1)); e.preventDefault(); }
    else if (e.key === "ArrowUp") { setIdx(i => Math.max(0, i - 1)); e.preventDefault(); }
    else if (e.key === "Enter") { filtered[idx]?.run(); close(); }
    else if (e.key === "Escape") { close(); }
  };
  if (!open) return null;
  return (
    <div className="palette-wrap" onClick={close}>
      <div className="palette" onClick={e => e.stopPropagation()}>
        <input ref={inputRef} className="palette-input" placeholder="cerca azione, schermata, run…"
          value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKey} />
        <div className="palette-list">
          {filtered.length === 0 && <div className="palette-empty">nessun risultato</div>}
          {filtered.slice(0, 12).map((a, i) => (
            <div key={a.label} className={`palette-item ${i === idx ? "on" : ""}`}
              onMouseEnter={() => setIdx(i)}
              onClick={() => { a.run(); close(); }}>
              <span className="palette-icon" style={{ color: a.color || Cs.amber }}>{a.icon || "›"}</span>
              <span className="palette-label">{a.label}</span>
              {a.hint && <span className="palette-hint">{a.hint}</span>}
              {a.key && <span className="palette-key">{a.key}</span>}
            </div>
          ))}
        </div>
        <div className="palette-foot lbl-mono dim">
          <kbd>↑↓</kbd> nav · <kbd>↵</kbd> select · <kbd>esc</kbd> close
        </div>
      </div>
    </div>
  );
}

function HelpToast({ open, close }) {
  if (!open) return null;
  return (
    <div className="help-toast" onClick={close}>
      <div className="help-card" onClick={e => e.stopPropagation()}>
        <div className="help-h">HOTKEYS</div>
        <div className="help-grid">
          <div><kbd>⌘K</kbd> command palette</div>
          <div><kbd>g</kbd>+<kbd>d</kbd>/<kbd>s</kbd>/<kbd>e</kbd>/<kbd>t</kbd>/<kbd>p</kbd>/<kbd>u</kbd>/<kbd>m</kbd>/<kbd>c</kbd> go to screen</div>
          <div><kbd>1</kbd>…<kbd>8</kbd> direct screen</div>
          <div><kbd>j</kbd>/<kbd>k</kbd> down / up in lists</div>
          <div><kbd>r</kbd> re-run current setup</div>
          <div><kbd>[</kbd>/<kbd>]</kbd> previous / next run</div>
          <div><kbd>?</kbd> this help</div>
          <div><kbd>esc</kbd> dismiss overlays</div>
        </div>
        <button className="btn" onClick={close}>close</button>
      </div>
    </div>
  );
}

// =================== ROOT APP ===================
function App() {
  const data = window.ParetoData;
  const [runs, setRuns] = useState(data.runs);
  const [savedStrategies, setSavedStrategies] = useState(data.library);
  const [runId, setRunId] = useState(data.runs[0].id);
  const [screen, setScreen] = useState("dashboard");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [compareIds, setCompareIds] = useState(["r1", "r2", "r3"]);
  const [gPrefix, setGPrefix] = useState(false);
  const [toast, setToast] = useState(null);

  const run = runs.find(r => r.id === runId);
  const setRun = (id) => setRunId(id);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 1800);
  };

  const goto = useCallback((id) => {
    setScreen(id);
    const s = SCREENS.find(x => x.id === id);
    if (s) showToast(`→ ${s.label}`);
  }, []);

  const mutateParams = (patch) => {
    setRuns(rs => rs.map(r => r.id === runId ? { ...r, params: { ...r.params, ...patch } } : r));
  };

  const runAll = () => {
    showToast("RUN started · simulated");
    setTimeout(() => showToast("RUN complete · Sh " + run.metricsOOS.sharpe), 900);
  };

  const toggleCompare = (id) => {
    setCompareIds(ids => ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id]);
  };

  // hotkeys
  useEffect(() => {
    const onKey = (e) => {
      const tag = (document.activeElement || {}).tagName;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) {
        if (e.key === "Escape") (document.activeElement).blur();
        return;
      }
      // ⌘K / ctrl+k
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); setPaletteOpen(o => !o); return;
      }
      if (e.key === "Escape") { setPaletteOpen(false); setHelpOpen(false); return; }
      if (paletteOpen) return;
      if (e.key === "?") { setHelpOpen(true); return; }
      if (e.key === "g") { setGPrefix(true); setTimeout(() => setGPrefix(false), 1200); return; }
      if (gPrefix) {
        const m = SCREENS.find(s => s.letter === e.key.toLowerCase());
        if (m) { goto(m.id); setGPrefix(false); return; }
      }
      const num = parseInt(e.key, 10);
      if (!isNaN(num)) {
        const s = SCREENS.find(x => x.num === num);
        if (s) goto(s.id);
        return;
      }
      if (e.key === "[") {
        const i = runs.findIndex(r => r.id === runId);
        setRunId(runs[(i - 1 + runs.length) % runs.length].id);
      } else if (e.key === "]") {
        const i = runs.findIndex(r => r.id === runId);
        setRunId(runs[(i + 1) % runs.length].id);
      } else if (e.key.toLowerCase() === "r") {
        runAll();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [gPrefix, paletteOpen, runId, runs]);

  const paletteActions = useMemo(() => {
    const goActions = SCREENS.map(s => ({
      label: `Vai a ${s.label}`,
      hint: s.id,
      key: `g·${s.letter}`,
      icon: "→",
      run: () => goto(s.id)
    }));
    const runActions = runs.map(r => ({
      label: `Carica run · ${r.name}`,
      hint: `Sharpe ${r.metricsOOS.sharpe} · CAGR ${r.metricsOOS.cagr}%`,
      key: "↵",
      icon: "▸",
      color: Cs.cyan,
      run: () => { setRunId(r.id); showToast(`run · ${r.name}`); }
    }));
    const misc = [
      { label: "Re-run corrente", hint: "rilancia il backtest", key: "r", icon: "▶", color: Cs.green, run: runAll },
      { label: "Toggle benchmark", hint: "non implementato qui — placeholder", icon: "·", run: () => showToast("benchmark toggled") },
      { label: "Export CSV trades", icon: "↓", run: () => showToast("export simulato") },
      { label: "Salva snapshot", icon: "💾", run: () => showToast("snapshot salvato") },
      { label: "Mostra hotkeys", key: "?", icon: "?", run: () => setHelpOpen(true) }
    ];
    return [...goActions, ...runActions, ...misc];
  }, [runs, goto]);

  const screenEl = (() => {
    switch (screen) {
      case "dashboard": return <DashboardScreen run={run} runs={runs} setRun={setRun} goto={goto} />;
      case "assets": return <AssetsScreen />;
      case "library": return <LibraryScreen goto={goto} setRunId={setRunId} runs={runs} savedStrategies={savedStrategies} setSavedStrategies={setSavedStrategies} />;
      case "vibe": return <VibeScreen savedStrategies={savedStrategies} setSavedStrategies={setSavedStrategies} goto={goto} showToast={showToast} />;
      case "setup": return <SetupScreen run={run} setRun={setRun} mutateParams={mutateParams} runAll={runAll} />;
      case "equity": return <EquityScreen run={run} />;
      case "trades": return <TradesScreen run={run} />;
      case "sweep": return <SweepScreen run={run} />;
      case "underwater": return <UnderwaterScreen run={run} />;
      case "mc": return <MonteCarloScreen run={run} />;
      case "compare": return <CompareScreen runs={runs} activeIds={compareIds} toggleActive={toggleCompare} />;
      default: return null;
    }
  })();

  const screenLabel = SCREENS.find(s => s.id === screen)?.label || "";

  return (
    <div className="app">
      <TopBar run={run} runs={runs} setRunId={setRunId}
        openPalette={() => setPaletteOpen(true)}
        screenLabel={screenLabel} />
      <div className="body">
        <Sidebar active={screen} goto={goto} />
        <main className="main">
          {screenEl}
        </main>
      </div>
      <StatusBar run={run} runs={runs} screen={screen} gPrefix={gPrefix} />
      <Palette open={paletteOpen} close={() => setPaletteOpen(false)} actions={paletteActions} />
      <HelpToast open={helpOpen} close={() => setHelpOpen(false)} />
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

function StatusBar({ run, runs, screen, gPrefix }) {
  return (
    <div className="statusbar">
      <span><span className="dim">user</span> @ <span style={{ color: Cs.cyan }}>local</span></span>
      <span><span className="dim">run</span> <b>{run.name}</b></span>
      <span><span className="dim">screen</span> <b>{screen}</b></span>
      <span><span className="dim">live</span> <b style={{ color: Cs.green }}>●</b> connected</span>
      <span style={{ flex: 1 }}></span>
      {gPrefix && <span style={{ color: Cs.yellow }}>g · waiting for key…</span>}
      <span className="dim">v0.1 · {new Date().toLocaleTimeString()}</span>
    </div>
  );
}

window.ParetoApp = App;
ReactDOM.createRoot(document.getElementById("root")).render(<App />);
