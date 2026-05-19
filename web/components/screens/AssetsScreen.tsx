"use client";
import { useState, useRef, useEffect } from "react";
import { fixtures } from "@/lib/fixtures";
import { useAssets, useAssetBars, useAssetStats } from "@/hooks/useAssets";
import { Sparkline } from "@/components/charts/Sparkline";
import type { Asset } from "@/lib/fixtures";
import styles from "./AssetsScreen.module.css";

const KIND_COLORS: Record<string, string> = {
  spot: "var(--cyan)",
  perp: "var(--amber)",
  index: "var(--green)",
};

const PERIODS = ["1y", "2y", "5y"] as const;

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
];

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
    ? ALL_TICKERS.filter(t =>
        t.toLowerCase().includes(searchVal.toLowerCase())
      ).slice(0, 10)
    : ALL_TICKERS.slice(0, 10);

  // API data (falls back to fixtures)
  const { data: apiAssets } = useAssets();
  // Only query bars/stats when the ticker is actually stored in the API
  const apiTickerExists = apiAssets?.some((a) => a.ticker === selectedTicker) ?? false;
  const { data: apiBars } = useAssetBars(apiTickerExists ? selectedTicker : null);
  const { data: apiStats } = useAssetStats(apiTickerExists ? selectedTicker : null);

  // Build display list: prefer API data, fall back to fixtures
  const fixtureMap = new Map<string, Asset>(
    fixtures.assets.map((a) => [a.ticker, a])
  );

  const displayAssets: Asset[] = apiAssets
    ? apiAssets.map((a) => fixtureMap.get(a.ticker) ?? {
        name: a.ticker,
        ticker: a.ticker,
        kind: "spot",
        bars: [],
        basePrice: 0,
        stats: fixtures.assets[0].stats,
      })
    : fixtures.assets;

  // Selected asset from fixtures
  const fixtureAsset =
    fixtureMap.get(selectedTicker) ?? fixtures.assets[0];

  // Bars: prefer API, fall back to fixture
  const bars =
    apiBars && apiBars.length > 0 ? apiBars : fixtureAsset.bars;
  const closePrices = bars.slice(-365).map((b) => b.c);

  // Stats: prefer API, fall back to fixture
  const stats = fixtureAsset.stats;
  const cagr    = apiStats?.cagr != null ? apiStats.cagr / 100 : stats.cagr;
  const annVol  = apiStats?.ann_vol != null ? apiStats.ann_vol / 100 : stats.annVol;
  const sharpe  = apiStats?.sharpe ?? stats.sharpe;
  const maxDD   = apiStats?.max_dd != null ? apiStats.max_dd / 100 : stats.maxDD;
  const skew    = apiStats?.skew ?? stats.skew;
  const kurt    = apiStats?.kurt ?? stats.kurt;
  const sortino = apiStats?.sortino ?? stats.sortino;
  const var95   = apiStats?.var95 ?? stats.var95;
  const cvar95  = apiStats?.cvar95 ?? stats.cvar95;
  const bestDay = apiStats?.best_day ?? stats.bestDay;
  const worstDay = apiStats?.worst_day ?? stats.worstDay;

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
        }),
      });
      if (res.ok) {
        setFetchMsg(`✓ ${fetchTicker} scaricato (${fetchPeriod})`);
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

  return (
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
              return (
                <div
                  key={asset.ticker}
                  className={`${styles.assetRow} ${isSelected ? styles.assetRowActive : ""}`}
                  onClick={() => setSelectedTicker(asset.ticker)}
                >
                  <div className={styles.assetRowTop}>
                    <span
                      className={styles.tickerChip}
                      style={{ borderColor: KIND_COLORS[asset.kind] ?? "var(--border-l)", color: KIND_COLORS[asset.kind] ?? "var(--text)" }}
                    >
                      {asset.ticker}
                    </span>
                    <span className={styles.kindBadge}>{asset.kind}</span>
                  </div>
                  <div className={styles.assetRowStats}>
                    <span className={styles.statItem}>
                      CAGR <span className={styles.statVal} style={{ color: "var(--green)" }}>{(s.cagr * 100).toFixed(1)}%</span>
                    </span>
                    <span className={styles.statItem}>
                      SHP <span className={styles.statVal} style={{ color: "var(--amber)" }}>{s.sharpe.toFixed(2)}</span>
                    </span>
                    <span className={styles.statItem}>
                      VOL <span className={styles.statVal} style={{ color: "var(--coral)" }}>{(s.annVol * 100).toFixed(0)}%</span>
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
                            e.preventDefault(); // avoid blur before click
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

                <div className={styles.fetchActions}>
                  <button
                    className={styles.btnFetch}
                    onClick={handleFetch}
                    disabled={fetching || !fetchTicker}
                  >
                    {fetching ? "SCARICANDO…" : `FETCH${fetchTicker ? ` ${fetchTicker}` : ""}`}
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

      {/* Middle: price chart — span 5 */}
      <div className={styles.panel} style={{ gridColumn: "span 5" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>
            {selectedTicker} · PRICE
          </span>
          <span className={styles.panelSub}>last 365 bars</span>
        </div>
        <div className={styles.panelBody}>
          <div className={styles.chartWrap}>
            <Sparkline
              data={closePrices}
              width={480}
              height={240}
              color="#ffb53b"
            />
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
              <span className={styles.chartVal} style={{ color: "var(--green)" }}>
                {closePrices.length > 0 ? Math.max(...closePrices).toLocaleString() : "—"}
              </span>
            </span>
            <span className={styles.chartLabel}>
              LOW{" "}
              <span className={styles.chartVal} style={{ color: "var(--coral)" }}>
                {closePrices.length > 0 ? Math.min(...closePrices).toLocaleString() : "—"}
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
            <StatRow label="CAGR"      value={`${(cagr * 100).toFixed(2)}%`}        color="var(--green)" />
            <StatRow label="ANN VOL"   value={`${(annVol * 100).toFixed(2)}%`}       color="var(--coral)" />
            <StatRow label="SHARPE"    value={sharpe.toFixed(3)}                      color="var(--green)" />
            <StatRow label="SORTINO"   value={sortino.toFixed(3)}                     color="var(--green)" />
            <StatRow label="MAX DD"    value={`${(maxDD * 100).toFixed(2)}%`}        color="var(--coral)" />
            <StatRow label="SKEW"      value={skew.toFixed(4)}                        color={skew >= 0 ? "var(--green)" : "var(--coral)"} />
            <StatRow label="KURT"      value={kurt.toFixed(4)}                        color="var(--coral)" />
            <StatRow label="VAR 95"    value={`${(var95 * 100).toFixed(3)}%`}        color="var(--coral)" />
            <StatRow label="CVAR 95"   value={`${(cvar95 * 100).toFixed(3)}%`}       color="var(--coral)" />
            <StatRow label="BEST DAY"  value={`${(bestDay * 100).toFixed(2)}%`}      color="var(--green)" />
            <StatRow label="WORST DAY" value={`${(worstDay * 100).toFixed(2)}%`}     color="var(--coral)" />
          </div>
        </div>
      </div>
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
      <span className={styles.statValue} style={{ color: color ?? "var(--text)" }}>
        {value}
      </span>
    </div>
  );
}
