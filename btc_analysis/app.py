"""
app.py — BTC Strategy Dashboard (Streamlit)
============================================
Avvio:
  streamlit run btc_analysis/app.py
"""

import os
import warnings
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st

warnings.filterwarnings("ignore")

OUTPUT = os.path.join(os.path.dirname(__file__), "output")

st.set_page_config(
    page_title="BTC Strategy Dashboard",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Palette ───────────────────────────────────────────────────────────────────
C_UP   = "#26a69a"
C_DOWN = "#ef5350"
C_LINE = "#2196f3"
C_ACC  = "#ff9800"
BG     = "#0e1117"


# ══════════════════════════════════════════════════════════════════════════════
#  Data loaders (cached)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data
def load_daily():
    df = pd.read_csv(f"{OUTPUT}/btc_daily.csv", index_col=0, parse_dates=True)
    df.index.name = "Date"
    return df

@st.cache_data
def load_hourly():
    df = pd.read_csv(f"{OUTPUT}/btc_hourly.csv", index_col=0, parse_dates=True)
    df.index.name = "Date"
    return df

@st.cache_data
def load_trades():
    return pd.read_csv(f"{OUTPUT}/trades.csv", parse_dates=["entry_time","exit_time"])

@st.cache_data
def load_strategy_comparison():
    return pd.read_csv(f"{OUTPUT}/enhanced_strategy_comparison.csv")

@st.cache_data
def load_wfo():
    return pd.read_csv(f"{OUTPUT}/walk_forward_results.csv")

@st.cache_data
def load_mc_bootstrap():
    return pd.read_csv(f"{OUTPUT}/mc_bootstrap_results.csv")

@st.cache_data
def load_mc_stress():
    return pd.read_csv(f"{OUTPUT}/mc_stress_results.csv")

@st.cache_data
def load_multi_asset():
    return pd.read_csv(f"{OUTPUT}/multi_asset_results.csv")

@st.cache_data
def load_optimization():
    return pd.read_csv(f"{OUTPUT}/optimization_results.csv")


# ── Equity from trades ────────────────────────────────────────────────────────

def equity_curve(trades: pd.DataFrame, capital: float = 10_000) -> pd.Series:
    eq = capital + trades["pnl"].cumsum()
    eq.index = trades["exit_time"]
    return eq

def drawdown_series(eq: pd.Series) -> pd.Series:
    peak = eq.cummax()
    return (eq - peak) / peak * 100


# ══════════════════════════════════════════════════════════════════════════════
#  Header
# ══════════════════════════════════════════════════════════════════════════════

st.title("₿ BTC/USD — Strategy Dashboard")
st.caption("Analisi serie storica · Strategia V5 · Walk-Forward · Monte Carlo · Multi-Asset")

# ── Top KPIs (versione migliore per Sharpe) ────────────────────────────────
try:
    cmp  = load_strategy_comparison()
    best = cmp.loc[cmp["sharpe_ratio"].idxmax()]

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("CAGR",         f"{best['cagr_pct']:.1f}%")
    col2.metric("Sharpe",       f"{best['sharpe_ratio']:.2f}")
    col3.metric("Max Drawdown", f"{best['max_drawdown_pct']:.1f}%")
    col4.metric("Win Rate",     f"{best['win_rate_pct']:.1f}%")
    col5.metric("Trade totali", f"{int(best['n_trades'])}  [{best['version']}]")
except Exception:
    pass

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
#  Tabs
# ══════════════════════════════════════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Prezzi & Rendimenti",
    "📈 Strategia V5",
    "🔄 Walk-Forward",
    "🎲 Monte Carlo",
    "🌐 Multi-Asset",
])


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — Prezzi & Rendimenti
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    daily = load_daily()

    # ── Filtro data ───────────────────────────────────────────────────────────
    col_a, col_b = st.columns([3, 1])
    with col_b:
        years = sorted(daily.index.year.unique())
        yr_from, yr_to = st.select_slider(
            "Periodo", options=years, value=(years[0], years[-1])
        )
    d = daily[(daily.index.year >= yr_from) & (daily.index.year <= yr_to)]

    # ── Candlestick + Volume ──────────────────────────────────────────────────
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.75, 0.25], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(
        x=d.index, open=d["Open"], high=d["High"],
        low=d["Low"],  close=d["Close"],
        increasing_line_color=C_UP, decreasing_line_color=C_DOWN,
        name="BTC/USD",
    ), row=1, col=1)
    colors = [C_UP if c >= o else C_DOWN
              for c, o in zip(d["Close"], d["Open"])]
    fig.add_trace(go.Bar(x=d.index, y=d["Volume"],
                         marker_color=colors, name="Volume",
                         showlegend=False), row=2, col=1)
    fig.update_layout(height=500, xaxis_rangeslider_visible=False,
                      margin=dict(l=0, r=0, t=30, b=0),
                      template="plotly_dark", title="BTC/USD — Candlestick giornaliero")
    fig.update_yaxes(title_text="Prezzo (USD)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)

    # ── Log-returns + Distribuzione ───────────────────────────────────────────
    log_ret = np.log(d["Close"] / d["Close"].shift(1)).dropna()

    col_l, col_r = st.columns(2)

    with col_l:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=log_ret.index, y=log_ret.values,
                                  mode="lines", line=dict(color=C_LINE, width=1),
                                  name="Log-return"))
        fig2.update_layout(height=300, template="plotly_dark",
                            title="Log-returns giornalieri",
                            margin=dict(l=0, r=0, t=40, b=0),
                            yaxis_title="Log-return")
        st.plotly_chart(fig2, use_container_width=True)

    with col_r:
        fig3 = go.Figure()
        fig3.add_trace(go.Histogram(x=log_ret.values, nbinsx=80,
                                    marker_color=C_LINE, opacity=0.8,
                                    name="Distribuzione"))
        # Gaussian overlay
        mu, sigma = log_ret.mean(), log_ret.std()
        x_norm = np.linspace(log_ret.min(), log_ret.max(), 200)
        y_norm = (np.exp(-0.5 * ((x_norm - mu) / sigma)**2)
                  / (sigma * np.sqrt(2 * np.pi))) * len(log_ret) * (log_ret.max() - log_ret.min()) / 80
        fig3.add_trace(go.Scatter(x=x_norm, y=y_norm, mode="lines",
                                  line=dict(color=C_ACC, width=2),
                                  name="Normale"))
        fig3.update_layout(height=300, template="plotly_dark",
                            title="Distribuzione log-returns",
                            margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig3, use_container_width=True)

    # ── Statistiche descrittive ───────────────────────────────────────────────
    from scipy import stats as scipy_stats
    kurt   = float(scipy_stats.kurtosis(log_ret, fisher=True))
    skew   = float(scipy_stats.skew(log_ret))
    jb_s, jb_p = scipy_stats.jarque_bera(log_ret)
    ann_vol = log_ret.std() * np.sqrt(252) * 100

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Volatilità annua",  f"{ann_vol:.1f}%")
    c2.metric("Curtosi (excess)",  f"{kurt:.2f}")
    c3.metric("Skewness",          f"{skew:.3f}")
    c4.metric("Jarque-Bera p-val", f"{jb_p:.4f}")

    # ── Rendimenti medi per ora del giorno ────────────────────────────────────
    st.subheader("Pattern intraday (dati orari)")
    try:
        hourly = load_hourly()
        hourly["log_ret"] = np.log(hourly["Close"] / hourly["Close"].shift(1))
        hourly["hour"] = hourly.index.hour
        by_hour = hourly.groupby("hour")["log_ret"].mean() * 1e4  # in basis points

        fig4 = go.Figure(go.Bar(
            x=by_hour.index, y=by_hour.values,
            marker_color=[C_UP if v >= 0 else C_DOWN for v in by_hour.values],
        ))
        fig4.update_layout(height=280, template="plotly_dark",
                            title="Rendimento medio per ora del giorno (UTC) — basis points",
                            xaxis_title="Ora (UTC)", yaxis_title="Rendimento medio (bp)",
                            margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig4, use_container_width=True)
    except Exception:
        st.info("Dati orari non disponibili.")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — Strategia V5
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    try:
        trades = load_trades()
        cmp    = load_strategy_comparison()
        optim  = load_optimization()

        # ── Equity curve + Drawdown ───────────────────────────────────────────
        eq = equity_curve(trades)
        dd = drawdown_series(eq)

        fig_eq = make_subplots(rows=2, cols=1, shared_xaxes=True,
                               row_heights=[0.7, 0.3], vertical_spacing=0.04)
        fig_eq.add_trace(go.Scatter(x=eq.index, y=eq.values, mode="lines",
                                    line=dict(color=C_UP, width=2),
                                    fill="tozeroy", fillcolor="rgba(38,166,154,0.1)",
                                    name="Equity"), row=1, col=1)
        fig_eq.add_hline(y=10_000, line_dash="dash",
                         line_color="gray", row=1, col=1)
        fig_eq.add_trace(go.Scatter(x=dd.index, y=dd.values, mode="lines",
                                    line=dict(color=C_DOWN, width=1.5),
                                    fill="tozeroy", fillcolor="rgba(239,83,80,0.2)",
                                    name="Drawdown %"), row=2, col=1)
        fig_eq.update_layout(height=480, template="plotly_dark",
                              title="Equity curve & Drawdown — Strategia V5",
                              margin=dict(l=0, r=0, t=40, b=0))
        fig_eq.update_yaxes(title_text="Capitale (USDT)", row=1, col=1)
        fig_eq.update_yaxes(title_text="Drawdown %", row=2, col=1)
        st.plotly_chart(fig_eq, use_container_width=True)

        # ── Trade scatter: P&L nel tempo ──────────────────────────────────────
        col_l, col_r = st.columns([2, 1])

        with col_l:
            fig_tr = go.Figure()
            wins  = trades[trades["pnl"] > 0]
            loss  = trades[trades["pnl"] <= 0]
            for sub, col, label in [(wins, C_UP, "Win"), (loss, C_DOWN, "Loss")]:
                fig_tr.add_trace(go.Scatter(
                    x=sub["exit_time"], y=sub["pnl"],
                    mode="markers",
                    marker=dict(color=col, size=6, opacity=0.7),
                    name=label,
                    hovertemplate="%{x|%Y-%m-%d %H:%M}<br>P&L: %{y:.2f} USDT",
                ))
            fig_tr.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_tr.update_layout(height=300, template="plotly_dark",
                                 title="P&L per trade",
                                 margin=dict(l=0, r=0, t=40, b=0),
                                 yaxis_title="P&L (USDT)")
            st.plotly_chart(fig_tr, use_container_width=True)

        with col_r:
            pnl_arr = trades["pnl"].values
            wins_n  = (pnl_arr > 0).sum()
            loss_n  = (pnl_arr <= 0).sum()
            fig_pie = go.Figure(go.Pie(
                labels=["Win", "Loss"],
                values=[wins_n, loss_n],
                marker_colors=[C_UP, C_DOWN],
                hole=0.5,
            ))
            fig_pie.update_layout(height=300, template="plotly_dark",
                                  title="Win / Loss ratio",
                                  margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig_pie, use_container_width=True)

        # ── Confronto versioni strategia ──────────────────────────────────────
        st.subheader("Confronto versioni strategia")
        disp = cmp[["version", "cagr_pct", "sharpe_ratio",
                     "max_drawdown_pct", "win_rate_pct",
                     "n_trades", "total_costs_usd"]].copy()
        disp.columns = ["Versione", "CAGR %", "Sharpe",
                        "Max DD %", "Win %", "Trade", "Costi USD"]
        disp = disp.set_index("Versione")
        st.dataframe(
            disp.style
                .background_gradient(subset=["CAGR %", "Sharpe"], cmap="RdYlGn")
                .background_gradient(subset=["Max DD %"], cmap="RdYlGn_r")
                .format({"CAGR %": "{:.1f}", "Sharpe": "{:.2f}",
                         "Max DD %": "{:.1f}", "Win %": "{:.1f}",
                         "Costi USD": "{:.0f}"}),
            use_container_width=True,
        )

        # ── Grid search heatmap ───────────────────────────────────────────────
        st.subheader("Grid search — Sharpe ratio (SL mult × TP mult)")
        pivot = optim.pivot_table(index="sl_mult", columns="tp_mult",
                                  values="sharpe", aggfunc="mean")
        fig_ht = px.imshow(
            pivot, color_continuous_scale="RdYlGn",
            labels=dict(x="TP mult", y="SL mult", color="Sharpe"),
            text_auto=".2f",
            aspect="auto",
        )
        fig_ht.update_layout(height=320, template="plotly_dark",
                              margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_ht, use_container_width=True)

    except Exception as e:
        st.error(f"Errore caricamento dati strategia: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 3 — Walk-Forward Optimization
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    try:
        wfo = load_wfo()

        # WFE = OOS_Sharpe / IS_Sharpe per fold
        wfo["wfe"] = wfo["oos_sharpe"] / wfo["is_sharpe"].replace(0, np.nan)

        # ── IS vs OOS Sharpe per fold ─────────────────────────────────────────
        fig_wf = go.Figure()
        fig_wf.add_trace(go.Bar(
            x=wfo["fold"].astype(str),
            y=wfo["is_sharpe"],
            name="IS Sharpe",
            marker_color=C_LINE,
        ))
        fig_wf.add_trace(go.Bar(
            x=wfo["fold"].astype(str),
            y=wfo["oos_sharpe"],
            name="OOS Sharpe",
            marker_color=C_ACC,
        ))
        fig_wf.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_wf.update_layout(
            barmode="group", height=380, template="plotly_dark",
            title="IS vs OOS Sharpe per fold",
            xaxis_title="Fold", yaxis_title="Sharpe Ratio",
            margin=dict(l=0, r=0, t=40, b=0),
        )
        st.plotly_chart(fig_wf, use_container_width=True)

        # ── IS vs OOS CAGR ────────────────────────────────────────────────────
        col_l, col_r = st.columns(2)

        with col_l:
            fig_cagr = go.Figure()
            fig_cagr.add_trace(go.Scatter(
                x=wfo["fold"], y=wfo["is_cagr"],
                mode="lines+markers", name="IS CAGR",
                line=dict(color=C_LINE, width=2),
            ))
            fig_cagr.add_trace(go.Scatter(
                x=wfo["fold"], y=wfo["oos_cagr"],
                mode="lines+markers", name="OOS CAGR",
                line=dict(color=C_ACC, width=2),
            ))
            fig_cagr.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_cagr.update_layout(
                height=300, template="plotly_dark",
                title="CAGR IS vs OOS per fold",
                xaxis_title="Fold", yaxis_title="CAGR %",
                margin=dict(l=0, r=0, t=40, b=0),
            )
            st.plotly_chart(fig_cagr, use_container_width=True)

        with col_r:
            fig_wfe = go.Figure(go.Bar(
                x=wfo["fold"].astype(str), y=wfo["wfe"],
                marker_color=[C_UP if v >= 0 else C_DOWN
                              for v in wfo["wfe"].fillna(0)],
                name="WFE",
            ))
            fig_wfe.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_wfe.update_layout(
                height=300, template="plotly_dark",
                title="Walk-Forward Efficiency (OOS/IS Sharpe)",
                xaxis_title="Fold", yaxis_title="WFE",
                margin=dict(l=0, r=0, t=40, b=0),
            )
            st.plotly_chart(fig_wfe, use_container_width=True)

        # ── Tabella riassuntiva ───────────────────────────────────────────────
        st.subheader("Dettaglio fold")
        cols_show = ["fold", "train_start", "train_end",
                     "test_start", "test_end",
                     "best_sl", "best_tp",
                     "is_sharpe", "oos_sharpe", "oos_cagr", "wfe"]
        cols_show = [c for c in cols_show if c in wfo.columns]
        st.dataframe(
            wfo[cols_show].style
                .background_gradient(subset=["oos_sharpe", "wfe"], cmap="RdYlGn")
                .format({c: "{:.2f}" for c in ["is_sharpe","oos_sharpe",
                                                "oos_cagr","wfe","best_sl","best_tp"]
                         if c in wfo.columns}),
            use_container_width=True,
        )

        wfe_mean = wfo["wfe"].mean()
        st.info(f"**WFE medio**: {wfe_mean:.2f}  —  "
                f"{'✅ modello robusto (WFE > 0.5)' if wfe_mean > 0.5 else '⚠️ rischio overfitting (WFE < 0.5)'}")

    except Exception as e:
        st.error(f"Errore caricamento dati WFO: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 4 — Monte Carlo
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    try:
        mc   = load_mc_bootstrap()
        stress = load_mc_stress()

        # ── Fan chart dai percentili bootstrap ────────────────────────────────
        # mc has percentile rows: percentile, final_cap_bs, cagr_bs, sharpe_bs, maxdd_bs
        pcts = [1, 5, 25, 50, 75, 95, 99]
        mc_pct = mc[mc["percentile"].isin(pcts)].set_index("percentile")

        # Build synthetic equity paths from percentiles
        trades_l = load_trades()
        n_trades = len(trades_l)
        cap0     = 10_000

        fig_fan = go.Figure()
        band_colors = {
            (1,99):   "rgba(239,83,80,0.10)",
            (5,95):   "rgba(255,152,0,0.15)",
            (25,75):  "rgba(38,166,154,0.20)",
        }
        for (lo, hi), fill_col in band_colors.items():
            if lo in mc_pct.index and hi in mc_pct.index:
                cap_lo = mc_pct.loc[lo, "final_cap_bs"]
                cap_hi = mc_pct.loc[hi, "final_cap_bs"]
                # linear interpolation across trade count
                y_lo = np.linspace(cap0, cap_lo, n_trades)
                y_hi = np.linspace(cap0, cap_hi, n_trades)
                fig_fan.add_trace(go.Scatter(
                    x=list(range(n_trades)) + list(range(n_trades))[::-1],
                    y=list(y_hi) + list(y_lo)[::-1],
                    fill="toself", fillcolor=fill_col,
                    line=dict(width=0),
                    name=f"P{lo}–P{hi}", showlegend=True,
                ))
        # Median
        if 50 in mc_pct.index:
            cap_med = mc_pct.loc[50, "final_cap_bs"]
            fig_fan.add_trace(go.Scatter(
                x=list(range(n_trades)),
                y=np.linspace(cap0, cap_med, n_trades),
                mode="lines", line=dict(color=C_UP, width=2.5),
                name="Mediana",
            ))
        fig_fan.add_hline(y=cap0, line_dash="dash", line_color="gray")
        fig_fan.update_layout(height=400, template="plotly_dark",
                              title="Monte Carlo Bootstrap — Fan chart equity (10.000 simulazioni)",
                              xaxis_title="Trade #", yaxis_title="Capitale (USDT)",
                              margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig_fan, use_container_width=True)

        # ── Metriche chiave MC ────────────────────────────────────────────────
        col1, col2, col3, col4 = st.columns(4)
        try:
            p50  = mc_pct.loc[50, "cagr_bs"]
            p5   = mc_pct.loc[5,  "cagr_bs"]
            p95  = mc_pct.loc[95, "cagr_bs"]
            p50d = mc_pct.loc[50, "maxdd_bs"]
            col1.metric("CAGR mediano",    f"{p50:.1f}%")
            col2.metric("CAGR P5–P95",     f"{p5:.1f}% / {p95:.1f}%")
            col3.metric("Max DD mediano",  f"{p50d:.1f}%")
            col4.metric("Capital finale P50",
                        f"${mc_pct.loc[50,'final_cap_bs']:,.0f}")
        except Exception:
            pass

        # ── Distribuzione CAGR bootstrap ─────────────────────────────────────
        col_l, col_r = st.columns(2)

        with col_l:
            fig_dist = go.Figure()
            fig_dist.add_trace(go.Bar(
                x=mc["percentile"], y=mc["cagr_bs"],
                marker_color=[C_UP if v >= 0 else C_DOWN for v in mc["cagr_bs"]],
                name="CAGR bootstrap",
            ))
            fig_dist.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_dist.update_layout(
                height=320, template="plotly_dark",
                title="Distribuzione CAGR per percentile (bootstrap)",
                xaxis_title="Percentile", yaxis_title="CAGR %",
                margin=dict(l=0, r=0, t=40, b=0),
            )
            st.plotly_chart(fig_dist, use_container_width=True)

        # ── Stress test ───────────────────────────────────────────────────────
        with col_r:
            fig_st = go.Figure(go.Bar(
                x=stress["scenario"],
                y=stress["cagr"],
                marker_color=[C_UP if v >= 0 else C_DOWN for v in stress["cagr"]],
                text=[f"{v:.1f}%" for v in stress["cagr"]],
                textposition="outside",
            ))
            fig_st.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_st.update_layout(
                height=320, template="plotly_dark",
                title="Stress test — CAGR per scenario",
                yaxis_title="CAGR %",
                margin=dict(l=0, r=0, t=40, b=0),
                xaxis_tickangle=-25,
            )
            st.plotly_chart(fig_st, use_container_width=True)

    except Exception as e:
        st.error(f"Errore caricamento dati Monte Carlo: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 5 — Multi-Asset
# ══════════════════════════════════════════════════════════════════════════════

with tab5:
    try:
        ma = load_multi_asset()

        # ── Bar chart metriche per asset ──────────────────────────────────────
        metrics = ["cagr_pct", "sharpe_ratio", "max_drawdown_pct", "win_rate_pct"]
        labels  = ["CAGR %",   "Sharpe",       "Max DD %",         "Win %"]

        fig_ma = make_subplots(rows=2, cols=2,
                               subplot_titles=labels,
                               vertical_spacing=0.18,
                               horizontal_spacing=0.1)
        positions = [(1,1),(1,2),(2,1),(2,2)]
        asset_colors = {"BTC": C_LINE, "ETH": "#9c27b0", "SOL": C_ACC}

        for (r, c), met, lab in zip(positions, metrics, labels):
            bar_colors = [asset_colors.get(a, "gray") for a in ma["asset"]]
            fig_ma.add_trace(
                go.Bar(x=ma["asset"], y=ma[met],
                       marker_color=bar_colors,
                       showlegend=False,
                       text=[f"{v:.1f}" for v in ma[met]],
                       textposition="outside"),
                row=r, col=c,
            )
            fig_ma.add_hline(y=0, line_dash="dash",
                             line_color="gray", row=r, col=c)

        fig_ma.update_layout(height=500, template="plotly_dark",
                             title="Performance per asset (estrategia V5)",
                             margin=dict(l=0, r=0, t=60, b=0))
        st.plotly_chart(fig_ma, use_container_width=True)

        # ── Tabella ───────────────────────────────────────────────────────────
        st.subheader("Tabella riassuntiva")
        disp_ma = ma[["asset", "capital_share", "cagr_pct", "sharpe_ratio",
                       "max_drawdown_pct", "win_rate_pct",
                       "n_trades", "total_costs_usd"]].copy()
        disp_ma.columns = ["Asset", "Peso %", "CAGR %", "Sharpe",
                            "Max DD %", "Win %", "Trade", "Costi USD"]
        disp_ma["Peso %"] = disp_ma["Peso %"] * 100
        st.dataframe(
            disp_ma.set_index("Asset").style
                .background_gradient(subset=["CAGR %", "Sharpe"], cmap="RdYlGn")
                .background_gradient(subset=["Max DD %"], cmap="RdYlGn_r")
                .format({"Peso %": "{:.0f}", "CAGR %": "{:.1f}",
                         "Sharpe": "{:.2f}", "Max DD %": "{:.1f}",
                         "Win %": "{:.1f}", "Costi USD": "{:.0f}"}),
            use_container_width=True,
        )

        # ── Peso portafoglio ──────────────────────────────────────────────────
        fig_alloc = go.Figure(go.Pie(
            labels=ma["asset"],
            values=ma["capital_share"],
            marker_colors=[asset_colors.get(a, "gray") for a in ma["asset"]],
            hole=0.5,
            textinfo="label+percent",
        ))
        fig_alloc.update_layout(
            height=300, template="plotly_dark",
            title="Allocazione portafoglio",
            margin=dict(l=0, r=80, t=40, b=0),
        )
        st.plotly_chart(fig_alloc, use_container_width=True)

    except Exception as e:
        st.error(f"Errore caricamento dati multi-asset: {e}")


# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("BTC Strategy Dashboard · Dati: sintetici (fallback) o Yahoo Finance via yfinance · "
           "Strategia V5: ATR breakout + GARCH filter + maker fees")
