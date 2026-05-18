"use client";
import { useState } from "react";
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

const FETCHABLE_TICKERS = [
  "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
  "ADA-USD", "AVAX-USD", "DOT-USD", "MATIC-USD", "LINK-USD",
  "ARB-USD", "OP-USD", "ATOM-USD", "NEAR-USD", "APT-USD",
];

export function AssetsScreen() {
  const [selectedTicker, setSelectedTicker] = useState<string>(
    fixtures.assets[0].ticker
  );
  const [showFetch, setShowFetch] = useState(false);
  const [fetchTicker, setFetchTicker] = useState(FETCHABLE_TICKERS[0]);
  const [fetchPeriod, setFetchPeriod] = useState<string>("2y");
  const [fetching, setFetching] = useState(false);
  const [fetchMsg, setFetchMsg] = useState<string | null>(null);

  // API data (falls back to fixtures)
  const { data: apiAssets } = useAssets();
  const { data: apiBars } = useAssetBars(selectedTicker);
  const { data: apiStats } = useAssetStats(selectedTicker);

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
  const cagr = apiStats?.cagr ?? stats.cagr;
  const annVol = apiStats?.ann_vol ?? stats.annVol;
  const sharpe = apiStats?.sharpe ?? stats.sharpe;
  const maxDD = apiStats?.max_dd ?? stats.maxDD;
  const skew = apiStats?.skew ?? stats.skew;
  const kurt = apiStats?.kurt ?? stats.kurt;

  const handleFetch = async () => {
    if (!fetchTicker) return;
    setFetching(true);
    setFetchMsg(null);
    try {
      const res = await fetch("/api/assets/fetch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: fetchTicker.trim().toUpperCase(),
          source: "yfinance",
          period: fetchPeriod,
        }),
      });
      if (res.ok) {
        setFetchMsg(`✓ ${fetchTicker} fetched (${fetchPeriod})`);
        setShowFetch(false);
      } else {
        setFetchMsg("Fetch failed — check ticker");
      }
    } catch {
      setFetchMsg("API unavailable");
    } finally {
      setFetching(false);
    }
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
                onClick={() => setShowFetch(true)}
              >
                + FETCH
              </button>
            ) : (
              <div className={styles.fetchForm}>
                <div className={styles.label}>TICKER</div>
                <div className={styles.tickerPills}>
                  {FETCHABLE_TICKERS.map((t) => (
                    <button
                      key={t}
                      className={`${styles.pill} ${fetchTicker === t ? styles.pillActive : ""}`}
                      onClick={() => setFetchTicker(t)}
                    >
                      {t.replace("-USD", "")}
                    </button>
                  ))}
                </div>
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
                    disabled={fetching}
                  >
                    {fetching ? "FETCHING…" : "FETCH"}
                  </button>
                  <button
                    className={styles.btnCancel}
                    onClick={() => { setShowFetch(false); setFetchMsg(null); }}
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
              color="var(--amber)"
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
                {Math.max(...closePrices).toLocaleString()}
              </span>
            </span>
            <span className={styles.chartLabel}>
              LOW{" "}
              <span className={styles.chartVal} style={{ color: "var(--coral)" }}>
                {Math.min(...closePrices).toLocaleString()}
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
            <StatRow label="SORTINO"   value={stats.sortino.toFixed(3)}              color="var(--green)" />
            <StatRow label="MAX DD"    value={`${(maxDD * 100).toFixed(2)}%`}        color="var(--coral)" />
            <StatRow label="SKEW"      value={skew.toFixed(4)}                        color={skew >= 0 ? "var(--green)" : "var(--coral)"} />
            <StatRow label="KURT"      value={kurt.toFixed(4)}                        color="var(--coral)" />
            <StatRow label="VAR 95"    value={`${(stats.var95 * 100).toFixed(3)}%`}  color="var(--coral)" />
            <StatRow label="CVAR 95"   value={`${(stats.cvar95 * 100).toFixed(3)}%`} color="var(--coral)" />
            <StatRow label="BEST DAY"  value={`${(stats.bestDay * 100).toFixed(2)}%`} color="var(--green)" />
            <StatRow label="WORST DAY" value={`${(stats.worstDay * 100).toFixed(2)}%`} color="var(--coral)" />
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
