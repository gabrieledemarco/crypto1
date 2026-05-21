"use client";
import { useEffect, useRef, useState, useMemo } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunTrades, isRealRunId } from "@/hooks/useRun";
import { useAssetBars } from "@/hooks/useAssets";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import type { TradeMarker } from "@/components/charts/CandlestickChart";
import { Sparkline } from "@/components/charts/Sparkline";
import { TradeAnalysisPanels } from "./TradeAnalysisScreen";
import styles from "./TradesScreen.module.css";
import type { Trade } from "@/lib/fixtures";

const MAX_CHART_BARS = 300;

// ─── Shared color helper ──────────────────────────────────────────────────────
function lerp3(t: number, a: [number,number,number], b: [number,number,number]) {
  return `rgb(${Math.round(a[0]+(b[0]-a[0])*t)},${Math.round(a[1]+(b[1]-a[1])*t)},${Math.round(a[2]+(b[2]-a[2])*t)})`;
}
const CORAL: [number,number,number] = [255,122,85];
const GREEN: [number,number,number] = [111,209,122];
const MID:   [number,number,number] = [185,165,105];
const GRAY = "#3a3c28";
function wrColor(wr: number) {
  if (wr < 0) return GRAY;
  return wr < 0.5 ? lerp3(wr/0.5, CORAL, MID) : lerp3((wr-0.5)/0.5, MID, GREEN);
}

// ─── Feature 1: Day-of-Week Heatmap ──────────────────────────────────────────
const DOW_LABELS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const DOW_ORDER  = [1,2,3,4,5,6,0]; // Mon-first; JS getDay 0=Sun
const SIDES = ["L","S","ALL"] as const;

function computeDow(trades: Trade[]) {
  return DOW_ORDER.flatMap((dow, ri) =>
    SIDES.map(side => {
      const sub = trades.filter(t =>
        new Date(t.date).getDay() === dow && (side==="ALL" || t.side===side));
      const wins = sub.filter(t => t.pnl > 0).length;
      return { dow, side, ri, total: sub.length, wr: sub.length > 0 ? wins/sub.length : -1 };
    })
  );
}

function DowHeatmap({ trades }: { trades: Trade[] }) {
  const cells = useMemo(() => computeDow(trades), [trades]);
  if (!trades.length) return <div className={styles.vizEmpty}>no data</div>;
  const CW=56, CH=22, LW=30, HDR=18;
  const W = LW + 3*CW + 2, H = HDR + 7*CH + 2;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{width:W,height:H,display:"block"}}>
      {SIDES.map((s,ci) => (
        <text key={s} x={LW+ci*CW+CW/2} y={HDR-4} textAnchor="middle" fontSize={8} fill="#888" fontFamily="var(--font-mono)">{s==="L"?"LONG":s==="S"?"SHORT":"ALL"}</text>
      ))}
      {DOW_ORDER.map((dow, ri) => {
        const y = HDR + ri*CH;
        return (
          <g key={dow}>
            <text x={LW-3} y={y+CH/2+4} textAnchor="end" fontSize={8} fill="#888" fontFamily="var(--font-mono)">{DOW_LABELS[ri]}</text>
            {SIDES.map((side, ci) => {
              const c = cells.find(x => x.dow===dow && x.side===side)!;
              const x = LW + ci*CW;
              return (
                <g key={side}>
                  <rect x={x+1} y={y+1} width={CW-2} height={CH-2} fill={wrColor(c.wr)} rx={2}/>
                  {c.wr >= 0 ? (
                    <>
                      <text x={x+CW/2} y={y+CH/2+2} textAnchor="middle" fontSize={8} fontWeight={700} fill="#fff" fontFamily="var(--font-mono)">{Math.round(c.wr*100)}%</text>
                      <text x={x+CW-3} y={y+CH-3} textAnchor="end" fontSize={6} fill="rgba(255,255,255,0.5)" fontFamily="var(--font-mono)">{c.total}</text>
                    </>
                  ) : (
                    <text x={x+CW/2} y={y+CH/2+3} textAnchor="middle" fontSize={7} fill="#555" fontFamily="var(--font-mono)">—</text>
                  )}
                </g>
              );
            })}
          </g>
        );
      })}
    </svg>
  );
}

