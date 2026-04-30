"""
app.py — BTC Strategy Dashboard (Streamlit)
============================================
Avvio:
  streamlit run btc_analysis/app.py
"""

import os
import re
import sys
import subprocess
import warnings
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st

warnings.filterwarnings("ignore")

BASE   = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE, "output")

_KEYS_FILE = os.path.join(OUTPUT, "api_keys.json")

def _load_api_keys() -> dict:
    if os.path.exists(_KEYS_FILE):
        try:
            import json as _j
            return _j.load(open(_KEYS_FILE, encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_api_keys(keys: dict) -> None:
    import json as _j
    os.makedirs(OUTPUT, exist_ok=True)
    _j.dump(keys, open(_KEYS_FILE, "w", encoding="utf-8"), indent=2)

# ── Asset catalog & universe helpers ──────────────────────────────────────────

ASSET_CATALOG: dict = {
    "Crypto Majors": {
        "BTC-USD": "Bitcoin",   "ETH-USD": "Ethereum",  "SOL-USD": "Solana",
        "BNB-USD": "BNB",       "XRP-USD": "XRP",        "ADA-USD": "Cardano",
        "DOGE-USD": "Dogecoin", "AVAX-USD": "Avalanche", "DOT-USD": "Polkadot",
        "LINK-USD": "Chainlink",
    },
    "Commodities": {
        "GC=F": "Gold", "SI=F": "Silver", "CL=F": "Crude Oil WTI",
        "NG=F": "Natural Gas", "HG=F": "Copper",
    },
    "Stocks US": {
        "SPY": "S&P 500 ETF", "QQQ": "Nasdaq ETF",
        "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA",
        "TSLA": "Tesla", "GOOGL": "Alphabet", "AMZN": "Amazon", "META": "Meta",
    },
    "Stocks EU": {
        "MC.PA": "LVMH", "SAP.DE": "SAP",    "ASML.AS": "ASML",
        "SIE.DE": "Siemens", "ALV.DE": "Allianz", "SAN.PA": "Sanofi",
        "BNP.PA": "BNP Paribas", "NESN.SW": "Nestlé",
    },
}
_TICKER_ALIAS = {"BTC-USD": "btc", "ETH-USD": "eth", "SOL-USD": "sol"}
_CATALOG_FLAT = {t: n for cat in ASSET_CATALOG.values() for t, n in cat.items()}

def ticker_to_fname(ticker: str) -> str:
    if ticker in _TICKER_ALIAS:
        return _TICKER_ALIAS[ticker]
    return re.sub(r"[^a-z0-9]", "_", ticker.lower()).strip("_")

_SELECTED_FILE = os.path.join(OUTPUT, "selected_assets.json")

def _load_selected_assets() -> list:
    if os.path.exists(_SELECTED_FILE):
        try:
            import json as _j
            return _j.load(open(_SELECTED_FILE, encoding="utf-8"))
        except Exception:
            pass
    return ["BTC-USD", "ETH-USD", "SOL-USD"]

def _save_selected_assets(tickers: list) -> None:
    import json as _j
    os.makedirs(OUTPUT, exist_ok=True)
    _j.dump(tickers, open(_SELECTED_FILE, "w", encoding="utf-8"), indent=2)

st.set_page_config(
    page_title="BTC Strategy Dashboard",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Genera dati se mancanti ────────────────────────────────────────────────────
_REQUIRED = [
    "btc_daily.csv", "btc_hourly.csv",
    "eth_hourly.csv", "sol_hourly.csv", "trades.csv",
]

def _run_script(name: str, extra_env: dict = None):
    env = os.environ.copy()
    _k = _load_api_keys()
    for _key in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
        if _k.get(_key):
            env[_key] = _k[_key]
    if extra_env:
        env.update(extra_env)
    subprocess.run(
        [sys.executable, os.path.join(BASE, name)],
        check=True, capture_output=True, env=env,
    )

def ensure_data():
    os.makedirs(OUTPUT, exist_ok=True)
    missing = [f for f in _REQUIRED if not os.path.exists(os.path.join(OUTPUT, f))]
    if not missing:
        return
    with st.spinner(f"Prima esecuzione: generazione dati ({', '.join(missing)})…"):
        try:
            _run_script("01_data_download.py")
            if "trades.csv" in missing:
                _run_script("04_strategy.py")
                _run_script("06_enhanced_strategy.py")
        except subprocess.CalledProcessError as e:
            st.error(f"Errore generazione dati: {e.stderr.decode()[:400]}")
            st.stop()
    st.rerun()

ensure_data()

# ── Palette ───────────────────────────────────────────────────────────────────
C_UP   = "#26a69a"
C_DOWN = "#ef5350"
C_LINE = "#2196f3"
C_ACC  = "#ff9800"
ASSET_COLORS = {"BTC": C_LINE, "ETH": "#9c27b0", "SOL": C_ACC}

# ══════════════════════════════════════════════════════════════════════════════
#  Sidebar
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("⚙️ Impostazioni")

    st.subheader("📅 Periodo prezzi")
    yr_from = st.number_input("Anno inizio", min_value=2015, max_value=2025,
                               value=2020, step=1)
    yr_to   = st.number_input("Anno fine",   min_value=2015, max_value=2025,
                               value=2025, step=1)

    st.divider()

    # ── Asset Universe ─────────────────────────────────────────────────────────
    st.subheader("📊 Asset Universe")
    _sel_saved = _load_selected_assets()
    _downloaded = [t for t in _sel_saved
                   if os.path.exists(os.path.join(OUTPUT, f"{ticker_to_fname(t)}_hourly.csv"))]

    # Load current strategy asset from config (needed to pre-select the selectbox)
    _cfg_path  = os.path.join(OUTPUT, "agent_strategy_config.json")
    _cur_src   = "—"
    _cur_asset = "BTC-USD"
    if os.path.exists(_cfg_path):
        try:
            import json as _j0
            _ac0 = _j0.load(open(_cfg_path))
            _cur_src   = _ac0.get("source", "?")
            _cur_asset = _ac0.get("asset", "BTC-USD")
        except Exception:
            pass

    # Full selectable list: catalog + user's saved universe (union, no duplicates)
    _all_tickers = list(dict.fromkeys(
        ["BTC-USD"] + list(_CATALOG_FLAT.keys()) + _sel_saved
    ))
    _cur_asset_sel = _cur_asset if _cur_asset in _all_tickers else "BTC-USD"
    asset = st.selectbox(
        "Asset",
        options=_all_tickers,
        index=_all_tickers.index(_cur_asset_sel),
        format_func=lambda t: f"{_CATALOG_FLAT.get(t, t)} ({t})",
        help="Tutti gli asset del catalogo + quelli nel tuo universe. Se non scaricato, download automatico al primo utilizzo.",
    )
    _asset_csv = os.path.join(OUTPUT, f"{ticker_to_fname(asset)}_hourly.csv")
    if not os.path.exists(_asset_csv):
        st.caption(f"⬇️ `{asset}` non ancora scaricato — download automatico al primo utilizzo.")

    with st.expander("➕ Aggiungi asset al universe"):
        _new_sel: list = []
        for _cat, _items in ASSET_CATALOG.items():
            _defaults = [t for t in _sel_saved if t in _items]
            _chosen = st.multiselect(
                _cat, options=list(_items.keys()), default=_defaults,
                format_func=lambda t, _i=_items: f"{_i.get(t, t)} ({t})",
                key=f"univ_{_cat}",
            )
            _new_sel.extend(_chosen)
        _uc1, _uc2 = st.columns(2)
        with _uc1:
            if st.button("💾 Salva", use_container_width=True, key="save_univ"):
                _save_selected_assets(_new_sel)
                st.success(f"{len(_new_sel)} salvati.")
        with _uc2:
            if st.button("⬇️ Scarica", use_container_width=True, key="dl_univ",
                         help="Scarica CSV orari per i nuovi asset"):
                _save_selected_assets(_new_sel)
                _to_dl = [t for t in _new_sel
                          if not os.path.exists(
                              os.path.join(OUTPUT, f"{ticker_to_fname(t)}_hourly.csv"))]
                if _to_dl:
                    with st.spinner(f"Download {len(_to_dl)} asset…"):
                        try:
                            import importlib.util as _ilu
                            _spec = _ilu.spec_from_file_location(
                                "dl01", os.path.join(BASE, "01_data_download.py"))
                            _dlm = _ilu.module_from_spec(_spec)
                            _spec.loader.exec_module(_dlm)
                            _r = _dlm.download_all_assets(_to_dl, skip_existing=True)
                            _ok = sum(_r.values())
                            st.success(f"OK {_ok}/{len(_to_dl)}")
                            st.cache_data.clear()
                        except Exception as _de:
                            st.error(f"Errore: {_de}")
                else:
                    st.info("Dati già presenti.")
                st.rerun()

    st.divider()

    # ── Chiavi API ────────────────────────────────────────────────────────────
    st.subheader("🔑 Chiavi API")
    _sk = _load_api_keys()

    st.caption("🤖 Agent AI")
    _ant_key = st.text_input(
        "ANTHROPIC_API_KEY",
        value=_sk.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", ""),
        type="password", placeholder="sk-ant-…",
        help="Claude claude-opus-4-7 con adaptive thinking",
    )
    _or_key = st.text_input(
        "OPENROUTER_API_KEY",
        value=_sk.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY", ""),
        type="password", placeholder="sk-or-…",
        help="Alternativa: Claude/GPT-4o/Gemini via OpenRouter",
    )
    _or_model = st.text_input(
        "OPENROUTER_MODEL",
        value=_sk.get("OPENROUTER_MODEL") or os.environ.get("OPENROUTER_MODEL", "anthropic/claude-opus-4"),
        help="Ignorato se si usa Anthropic diretto",
    )

    st.caption("📡 Dati (Alpaca Markets)")
    _alp_key = st.text_input(
        "ALPACA_API_KEY",
        value=_sk.get("ALPACA_API_KEY") or os.environ.get("ALPACA_API_KEY", ""),
        type="password", placeholder="PK…",
        help="Fallback se Yahoo Finance non è disponibile",
    )
    _alp_sec = st.text_input(
        "ALPACA_SECRET_KEY",
        value=_sk.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY", ""),
        type="password", placeholder="…",
    )

    if st.button("💾 Salva tutte le chiavi", use_container_width=True,
                 help="Salva in output/api_keys.json (escluso da git)"):
        _save_api_keys({
            "ANTHROPIC_API_KEY":  _ant_key,
            "OPENROUTER_API_KEY": _or_key,
            "OPENROUTER_MODEL":   _or_model,
            "ALPACA_API_KEY":     _alp_key,
            "ALPACA_SECRET_KEY":  _alp_sec,
        })
        st.success("Chiavi salvate.")

    st.divider()

    # ── Agent AI configurator ─────────────────────────────────────────────────
    st.subheader("🤖 Agent AI")
    st.caption(f"Config attuale: `{_cur_src}` | asset: `{_cur_asset}`")

    if st.button("▶ Esegui Agent", use_container_width=True):
        if not _ant_key and not _or_key:
            st.warning("Inserisci almeno una chiave AI (Anthropic o OpenRouter).")
        else:
            # Download asset data if missing
            if not os.path.exists(_asset_csv):
                with st.spinner(f"Download dati {asset}…"):
                    try:
                        import importlib.util as _ilu2
                        _spec2 = _ilu2.spec_from_file_location(
                            "dl01b", os.path.join(BASE, "01_data_download.py"))
                        _dlm2 = _ilu2.module_from_spec(_spec2)
                        _spec2.loader.exec_module(_dlm2)
                        _r2 = _dlm2.download_all_assets([asset], skip_existing=False)
                        if not _r2.get(asset):
                            st.error(f"Impossibile scaricare i dati per {asset}.")
                            st.stop()
                        st.cache_data.clear()
                    except Exception as _de2:
                        st.error(f"Errore download {asset}: {_de2}")
                        st.stop()
            import sys as _sys
            _sys.path.insert(0, BASE)
            import importlib, agent_strategy as _ag
            importlib.reload(_ag)
            with st.spinner(f"L'agent sta analizzando {asset}…"):
                try:
                    _cfg_r, _code_r, _report_r = _ag.run_agent(
                        anthropic_key=_ant_key,
                        openrouter_key=_or_key,
                        openrouter_model=_or_model,
                        asset=asset,
                    )
                    _ag.save_outputs(_cfg_r, _code_r, _report_r)
                except Exception as _ae:
                    st.error(f"Errore agent: {_ae}")
                    st.stop()
            with st.spinner(f"Backtest {asset}…"):
                try:
                    _run_script("06_enhanced_strategy.py",
                                extra_env={"STRATEGY_ASSET": asset})
                    st.cache_data.clear()
                    st.success(
                        f"✅ Strategia `{_cfg_r.get('strategy_type','')}` su "
                        f"`{asset}` pronta. Vedi Tab **🤖 Agent Strategy**."
                    )
                except subprocess.CalledProcessError as _be:
                    st.warning(f"Backtest fallito: {_be.stderr.decode()[:300]}")
            st.rerun()

    st.divider()
    st.subheader("ℹ️ Info")
    _info_name = "ATR Breakout + GARCH Filter (default)"
    _info_type = "breakout"
    if os.path.exists(_cfg_path):
        try:
            import json as _j2
            _info_cfg  = _j2.load(open(_cfg_path))
            _info_name = _info_cfg.get("strategy_name", _info_name)
            _info_type = _info_cfg.get("strategy_type", _info_type)
        except Exception:
            pass
    st.caption(
        f"**Strategia**: {_info_name}\n"
        f"**Tipo**: {_info_type}\n"
        "**Dati**: Yahoo Finance · Alpaca Markets"
    )
    if st.button("🔄 Rigenera dati", use_container_width=True):
        st.cache_data.clear()
        for f in _REQUIRED:
            p = os.path.join(OUTPUT, f)
            if os.path.exists(p):
                os.remove(p)
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  Data loaders (cached)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data
def load_ohlcv_daily(sym: str) -> pd.DataFrame:
    fname = ticker_to_fname(sym)
    path  = os.path.join(OUTPUT, f"{fname}_daily.csv")
    if not os.path.exists(path):
        path = os.path.join(OUTPUT, "btc_daily.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index.name = "Date"
    return df

@st.cache_data
def load_ohlcv_hourly(sym: str) -> pd.DataFrame:
    path = os.path.join(OUTPUT, f"{ticker_to_fname(sym)}_hourly.csv")
    df   = pd.read_csv(path, index_col=0, parse_dates=True)
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


# ── Helpers ───────────────────────────────────────────────────────────────────

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

_ASSET_EMOJI = {"BTC-USD": "₿", "ETH-USD": "⟠", "SOL-USD": "◎"}
_aname = _CATALOG_FLAT.get(asset, asset)
st.title(f"{_ASSET_EMOJI.get(asset, '📈')} {_aname} — Strategy Dashboard")
st.caption("Analisi serie storica · Strategia V5 · Walk-Forward · Monte Carlo · Multi-Asset")

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

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Prezzi & Rendimenti",
    "📈 Strategia V5",
    "🔄 Walk-Forward",
    "🎲 Monte Carlo",
    "🌐 Multi-Asset",
    "🤖 Agent Strategy",
])


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — Prezzi & Rendimenti
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    from scipy import stats as scipy_stats

    if not os.path.exists(_asset_csv):
        st.info(
            f"**{_CATALOG_FLAT.get(asset, asset)} ({asset})** non è ancora stato scaricato. "
            "Clicca **▶ Esegui Agent** nel sidebar (scarica e analizza automaticamente) "
            "oppure usa **⬇️ Scarica** nella sezione 📊 Asset Universe."
        )

    a_color = ASSET_COLORS.get(asset, C_LINE)
    daily   = load_ohlcv_daily(asset)
    d = daily[(daily.index.year >= yr_from) & (daily.index.year <= yr_to)]

    if d.empty:
        st.warning("Nessun dato per il periodo selezionato.")
    else:
        # ── Candlestick + Volume ──────────────────────────────────────────────
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            row_heights=[0.75, 0.25], vertical_spacing=0.03)
        fig.add_trace(go.Candlestick(
            x=d.index, open=d["Open"], high=d["High"],
            low=d["Low"], close=d["Close"],
            increasing_line_color=C_UP, decreasing_line_color=C_DOWN,
            name=f"{asset}/USD",
        ), row=1, col=1)
        bar_colors = [C_UP if c >= o else C_DOWN
                      for c, o in zip(d["Close"], d["Open"])]
        fig.add_trace(go.Bar(x=d.index, y=d["Volume"],
                             marker_color=bar_colors,
                             showlegend=False, name="Volume"), row=2, col=1)
        fig.update_layout(height=500, xaxis_rangeslider_visible=False,
                          margin=dict(l=0, r=0, t=30, b=0),
                          template="plotly_dark",
                          title=f"{asset}/USD — Candlestick giornaliero")
        fig.update_yaxes(title_text="Prezzo (USD)", row=1, col=1)
        fig.update_yaxes(title_text="Volume",       row=2, col=1)
        st.plotly_chart(fig, use_container_width=True)

        # ── Log-returns + Distribuzione ───────────────────────────────────────
        log_ret = np.log(d["Close"] / d["Close"].shift(1)).dropna()
        col_l, col_r = st.columns(2)

        with col_l:
            fig2 = go.Figure(go.Scatter(
                x=log_ret.index, y=log_ret.values,
                mode="lines", line=dict(color=a_color, width=1),
                name="Log-return",
            ))
            fig2.update_layout(height=300, template="plotly_dark",
                                title="Log-returns giornalieri",
                                margin=dict(l=0, r=0, t=40, b=0),
                                yaxis_title="Log-return")
            st.plotly_chart(fig2, use_container_width=True)

        with col_r:
            mu, sigma = log_ret.mean(), log_ret.std()
            x_n = np.linspace(log_ret.min(), log_ret.max(), 200)
            y_n = (np.exp(-0.5 * ((x_n - mu) / sigma) ** 2)
                   / (sigma * np.sqrt(2 * np.pi))
                   * len(log_ret) * (log_ret.max() - log_ret.min()) / 80)
            fig3 = go.Figure()
            fig3.add_trace(go.Histogram(x=log_ret.values, nbinsx=80,
                                        marker_color=a_color, opacity=0.75,
                                        name="Empirica"))
            fig3.add_trace(go.Scatter(x=x_n, y=y_n, mode="lines",
                                      line=dict(color=C_ACC, width=2),
                                      name="Normale"))
            fig3.update_layout(height=300, template="plotly_dark",
                                title="Distribuzione log-returns",
                                margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig3, use_container_width=True)

        # ── Statistiche ───────────────────────────────────────────────────────
        kurt    = float(scipy_stats.kurtosis(log_ret, fisher=True))
        skew_v  = float(scipy_stats.skew(log_ret))
        _, jb_p = scipy_stats.jarque_bera(log_ret)
        ann_vol = log_ret.std() * np.sqrt(252) * 100

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Volatilità annua",  f"{ann_vol:.1f}%")
        c2.metric("Curtosi (excess)",  f"{kurt:.2f}")
        c3.metric("Skewness",          f"{skew_v:.3f}")
        c4.metric("Jarque-Bera p-val", f"{jb_p:.4f}")

        # ── Pattern intraday ──────────────────────────────────────────────────
        st.subheader(f"Pattern intraday {asset} (dati orari)")
        try:
            hourly = load_ohlcv_hourly(asset)
            hourly["log_ret"] = np.log(hourly["Close"] / hourly["Close"].shift(1))
            by_hour = hourly.groupby(hourly.index.hour)["log_ret"].mean() * 1e4
            fig4 = go.Figure(go.Bar(
                x=by_hour.index, y=by_hour.values,
                marker_color=[C_UP if v >= 0 else C_DOWN for v in by_hour.values],
            ))
            fig4.update_layout(height=280, template="plotly_dark",
                                title=f"Rendimento medio per ora del giorno (UTC) — {asset}",
                                xaxis_title="Ora (UTC)",
                                yaxis_title="Rendimento medio (bp)",
                                margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig4, use_container_width=True)
        except Exception:
            st.info("Dati orari non disponibili.")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — Strategia V5
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    if ticker_to_fname(asset) != "btc":
        st.info("Il backtest della strategia V5 è calcolato su **BTC**. "
                "I risultati per ETH e SOL sono disponibili nel tab 🌐 Multi-Asset.")
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
    if ticker_to_fname(asset) != "btc":
        st.info("La Walk-Forward Optimization è calcolata su **BTC**. "
                "I risultati per altri asset sono in sviluppo.")
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
    if ticker_to_fname(asset) != "btc":
        st.info("La simulazione Monte Carlo è calcolata su **BTC**. "
                "Seleziona BTC nella sidebar per la visione completa.")
    try:
        mc     = load_mc_bootstrap()
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

        for (r, c), met, lab in zip(positions, metrics, labels):
            # Evidenzia l'asset selezionato nella sidebar
            bar_colors = [
                ASSET_COLORS.get(a, "gray") if a == asset
                else f"rgba({','.join(str(int(ASSET_COLORS.get(a,'#888888').lstrip('#')[i:i+2],16)) for i in (0,2,4))},0.35)"
                for a in ma["asset"]
            ]
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
            marker_colors=[ASSET_COLORS.get(a, "gray") for a in ma["asset"]],
            hole=0.5,
            textinfo="label+percent",
            pull=[0.08 if a == asset else 0 for a in ma["asset"]],
        ))
        fig_alloc.update_layout(
            height=300, template="plotly_dark",
            title="Allocazione portafoglio",
            margin=dict(l=0, r=80, t=40, b=0),
        )
        st.plotly_chart(fig_alloc, use_container_width=True)

    except Exception as e:
        st.error(f"Errore caricamento dati multi-asset: {e}")

    # ── Asset Universe Performance ────────────────────────────────────────────
    st.divider()
    st.subheader("🌍 Asset Universe Performance")
    _univ_sel = _load_selected_assets()
    _univ_avail = [t for t in _univ_sel
                   if os.path.exists(os.path.join(OUTPUT, f"{ticker_to_fname(t)}_hourly.csv"))]
    if not _univ_avail:
        st.info("Nessun asset scaricato. Usa **📊 Asset Universe** nel sidebar per aggiungerne.")
    else:
        _rets: dict = {}
        for _t in _univ_avail:
            try:
                _dh = load_ohlcv_hourly(_t)
                _dc = _dh["Close"].resample("D").last().dropna()
                _rets[_CATALOG_FLAT.get(_t, _t)] = _dc.pct_change().dropna()
            except Exception:
                pass

        if _rets:
            # Cumulative return chart
            _fig_u = go.Figure()
            for _nm, _r in _rets.items():
                _cum = (1 + _r).cumprod() - 1
                _fig_u.add_trace(go.Scatter(
                    x=_cum.index, y=(_cum * 100).values,
                    name=_nm, mode="lines", line=dict(width=1.5),
                ))
            _fig_u.update_layout(
                height=350, template="plotly_dark",
                title="Rendimento cumulativo normalizzato (%)",
                yaxis_ticksuffix="%",
                legend=dict(orientation="h", y=-0.2),
            )
            st.plotly_chart(_fig_u, use_container_width=True)

            # Performance table
            _rows = {}
            for _nm, _r in _rets.items():
                _ann_ret = (1 + _r).prod() ** (252 / max(len(_r), 1)) - 1
                _ann_vol = _r.std() * np.sqrt(252)
                _sharpe  = _ann_ret / _ann_vol if _ann_vol > 0 else 0
                _cum_s   = (1 + _r).cumprod()
                _max_dd  = (_cum_s / _cum_s.cummax() - 1).min()
                _rows[_nm] = {
                    "Ann. Return %": round(_ann_ret * 100, 2),
                    "Volatilità %":  round(_ann_vol * 100, 2),
                    "Sharpe":        round(_sharpe, 2),
                    "Max DD %":      round(_max_dd * 100, 2),
                }
            _pf = pd.DataFrame(_rows).T.sort_values("Sharpe", ascending=False)
            st.dataframe(
                _pf.style
                   .background_gradient(subset=["Ann. Return %", "Sharpe"], cmap="RdYlGn")
                   .background_gradient(subset=["Max DD %", "Volatilità %"], cmap="RdYlGn_r")
                   .format("{:.2f}"),
                use_container_width=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 6 — Agent Strategy
# ══════════════════════════════════════════════════════════════════════════════

with tab6:
    import json as _json

    st.subheader("🤖 Agent Strategy")
    st.markdown(
        "L'**AI Agent** analizza le proprietà statistiche della serie storica "
        "(Hurst, autocorrelazione, kurtosis, regimi GARCH, pattern intraday) e "
        "**progetta la strategia ottimale da zero** — scegliendo tra trend following, "
        "mean reversion, breakout o range trading — scrivendo il codice Python "
        "eseguito direttamente dalla pipeline."
    )

    _cfg_path = os.path.join(OUTPUT, "agent_strategy_config.json")
    _rpt_path = os.path.join(OUTPUT, "agent_strategy_report.md")
    _code_path = os.path.join(OUTPUT, "agent_strategy_code.py")

    if not os.path.exists(_cfg_path):
        st.info(
            "L'agent non è ancora stato eseguito. Configura una chiave API "
            "nella sidebar e clicca **▶ Esegui Agent**, oppure esegui `run_all.py`."
        )
    else:
        try:
            with open(_cfg_path) as _f:
                _cfg = _json.load(_f)

            _src = _cfg.get("source", "unknown")
            if _src.startswith("anthropic"):
                st.success(f"✅ Strategia generata da **Anthropic** (`{_src}`)")
            elif _src.startswith("openrouter"):
                st.success(f"✅ Strategia generata da **OpenRouter** (`{_src}`)")
            else:
                st.warning(
                    f"⚠️ Strategia di **default V5** (`{_src}`). "
                    "Imposta una chiave API per far progettare la strategia all'AI."
                )

            # ── KPI ──────────────────────────────────────────────────────────
            _ah = _cfg.get("active_hours", [6, 22])
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Tipo strategia",   _cfg.get("strategy_type", "—").replace("_", " ").title())
            c2.metric("SL",               f"{_cfg.get('sl_mult', 2.0):.2f}×ATR")
            c3.metric("TP",               f"{_cfg.get('tp_mult', 5.0):.2f}×ATR")
            c4.metric("Ore attive UTC",   f"{_ah[0]:02d}:00–{_ah[1]:02d}:00")
            c5.metric("Risk/trade",       f"{_cfg.get('risk_per_trade', 0.01)*100:.1f}%")

            # ── Backtest results from enhanced_strategy_comparison.csv ─────────
            _comp_path = os.path.join(OUTPUT, "enhanced_strategy_comparison.csv")
            if os.path.exists(_comp_path):
                try:
                    _comp = pd.read_csv(_comp_path)
                    _vrow = _comp[_comp["version"] == "V_Agent"]
                    if not _vrow.empty:
                        _r = _vrow.iloc[0]
                        st.subheader("📊 Backtest V_Agent")
                        _bc1, _bc2, _bc3, _bc4, _bc5, _bc6 = st.columns(6)
                        _bc1.metric("Return totale",  f"{_r['total_return_pct']:.1f}%")
                        _bc2.metric("CAGR",           f"{_r['cagr_pct']:.1f}%")
                        _bc3.metric("Sharpe",         f"{_r['sharpe_ratio']:.2f}")
                        _bc4.metric("Max DD",         f"{_r['max_drawdown_pct']:.1f}%")
                        _bc5.metric("Win rate",       f"{_r['win_rate_pct']:.1f}%")
                        _bc6.metric("# Trade",        int(_r["n_trades"]))

                        # compare V_Agent vs V4 (best baseline)
                        _v4 = _comp[_comp["version"] == "V4 +GARCH+Costi"]
                        if not _v4.empty:
                            _v4r = _v4.iloc[0]
                            st.markdown(
                                f"**vs V4 baseline** — CAGR: "
                                f"`{_r['cagr_pct']:.1f}%` vs `{_v4r['cagr_pct']:.1f}%` · "
                                f"Sharpe: `{_r['sharpe_ratio']:.2f}` vs "
                                f"`{_v4r['sharpe_ratio']:.2f}` · "
                                f"Max DD: `{_r['max_drawdown_pct']:.1f}%` vs "
                                f"`{_v4r['max_drawdown_pct']:.1f}%`"
                            )
                    else:
                        st.info("Esegui **▶ Esegui Agent** per calcolare il backtest V_Agent.")
                except Exception as _ce:
                    st.warning(f"Errore lettura metriche backtest: {_ce}")

            st.divider()

            # ── Markdown report ───────────────────────────────────────────────
            if os.path.exists(_rpt_path):
                st.markdown("### 📄 Report dell'Agent")
                st.markdown(open(_rpt_path, encoding="utf-8").read())
                st.divider()

            # ── Strategy code ─────────────────────────────────────────────────
            if os.path.exists(_code_path):
                with st.expander("📝 Codice strategia (`generate_signals_agent`)"):
                    st.code(open(_code_path, encoding="utf-8").read(), language="python")

            # ── Raw JSON ─────────────────────────────────────────────────────
            with st.expander("⚙️ Raw JSON config"):
                st.json(_cfg)

        except Exception as _e:
            st.error(f"Errore lettura output agent: {_e}")


# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("BTC Strategy Dashboard · Dati: sintetici (fallback) o Yahoo Finance via yfinance · "
           "Agent Strategy: parametri ottimizzati da Claude claude-opus-4-7")
