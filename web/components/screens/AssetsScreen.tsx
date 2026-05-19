"use client";
import { useState, useRef, useEffect, useMemo } from "react";
import { fixtures } from "@/lib/fixtures";
import { useAssets, useAssetBars, useAssetStats } from "@/hooks/useAssets";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { Histogram } from "@/components/charts/Histogram";
import { QQPlot }  from "@/components/charts/QQPlot";
import { ACFPlot } from "@/components/charts/ACFPlot";
import type { Asset } from "@/lib/fixtures";
import styles from "./AssetsScreen.module.css";

const KIND_COLORS: Record<string, string> = {
  spot:      "var(--cyan)",
  perp:      "var(--amber)",
  index:     "var(--green)",
  forex:     "var(--green)",
  stock:     "var(--text)",
  commodity: "var(--amber)",
  crypto:    "var(--cyan)",
};

function getKind(ticker: string): string {
  if (ticker.endsWith("=X")) return "forex";
  if (ticker.endsWith("=F")) return "commodity";
  if (ticker.startsWith("^"))  return "index";
  if (ticker.endsWith("-USD") || ticker.endsWith("-USDT")) return "crypto";
  return "stock";
}

const PERIODS    = ["3mo", "6mo", "1y", "2y", "5y", "max"] as const;
const TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d", "1wk"]  as const;

const ALL_TICKERS = [
  // Crypto — large cap
  "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
  "ADA-USD", "AVAX-USD", "DOGE-USD", "TRX-USD", "DOT-USD",
  "MATIC-USD", "LINK-USD", "SHIB-USD", "LTC-USD", "BCH-USD",
  "UNI-USD", "ATOM-USD", "XLM-USD", "ALGO-USD", "VET-USD",
  "HBAR-USD", "ICP-USD", "NEAR-USD", "FIL-USD", "AAVE-USD",
  "GRT-USD", "MKR-USD", "COMP-USD", "SNX-USD", "CRV-USD",
  "ARB-USD", "OP-USD", "APT-USD", "SUI-USD", "INJ-USD",
  "IMX-USD", "LDO-USD", "RPL-USD", "RNDR-USD", "FTM-USD",
  "SAND-USD", "MANA-USD", "AXS-USD", "ENJ-USD", "CHZ-USD",
  "STX-USD", "TIA-USD", "SEI-USD", "WLD-USD", "JTO-USD",
  "DYDX-USD", "GMX-USD", "RUNE-USD", "ROSE-USD", "ONE-USD",
  "EGLD-USD", "THETA-USD", "ZEC-USD", "DASH-USD", "ETC-USD",
  "XMR-USD", "EOS-USD", "NEO-USD", "IOTA-USD", "WAVES-USD",
  // US Equities
  "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
  "BRK-B", "JPM", "V", "MA", "NFLX", "DIS", "PYPL",
  "AMD", "INTC", "QCOM", "AVGO", "CRM", "ORCL", "COIN",
  "MSTR", "RIOT", "MARA", "CLSK", "HUT",
  // ETF
  "SPY", "QQQ", "GLD", "SLV", "USO", "VTI", "IWM", "TLT",
  // Forex (Yahoo Finance format)
  "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",
  "USDCHF=X", "NZDUSD=X", "EURGBP=X", "EURJPY=X", "GBPJPY=X",
  "USDMXN=X", "USDBRL=X", "USDCNY=X", "USDINR=X", "USDZAR=X",
  // Commodities (Yahoo Finance futures format)
  "GC=F", "SI=F", "CL=F", "NG=F", "BZ=F", "ZW=F", "ZC=F", "ZS=F",
  // Indices
  "^GSPC", "^IXIC", "^DJI", "^VIX", "^FTSE", "^N225", "^HSI", "^STOXX50E",
];

// ─── Statistical helpers ───────────────────────────────────────────────────

function hurstRS(returns: number[]): number {
  const n = returns.length;
  if (n < 20) return 0.5;
  const mean = returns.reduce((a, b) => a + b, 0) / n;
  const deviations = returns.map((r) => r - mean);
  let maxCumDev = -Infinity, minCumDev = Infinity;
  let cumSum = 0;
  for (const d of deviations) {
    cumSum += d;
    if (cumSum > maxCumDev) maxCumDev = cumSum;
    if (cumSum < minCumDev) minCumDev = cumSum;
  }
  const R = maxCumDev - minCumDev;
  const S = Math.sqrt(
    returns.reduce((a, b) => a + b * b, 0) / n - mean * mean
  );
  return S > 0 ? Math.log(R / S) / Math.log(n) : 0.5;
}