// ─── Feature 2: Holding Time Histogram ───────────────────────────────────────
const DUR_LABELS = ["<1h","1-4h","4-8h","8-24h","1-3d",">3d"];
const DUR_EDGES  = [0,1,4,8,24,72,Infinity];
function durBin(h: number) {
  for (let i=0; i<DUR_EDGES.length-1; i++) if (h>=DUR_EDGES[i] && h<DUR_EDGES[i+1]) return i;
  return DUR_EDGES.length-2;
}

function HoldingHistogram({ trades }: { trades: Trade[] }) {
  const counts = useMemo(() => {
    const a = new Array<number>(DUR_LABELS.length).fill(0);
    trades.forEach(t => { if (t.durH!=null) a[durBin(t.durH)]++; });
    return a;
  }, [trades]);
  const total = counts.reduce((s,c)=>s+c,0);
  if (!total) return <div className={styles.vizEmpty}>no data</div>;
  const maxC = Math.max(...counts, 1);
  const BH=14, GAP=3, LW=36, BAR=160, STATW=64;
  const W = LW+BAR+STATW+4, H = DUR_LABELS.length*(BH+GAP)+4;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{width:W,height:H,display:"block"}}>
      {DUR_LABELS.map((lbl, i) => {
        const c=counts[i], pct=((c/total)*100).toFixed(0), bw=(c/maxC)*BAR, y=i*(BH+GAP)+2;
        return (
          <g key={lbl}>
            <text x={LW-3} y={y+BH/2+3} textAnchor="end" fontSize={8} fill="#888" fontFamily="var(--font-mono)">{lbl}</text>
            <rect x={LW} y={y} width={BAR} height={BH} fill="rgba(255,255,255,0.04)" rx={2}/>
            {bw>0 && <rect x={LW} y={y} width={bw} height={BH} fill="var(--amber)" rx={2} opacity={0.85}/>}
            <text x={LW+BAR+4} y={y+BH/2+3} fontSize={8} fill="#aaa" fontFamily="var(--font-mono)">{c} · {pct}%</text>
          </g>
        );
      })}
    </svg>
  );
}