function jarqueBera(returns: number[]): { stat: number; isNormal: boolean } {
  const n = returns.length;
  if (n < 4) return { stat: 0, isNormal: true };
  const mean = returns.reduce((a, b) => a + b, 0) / n;
  const variance = returns.reduce((a, b) => a + (b - mean) ** 2, 0) / n;
  if (variance === 0) return { stat: 0, isNormal: true };
  const skew =
    returns.reduce((a, b) => a + (b - mean) ** 3, 0) /
    n /
    Math.pow(variance, 1.5);
  const kurt =
    returns.reduce((a, b) => a + (b - mean) ** 4, 0) / n / variance ** 2;
  const jb = (n / 6) * (skew ** 2 + (kurt - 3) ** 2 / 4);
  return { stat: jb, isNormal: jb < 5.99 };
}

// ─── Component ────────────────────────────────────────────────────────────

export function AssetsScreen() {
  const [selectedTicker, setSelectedTicker] = useState<string>(
    fixtures.assets[0].ticker
  );
  const [showFetch, setShowFetch] = useState(false);
  const [fetchTicker, setFetchTicker] = useState<string>("");
  const [searchVal, setSearchVal] = useState("");
  const [dropOpen, setDropOpen] = useState(false);
  const [fetchPeriod, setFetchPeriod] = useState<string>("2y");
  const [fetching, setFetching] = useState(false);
  const [fetchMsg, setFetchMsg] = useState<string | null>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [fetchInterval, setFetchInterval] = useState<string>("1d");
  const [viewInterval,  setViewInterval]  = useState<string>("1d");

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setDropOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const suggestions = searchVal.length > 0
    ? ALL_TICKERS.filter((t) =>
        t.toLowerCase().includes(searchVal.toLowerCase())
      ).slice(0, 10)
    : ALL_TICKERS.slice(0, 10);

  // API data (falls back to fixtures)
  const { data: apiAssets } = useAssets();
  // Only query bars/stats when the ticker is actually stored in the API
  const apiTickerExists =
    apiAssets?.some((a) => a.ticker === selectedTicker) ?? false;
  const { data: apiBars }  = useAssetBars(apiTickerExists ? selectedTicker : null, viewInterval);
  const { data: apiStats } = useAssetStats(apiTickerExists ? selectedTicker : null, viewInterval);

  // Build display list: prefer API data, fall back to fixtures
  const fixtureMap = new Map<string, Asset>(
    fixtures.assets.map((a) => [a.ticker, a])
  );

  const displayAssets: Asset[] = apiAssets
    ? apiAssets.map(
        (a) =>
          fixtureMap.get(a.ticker) ?? {
            name: a.ticker,
            ticker: a.ticker,
            kind: "spot",
            bars: [],
            basePrice: 0,
            stats: fixtures.assets[0].stats,
          }
      )
    : fixtures.assets;

  // Selected asset from fixtures
  const fixtureAsset = fixtureMap.get(selectedTicker) ?? fixtures.assets[0];

  // Bars: prefer API, fall back to fixture
  const bars =
    apiBars && apiBars.length > 0 ? apiBars : fixtureAsset.bars;

  // Stats: prefer API, fall back to fixture
  const stats = fixtureAsset.stats;
  const cagr    = apiStats?.cagr    != null ? apiStats.cagr    / 100 : stats.cagr;
  const annVol  = apiStats?.ann_vol != null ? apiStats.ann_vol / 100 : stats.annVol;
  const sharpe  = apiStats?.sharpe  ?? stats.sharpe;
  const maxDD   = apiStats?.max_dd  != null ? apiStats.max_dd  / 100 : stats.maxDD;
  const skew    = apiStats?.skew    ?? stats.skew;
  const kurt    = apiStats?.kurt    ?? stats.kurt;
  const sortino = apiStats?.sortino ?? stats.sortino;
  const var95   = apiStats?.var95   ?? stats.var95;
  const cvar95  = apiStats?.cvar95  ?? stats.cvar95;
  const bestDay  = apiStats?.best_day  ?? stats.bestDay;
  const worstDay = apiStats?.worst_day ?? stats.worstDay;

  // ─── Analysis computations ──────────────────────────────────────────────

  const analysisData = useMemo(() => {
    const recentBars = bars.slice(-365);
    if (recentBars.length < 2) {
      return { logReturns: [], hurst: 0.5, jb: { stat: 0, isNormal: true } };
    }
    const logReturns: number[] = [];
    for (let i = 1; i < recentBars.length; i++) {
      const prev = recentBars[i - 1].c;
      const curr = recentBars[i].c;
      if (prev > 0 && curr > 0) {
        logReturns.push(Math.log(curr / prev));
      }
    }
    const hurst = hurstRS(logReturns);
    const jb    = jarqueBera(logReturns);
    return { logReturns, hurst, jb };
  }, [bars]);

  const { logReturns, hurst, jb } = analysisData;

  const hurstLabel =
    hurst < 0.45
      ? { text: "MEAN REVERTING", color: "var(--cyan)" }
      : hurst > 0.55
      ? { text: "TRENDING", color: "var(--green)" }
      : { text: "RANDOM WALK", color: "var(--amber)" };

  // ─── Fetch handler ──────────────────────────────────────────────────────

  const handleFetch = async () => {
    if (!fetchTicker) return;
    setFetching(true);
    setFetchMsg(null);
    try {
      const res = await fetch("/api/assets/fetch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: fetchTicker,
          source: "yfinance",
          period: fetchPeriod,
          interval: fetchInterval,
        }),
      });
      if (res.ok) {
        setFetchMsg(`✓ ${fetchTicker} (${fetchPeriod}, ${fetchInterval}) scaricato`);
        setShowFetch(false);
        setFetchTicker("");
        setSearchVal("");
      } else {
        const err = await res.json().catch(() => ({}));
        setFetchMsg(`Errore: ${err.detail ?? res.status}`);
      }
    } catch {
      setFetchMsg("API non raggiungibile");
    } finally {
      setFetching(false);
    }
  };

  const selectTicker = (t: string) => {
    setFetchTicker(t);
    setSearchVal(t);
    setDropOpen(false);
  };

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {/* Top row: asset list + price chart + stats */}
      <div className={styles.grid}>
        {/* Left: asset list — span 4 */}
        <div className={styles.panel} style={{ gridColumn: "span 4" }}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>ASSETS</span>
            <span className={styles.panelSub}>{displayAssets.length} tracked</span>
          </div>
          <div className={styles.panelBody}>
            <div className={styles.assetList}>
              {displayAssets.map((asset) => {
                const fx = fixtureMap.get(asset.ticker) ?? asset;
                const s = fx.stats;
                const isSelected = asset.ticker === selectedTicker;
                const kind = getKind(asset.ticker);
                return (
                  <div
                    key={asset.ticker}
                    className={`${styles.assetRow} ${isSelected ? styles.assetRowActive : ""}`}
                    onClick={() => setSelectedTicker(asset.ticker)}
                  >
                    <div className={styles.assetRowTop}>
                      <span
                        className={styles.tickerChip}
                        style={{
                          borderColor:
                            KIND_COLORS[kind] ?? "var(--border-l)",
                          color: KIND_COLORS[kind] ?? "var(--text)",
                        }}
                      >
                        {asset.ticker}
                      </span>
                      <span className={styles.kindBadge}>{kind}</span>
                    </div>
                    <div className={styles.assetRowStats}>
                      <span className={styles.statItem}>
                        CAGR{" "}
                        <span
                          className={styles.statVal}
                          style={{ color: "var(--green)" }}
                        >
                          {(s.cagr * 100).toFixed(1)}%
                        </span>
                      </span>
                      <span className={styles.statItem}>
                        SHP{" "}
                        <span
                          className={styles.statVal}
                          style={{ color: "var(--amber)" }}
                        >
                          {s.sharpe.toFixed(2)}
                        </span>
                      </span>
                      <span className={styles.statItem}>
                        VOL{" "}
                        <span
                          className={styles.statVal}
                          style={{ color: "var(--coral)" }}
                        >
                          {(s.annVol * 100).toFixed(0)}%
                        </span>
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Fetch form */}
            <div className={styles.fetchSection}>
              {!showFetch ? (
                <button
                  className={styles.btnFetch}
                  onClick={() => {
                    setShowFetch(true);
                    setTimeout(() => inputRef.current?.focus(), 50);
                  }}
                >
                  + FETCH
                </button>
              ) : (
                <div className={styles.fetchForm}>
                  <div className={styles.label}>CERCA TICKER</div>

                  {/* Autocomplete */}
                  <div className={styles.searchWrap} ref={searchRef}>
                    <input
                      ref={inputRef}
                      className={styles.searchInput}
                      placeholder="es. BTC, ETH, AAPL…"
                      value={searchVal}
                      autoComplete="off"
                      spellCheck={false}
                      onChange={(e) => {
                        const v = e.target.value.toUpperCase();
                        setSearchVal(v);
                        setFetchTicker("");
                        setDropOpen(true);
                      }}
                      onFocus={() => setDropOpen(true)}
                      onKeyDown={(e) => {
                        if (e.key === "Escape") setDropOpen(false);
                        if (e.key === "Enter" && suggestions.length > 0) {
                          selectTicker(suggestions[0]);
                        }
                      }}
                    />
                    {dropOpen && suggestions.length > 0 && (
                      <div className={styles.dropdown}>
                        {suggestions.map((t) => (
                          <button
                            key={t}
                            className={`${styles.dropItem} ${fetchTicker === t ? styles.dropItemActive : ""}`}
                            onMouseDown={(e) => {
                              e.preventDefault();
                              selectTicker(t);
                            }}
                          >
                            {t}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Period pills */}
                  <div className={styles.label}>PERIODO</div>
                  <div className={styles.periodPills}>
                    {PERIODS.map((p) => (
                      <button
                        key={p}
                        className={`${styles.pill} ${fetchPeriod === p ? styles.pillActive : ""}`}
                        onClick={() => setFetchPeriod(p)}
                      >
                        {p}
                      </button>
                    ))}
                  </div>

                  {/* Timeframe pills */}
                  <div className={styles.label}>TIMEFRAME</div>
                  <div className={styles.periodPills}>
                    {TIMEFRAMES.map((tf) => (
                      <button
                        key={tf}
                        className={`${styles.pill} ${fetchInterval === tf ? styles.pillActive : ""}`}
                        onClick={() => setFetchInterval(tf)}
                      >
                        {tf}
                      </button>
                    ))}
                  </div>

                  <div className={styles.fetchActions}>
                    <button
                      className={styles.btnFetch}
                      onClick={handleFetch}
                      disabled={fetching || !fetchTicker}
                    >
                      {fetching
                        ? "SCARICANDO…"
                        : `FETCH${fetchTicker ? ` ${fetchTicker}` : ""}`}
                    </button>
                    <button
                      className={styles.btnCancel}
                      onClick={() => {
                        setShowFetch(false);
                        setFetchMsg(null);
                        setFetchTicker("");
                        setSearchVal("");
                      }}
                    >
                      CANCEL
                    </button>
                  </div>
                  {fetchMsg && (
                    <div className={styles.fetchMsg}>{fetchMsg}</div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Middle: candlestick chart — span 5 */}
        <div className={styles.panel} style={{ gridColumn: "span 5" }}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>
              {selectedTicker} · PRICE · {viewInterval.toUpperCase()}
            </span>
            <span className={styles.panelSub}>last {Math.min(bars.length, 120)} bars</span>
            <div style={{ display: "flex", gap: 3, marginLeft: "auto" }}>
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  className={`${styles.pill} ${viewInterval === tf ? styles.pillActive : ""}`}
                  style={{ padding: "1px 5px", fontSize: 9 }}
                  onClick={() => setViewInterval(tf)}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
          <div className={styles.panelBody}>
            <div className={styles.chartWrap}>
              {bars.length > 0 ? (
                <CandlestickChart
                  bars={bars.slice(-365)}
                  height={200}
                  showEMA20={true}
                  showEMA50={false}
                />
              ) : (
                <div
                  style={{
                    height: 200,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "var(--faint)",
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                  }}
                >
                  LOADING…
                </div>
              )}
            </div>
            <div className={styles.chartFooter}>
              <span className={styles.chartLabel}>
                OPEN{" "}
                <span className={styles.chartVal}>
                  {bars[bars.length - 365]?.o.toLocaleString() ?? "—"}
                </span>
              </span>
              <span className={styles.chartLabel}>
                CLOSE{" "}
                <span className={styles.chartVal}>
                  {bars[bars.length - 1]?.c.toLocaleString() ?? "—"}
                </span>
              </span>
              <span className={styles.chartLabel}>
                HIGH{" "}
                <span
                  className={styles.chartVal}
                  style={{ color: "var(--green)" }}
                >
                  {bars.length > 0
                    ? Math.max(...bars.slice(-365).map((b) => b.h)).toLocaleString()
                    : "—"}
                </span>
              </span>
              <span className={styles.chartLabel}>
                LOW{" "}
                <span
                  className={styles.chartVal}
                  style={{ color: "var(--coral)" }}
                >
                  {bars.length > 0
                    ? Math.min(...bars.slice(-365).map((b) => b.l)).toLocaleString()
                    : "—"}
                </span>
              </span>
            </div>
          </div>
        </div>

        {/* Right: stats — span 3 */}
        <div className={styles.panel} style={{ gridColumn: "span 3" }}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>STATS · {selectedTicker}</span>
          </div>
          <div className={styles.panelBody}>
            <div className={styles.statsGrid}>
              <StatRow label="CAGR"      value={`${(cagr * 100).toFixed(2)}%`}         color="var(--green)" />
              <StatRow label="ANN VOL"   value={`${(annVol * 100).toFixed(2)}%`}        color="var(--coral)" />
              <StatRow label="SHARPE"    value={sharpe.toFixed(3)}                       color="var(--green)" />
              <StatRow label="SORTINO"   value={sortino.toFixed(3)}                      color="var(--green)" />
              <StatRow label="MAX DD"    value={`${(maxDD * 100).toFixed(2)}%`}         color="var(--coral)" />
              <StatRow label="SKEW"      value={skew.toFixed(4)}                         color={skew >= 0 ? "var(--green)" : "var(--coral)"} />
              <StatRow label="KURT"      value={kurt.toFixed(4)}                         color="var(--coral)" />
              <StatRow label="VAR 95"    value={`${(var95 * 100).toFixed(3)}%`}         color="var(--coral)" />
              <StatRow label="CVAR 95"   value={`${(cvar95 * 100).toFixed(3)}%`}        color="var(--coral)" />
              <StatRow label="BEST DAY"  value={`${(bestDay * 100).toFixed(2)}%`}       color="var(--green)" />
              <StatRow label="WORST DAY" value={`${(worstDay * 100).toFixed(2)}%`}      color="var(--coral)" />
            </div>
          </div>
        </div>
      </div>

      {/* Bottom row: analysis panels */}
      <div className={styles.analysisRow}>
        {/* Panel A — Return Distribution (span 7) */}
        <div className={styles.analysisPanel} style={{ gridColumn: "span 7" }}>
          <div className={styles.analysisPanelHeader}>
            <span className={styles.analysisPanelTitle}>
              DAILY RETURN DIST.
            </span>
            <span className={styles.panelSub}>
              {logReturns.length} observations
            </span>
          </div>
          <div className={styles.analysisPanelBody}>
            <Histogram
              data={logReturns}
              bins={30}
              height={120}
              color="#ffb53b"
              fmt={(v) => `${(v * 100).toFixed(2)}%`}
            />
          </div>
        </div>

        {/* Panel B — Advanced Stats (span 5) */}
        <div className={styles.analysisPanel} style={{ gridColumn: "span 5" }}>
          <div className={styles.analysisPanelHeader}>
            <span className={styles.analysisPanelTitle}>ADVANCED STATS</span>
          </div>
          <div className={styles.analysisPanelBody}>
            <div className={styles.advStatsGrid}>
              {/* Hurst Exponent */}
              <div className={styles.advStatRow}>
                <span className={styles.advStatLabel}>HURST</span>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span className={styles.advStatVal}>
                    H = {hurst.toFixed(2)}
                  </span>
                  <span
                    className={styles.advStatBadge}
                    style={{ color: hurstLabel.color }}
                  >
                    {hurstLabel.text}
                  </span>
                </div>
              </div>

              {/* Skewness */}
              <div className={styles.advStatRow}>
                <span className={styles.advStatLabel}>SKEWNESS</span>
                <span
                  className={styles.advStatVal}
                  style={{ color: skew >= 0 ? "var(--green)" : "var(--coral)" }}
                >
                  {skew.toFixed(4)}
                </span>
              </div>

              {/* Kurtosis */}
              <div className={styles.advStatRow}>
                <span className={styles.advStatLabel}>KURTOSIS</span>
                <span
                  className={styles.advStatVal}
                  style={{ color: "var(--coral)" }}
                >
                  {kurt.toFixed(4)}
                </span>
              </div>

              {/* Jarque-Bera */}
              <div className={styles.advStatRow}>
                <span className={styles.advStatLabel}>JARQUE-BERA</span>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span className={styles.advStatVal}>
                    JB = {jb.stat.toFixed(1)}
                  </span>
                  <span
                    className={styles.advStatBadge}
                    style={{
                      color: jb.isNormal ? "var(--green)" : "var(--coral)",
                    }}
                  >
                    {jb.isNormal ? "NORMAL" : "NON-NORMAL"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Second analysis row: QQ Plot + ACF + Standardized Residuals */}
      {logReturns.length >= 10 && (
        <div className={styles.analysisRow}>

          {/* QQ Plot — span 4 */}
          <div className={styles.analysisPanel} style={{ gridColumn: "span 4" }}>
            <div className={styles.analysisPanelHeader}>
              <span className={styles.analysisPanelTitle}>Q-Q PLOT</span>
              <span className={styles.panelSub}>vs normal</span>
            </div>
            <div className={styles.analysisPanelBody}>
              <QQPlot data={logReturns} height={160} color="#5cc1ff" />
            </div>
          </div>

          {/* ACF Plot — span 4 */}
          <div className={styles.analysisPanel} style={{ gridColumn: "span 4" }}>
            <div className={styles.analysisPanelHeader}>
              <span className={styles.analysisPanelTitle}>AUTOCORRELATION (ACF)</span>
              <span className={styles.panelSub}>lags 1–30</span>
            </div>
            <div className={styles.analysisPanelBody}>
              <ACFPlot data={logReturns} maxLag={30} height={160} color="#ffb53b" />
            </div>
          </div>

          {/* Standardized Residuals — span 4 */}
          <div className={styles.analysisPanel} style={{ gridColumn: "span 4" }}>
            <div className={styles.analysisPanelHeader}>
              <span className={styles.analysisPanelTitle}>STD RESIDUALS</span>
              <span className={styles.panelSub}>±2σ reference</span>
            </div>
            <div className={styles.analysisPanelBody}>
              <StdResidualsChart returns={logReturns} height={160} />
            </div>
          </div>

        </div>
      )}
    </div>
  );
}

function StatRow({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className={styles.statRow}>
      <span className={styles.statLabel}>{label}</span>
      <span
        className={styles.statValue}
        style={{ color: color ?? "var(--text)" }}
      >
        {value}
      </span>
    </div>
  );
}

function StdResidualsChart({ returns, height = 160 }: { returns: number[]; height: number }) {
  const n = returns.length;
  if (n < 4) return null;
  const mean = returns.reduce((a, b) => a + b, 0) / n;
  const std  = Math.sqrt(returns.reduce((a, b) => a + (b - mean) ** 2, 0) / n) || 1;
  const z    = returns.map((r) => (r - mean) / std);
  const maxAbs = Math.max(3, ...z.map(Math.abs));

  const padL = 32, padR = 8, padT = 8, padB = 20;
  const W = 300, H = height;
  const w = W - padL - padR, h = H - padT - padB;

  const cx = (i: number) => padL + (i / (n - 1)) * w;
  const cy = (v: number) => padT + h / 2 - (v / maxAbs) * (h / 2);

  const outliers  = z.filter((v) => Math.abs(v) > 2).length;
  const pctOut    = ((outliers / n) * 100).toFixed(1);

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", height, display: "block" }}
      >
        {/* grid lines */}
        {[-2, 0, 2].map((level) => (
          <line
            key={level}
            x1={padL} y1={cy(level)} x2={W - padR} y2={cy(level)}
            stroke={level === 0 ? "#ffb53b" : "#ff7a55"}
            strokeWidth={level === 0 ? 0.8 : 0.5}
            strokeDasharray={level === 0 ? undefined : "3 3"}
          />
        ))}
        {/* y-axis labels */}
        {[-2, 0, 2].map((level) => (
          <text
            key={level}
            x={padL - 4} y={cy(level) + 3}
            textAnchor="end"
            fontFamily="var(--font-mono)" fontSize={8}
            fill="var(--faint)"
          >
            {level}σ
          </text>
        ))}
        {/* dots */}
        {z.map((v, i) => (
          <circle
            key={i}
            cx={cx(i)} cy={cy(v)} r={1.5}
            fill={Math.abs(v) > 2 ? "#ff7a55" : "#5cc1ff"}
            opacity={0.65}
          />
        ))}
      </svg>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: 9,
        color: "var(--faint)", paddingTop: 2,
      }}>
        outliers &gt;2σ: <span style={{ color: outliers / n > 0.05 ? "var(--coral)" : "var(--green)" }}>
          {outliers} ({pctOut}%)
        </span>
      </div>
    </div>
  );
}