// ─── Feature 3: PnL CDF ──────────────────────────────────────────────────────
function PnlCdf({ trades }: { trades: Trade[] }) {
  const cdf = useMemo(() => {
    if (!trades.length) return null;
    const sorted = [...trades].map(t=>t.pnl).sort((a,b)=>a-b);
    return { sorted, n: sorted.length, min: sorted[0], max: sorted[sorted.length-1] };
  }, [trades]);
  if (!cdf) return <div className={styles.vizEmpty}>no data</div>;
  const { sorted, n, min, max } = cdf;
  const W=280, H=90, PL=30, PR=8, PT=8, PB=16;
  const PW=W-PL-PR, PH=H-PT-PB, rng=max-min||1;
  const xOf=(p:number) => PL+((p-min)/rng)*PW;
  const yOf=(pr:number) => PT+(1-pr)*PH;
  const polyline = sorted.map((p,i)=>`${xOf(p).toFixed(1)},${yOf((i+1)/n).toFixed(1)}`).join(" ");
  const showZero = min<0 && max>0;
  const zX = xOf(0);
  // loss shade path
  const lossPts = sorted.filter(p=>p<=0).map((p,i)=>`${xOf(p).toFixed(1)},${yOf((i+1)/n).toFixed(1)}`).join(" ");
  const shade = lossPts ? `M${PL},${PT+PH} L${PL},${yOf(sorted.filter(p=>p<=0).length/n)} ${lossPts} L${zX},${PT+PH} Z` : "";
  const yTicks = [[1,"100%"],[0.75,"75%"],[0.5,"50%"],[0.25,"25%"],[0,"0%"]] as const;
  return (
    <div className={styles.cdfWrap}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{width:W,height:H,display:"block"}}>
        <rect x={PL} y={PT} width={PW} height={PH} fill="rgba(255,255,255,0.02)" stroke="rgba(255,255,255,0.06)" strokeWidth={0.5}/>
        {yTicks.map(([pr,lbl]) => (
          <g key={lbl}>
            <line x1={PL} y1={yOf(pr)} x2={PL+PW} y2={yOf(pr)} stroke="rgba(255,255,255,0.07)" strokeWidth={0.5}/>
            <text x={PL-3} y={yOf(pr)+3} textAnchor="end" fontSize={6.5} fill="#666" fontFamily="var(--font-mono)">{lbl}</text>
          </g>
        ))}
        {showZero && <line x1={zX} y1={PT} x2={zX} y2={PT+PH} stroke="rgba(255,255,255,0.25)" strokeWidth={0.8} strokeDasharray="3,2"/>}
        {shade && <path d={shade} fill="rgba(255,122,85,0.12)"/>}
        <polyline points={polyline} fill="none" stroke="var(--cyan)" strokeWidth={1.5} strokeLinejoin="round"/>
        <text x={PL} y={H-2} textAnchor="middle" fontSize={6.5} fill="#555" fontFamily="var(--font-mono)">{min.toFixed(1)}</text>
        {showZero && <text x={zX} y={H-2} textAnchor="middle" fontSize={6.5} fill="#888" fontFamily="var(--font-mono)">0</text>}
        <text x={PL+PW} y={H-2} textAnchor="middle" fontSize={6.5} fill="#555" fontFamily="var(--font-mono)">{max.toFixed(1)}</text>
      </svg>
      <div className={styles.cdfCaption}>P(trade PnL ≤ x)</div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export function TradesScreen() {
  const { activeRunId, runs } = useStore();
  const [filterSide, setFilterSide] = useState("all");
  const [filterPnl, setFilterPnl] = useState("all");
  const [filterText, setFilterText] = useState("");
  const [sortKey, setSortKey] = useState<keyof Trade>("n");
  const [sortDir, setSortDir] = useState<1 | -1>(1);
  const [cursor, setCursor] = useState(0);
  const filterRef = useRef<HTMLInputElement>(null);

  const run = runs.find((r) => r.id === activeRunId) ?? fixtures.runs[0];
  const isReal = isRealRunId(activeRunId);
  const tradesQuery = useRunTrades(activeRunId || null, { limit: 500 });
  const allTrades: Trade[] =
    tradesQuery.data?.trades && tradesQuery.data.trades.length > 0
      ? (tradesQuery.data.trades as Trade[])
      : run?.trades ?? [];

  const ticker = isReal ? (run?.strategy ?? null) : null;
  const interval = run?.params?.timeframe ?? "1d";
  const { data: bars } = useAssetBars(ticker, interval);

  const tradeMarkers = useMemo((): TradeMarker[] => {
    if (!bars?.length || !allTrades.length) return [];
    const visible = bars.slice(-MAX_CHART_BARS);
    const firstTs = visible[0]?.ts ? new Date(visible[0].ts).getTime() : 0;
    const lastTs = visible[visible.length-1]?.ts ? new Date(visible[visible.length-1].ts!).getTime() : Infinity;
    return allTrades
      .filter(t => t.date >= firstTs && t.date <= lastTs)
      .map(t => ({ entryTs: t.date, entryPrice: t.entry, exitTs: t.date + t.durH*3600*1000, exitPrice: t.exit, side: t.side, win: t.pnl > 0 }));
  }, [allTrades, bars]);

  const filteredTrades = useMemo(() =>
    [...allTrades]
      .filter(t => {
        if (filterSide==="long"  && t.side!=="L") return false;
        if (filterSide==="short" && t.side!=="S") return false;
        if (filterPnl==="win"  && t.pnl<=0) return false;
        if (filterPnl==="loss" && t.pnl>0)  return false;
        if (filterText) {
          const q = filterText.toLowerCase();
          return String(t.n).includes(q) || (t.side==="L"?"long":"short").includes(q) ||
                 String(t.entry).includes(q) || String(t.pnl).includes(q);
        }
        return true;
      })
      .sort((a,b) => {
        const av=a[sortKey], bv=b[sortKey];
        if (av==null||bv==null) return 0;
        return (av<bv?-1:av>bv?1:0)*sortDir;
      }),
    [allTrades, filterSide, filterPnl, filterText, sortKey, sortDir]
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (document.activeElement as HTMLElement)?.tagName;
      if (tag==="INPUT"||tag==="TEXTAREA") return;
      if (e.key==="j") { setCursor(c=>Math.min(filteredTrades.length-1,c+1)); e.preventDefault(); }
      else if (e.key==="k") { setCursor(c=>Math.max(0,c-1)); e.preventDefault(); }
      else if (e.key==="f") { filterRef.current?.focus(); e.preventDefault(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filteredTrades.length]);

  const equity = run?.equity ?? [];
  const winners = allTrades.filter(t=>t.pnl>0).length;
  const cols = "32px 72px 44px 88px 88px 52px 52px 72px 88px";

  function SortHeader({ k, label }: { k: keyof Trade; label: string }) {
    return (
      <span className={styles.sortable} onClick={() => {
        if (sortKey===k) setSortDir(d=>d===1?-1:1);
        else { setSortKey(k); setSortDir(1); }
      }}>
        {label}{sortKey===k?(sortDir>0?" ↑":" ↓"):""}
      </span>
    );
  }

  return (
    <div className={styles.page}>

      {bars && bars.length > 0 && (
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>PRICE · {ticker} · {interval.toUpperCase()}</span>
            <span className={styles.panelSub}>
              {tradeMarkers.length} trades ·{" "}
              <span style={{color:"#ffb53b"}}>▲</span> entry ·{" "}
              <span style={{color:"var(--green)"}}>◆</span> exit win ·{" "}
              <span style={{color:"var(--coral)"}}>◆</span> exit loss
            </span>
          </div>
          <CandlestickChart bars={bars} height={240} maxBars={MAX_CHART_BARS} markers={tradeMarkers} showEMA20/>
        </div>
      )}

      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>TRADE LOG</span>
          <span className={styles.panelSub}>{filteredTrades.length} of {allTrades.length}</span>
          <span style={{flex:1}}/>
          <span className={styles.counts}>
            <span style={{color:"var(--amber)"}}>{allTrades.filter(t=>t.side==="L").length} L</span>
            &nbsp;·&nbsp;
            <span style={{color:"var(--cyan)"}}>{allTrades.filter(t=>t.side==="S").length} S</span>
            &nbsp;·&nbsp;
            <span style={{color:"var(--green)"}}>{winners} win</span>
            &nbsp;·&nbsp;
            <span style={{color:"var(--coral)"}}>{allTrades.length-winners} loss</span>
          </span>
          <button className={styles.btn} onClick={() => {
            const header = "#,OPEN,SIDE,ENTRY,EXIT,R,DUR(h),P&L%";
            const rows = filteredTrades.map((t,i) =>
              [i+1, new Date(t.date).toISOString().slice(0,16),
               t.side==="L"?"L":"S", t.entry?.toFixed(2)??"",
               t.exit?.toFixed(2)??"", t.r?.toFixed(2)??"",
               t.durH??"", t.pnl??""
              ].join(","));
            const csv = [header,...rows].join("\n");
            const blob = new Blob([csv],{type:"text/csv"});
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href=url; a.download=`trades_${Date.now()}.csv`; a.click();
            URL.revokeObjectURL(url);
          }}>↓ CSV</button>
        </div>

        <div className={styles.filterBar}>
          <span className={styles.filterLabel}>side:</span>
          {["all","long","short"].map(s=>(
            <button key={s} className={`${styles.pill} ${filterSide===s?styles.active:""}`} onClick={()=>setFilterSide(s)}>{s}</button>
          ))}
          <span className={styles.filterLabel} style={{marginLeft:12}}>pnl:</span>
          {["all","win","loss"].map(s=>(
            <button key={s} className={`${styles.pill} ${filterPnl===s?styles.active:""}`} onClick={()=>setFilterPnl(s)}>{s}</button>
          ))}
          <input ref={filterRef} className={styles.filterInput} placeholder="filter…" style={{marginLeft:"auto"}} value={filterText} onChange={e=>setFilterText(e.target.value)}/>
        </div>

        <div className={styles.tableWrap}>
          <div className={styles.thead} style={{gridTemplateColumns:cols}}>
            <span><SortHeader k="n" label="#"/></span>
            <span><SortHeader k="date" label="OPEN"/></span>
            <span><SortHeader k="side" label="SIDE"/></span>
            <span><SortHeader k="entry" label="ENTRY"/></span>
            <span><SortHeader k="exit" label="EXIT"/></span>
            <span><SortHeader k="r" label="R"/></span>
            <span><SortHeader k="durH" label="DUR"/></span>
            <span><SortHeader k="pnl" label="P&L%"/></span>
            <span>EQUITY</span>
          </div>
          {filteredTrades.slice(0,200).map((t,i) => (
            <div key={t.n} className={`${styles.trow} ${cursor===i?styles.selected:""}`} onClick={()=>setCursor(i)} style={{gridTemplateColumns:cols}}>
              <span className={styles.dim}>{String(t.n).padStart(3,"0")}</span>
              <span className={styles.dim}>t{String(t.idx).padStart(3,"0")}</span>
              <span style={{color:t.side==="L"?"var(--amber)":"var(--cyan)",fontWeight:700}}>{t.side}</span>
              <span>{t.entry?.toLocaleString()}</span>
              <span>{t.exit?.toLocaleString()}</span>
              <span style={{color:t.r>0?"var(--green)":"var(--coral)"}}>{t.r?.toFixed(1)}</span>
              <span>{t.durH}h</span>
              <span style={{color:t.pnl>0?"var(--green)":"var(--coral)",fontWeight:700}}>{t.pnl>0?"+":""}{t.pnl}</span>
              <Sparkline data={equity.slice(Math.max(0,t.idx-5),t.idx+2).map(e=>e.v)} width={80} height={12} color={t.pnl>0?"#6fd17a":"#ff7a55"}/>
            </div>
          ))}
        </div>

        <div className={styles.footer}>
          <span className={styles.dim}><kbd>j</kbd>↓ <kbd>k</kbd>↑ · <kbd>f</kbd> filter</span>
          <span style={{flex:1}}/>
          <span className={styles.dim}>cursor {cursor+1}/{filteredTrades.length}</span>
        </div>
      </div>

      <TradeAnalysisPanels trades={allTrades}/>

      {/* ── Quant visualizations ── */}
      <div className={styles.quantRow}>
        <div className={styles.quantPanel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>DAY-OF-WEEK</span>
            <span className={styles.panelSub}>win rate · L / S / ALL</span>
          </div>
          <div className={styles.quantBody}><DowHeatmap trades={allTrades}/></div>
        </div>

        <div className={styles.quantPanel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>HOLDING TIME DISTRIBUTION</span>
            <span className={styles.panelSub}>{allTrades.length} trades</span>
          </div>
          <div className={styles.quantBody}><HoldingHistogram trades={allTrades}/></div>
        </div>

        <div className={styles.quantPanel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>PnL CDF</span>
            <span className={styles.panelSub}>cumulative distribution</span>
          </div>
          <div className={styles.quantBody}><PnlCdf trades={allTrades}/></div>
        </div>
      </div>

    </div>
  );
}
