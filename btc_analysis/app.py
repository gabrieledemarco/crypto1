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
    page_title="Crypto Strategy Dashboard",
    page_icon="📈",
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
                _run_script("04_backtest.py")
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
ASSET_COLORS = {
    "BTC-USD": C_LINE,    "BTC": C_LINE,
    "ETH-USD": "#9c27b0", "ETH": "#9c27b0",
    "SOL-USD": C_ACC,     "SOL": C_ACC,
}

# ══════════════════════════════════════════════════════════════════════════════
#  Sidebar
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("⚙️ Impostazioni")

    _CHART_TF = {
        "1 settimana":     7,
        "1 mese":         30,
        "3 mesi":         90,
        "6 mesi":        180,
        "1 anno":        365,
        "2 anni":        730,
        "Max disponibile": None,
    }
    chart_tf_label = st.selectbox(
        "📅 Timeframe grafici",
        options=list(_CHART_TF.keys()),
        index=4,
        help="Finestra temporale mostrata in tutti i grafici.",
    )
    _chart_days = _CHART_TF[chart_tf_label]
    chart_start = (
        pd.Timestamp.today() - pd.Timedelta(days=_chart_days)
    ) if _chart_days is not None else None

    _INTERVALS = {
        "1 min  (max 7 gg)":    ("1m",  7),
        "15 min (max 60 gg)":   ("15m", 60),
        "30 min (max 60 gg)":   ("30m", 60),
        "1 ora":                ("1h",  720),
        "4 ore":                ("4h",  720),
        "Giornaliero":          ("1d",  None),
    }
    chart_interval_label = st.selectbox(
        "🕯️ Intervallo candele",
        options=list(_INTERVALS.keys()),
        index=3,
        help="Granularità delle candele nei grafici. Intervalli < 1h richiedono download separato.",
    )
    chart_interval, _interval_max_days = _INTERVALS[chart_interval_label]

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

    # ── Timeframe dati orari ───────────────────────────────────────────────────
    _YFINANCE_LIMIT = 720   # giorni massimi supportati da yfinance per dati orari
    _TF_OPTIONS = {
        "3 mesi  (90 gg)":    90,
        "6 mesi  (180 gg)":  180,
        "1 anno  (365 gg)":  365,
        "2 anni  (730 gg)":  730,
    }
    _tf_label = st.selectbox(
        "📅 Finestra dati orari",
        options=list(_TF_OPTIONS.keys()),
        index=2,
        help="Periodo di storia scaricato per l'analisi e il backtest (dati orari).",
    )
    _tf_requested = _TF_OPTIONS[_tf_label]
    if _tf_requested > _YFINANCE_LIMIT:
        _tf_actual = _YFINANCE_LIMIT
        st.warning(
            f"⚠️ yfinance fornisce dati orari per massimo ~730 giorni. "
            f"La finestra verrà ridotta da **{_tf_requested}** a **{_tf_actual} giorni** "
            f"({_tf_actual // 30} mesi circa, dal "
            f"{(pd.Timestamp.today() - pd.Timedelta(days=_tf_actual)).strftime('%d/%m/%Y')}"
            " ad oggi)."
        )
    else:
        _tf_actual = _tf_requested

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
                            _dlm.HOURLY_DAYS  = _tf_actual
                            _dlm.HOURLY_START = (
                                pd.Timestamp.today() - pd.Timedelta(days=_tf_actual)
                            ).strftime("%Y-%m-%d")
                            _r = _dlm.download_all_assets(_to_dl, skip_existing=True)
                            _ok = sum(1 for v in _r.values() if v is True)
                            _errs = {t: v for t, v in _r.items() if v is not True}
                            st.success(f"OK {_ok}/{len(_to_dl)}")
                            if _errs:
                                for _et, _emsg in _errs.items():
                                    st.error(f"{_et}: {_emsg}")
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

    # Keys already set in os.environ (e.g. Railway) are used directly —
    # their input fields are hidden to avoid redundancy.
    def _resolve_key(name: str, default: str = "") -> tuple:
        env_val = os.environ.get(name, "")
        if env_val:
            return env_val, True   # (value, from_env)
        return _sk.get(name, "") or default, False

    _ant_key,    _ant_env = _resolve_key("ANTHROPIC_API_KEY")
    _or_key,     _or_env  = _resolve_key("OPENROUTER_API_KEY")
    _or_model,   _orm_env = _resolve_key("OPENROUTER_MODEL", "anthropic/claude-opus-4")
    _vibe_url,   _vu_env  = _resolve_key("VIBE_TRADING_API_URL")
    _vibe_token, _vt_env  = _resolve_key("VIBE_SERVICE_TOKEN")
    _alp_key,    _ak_env  = _resolve_key("ALPACA_API_KEY")
    _alp_sec,    _as_env  = _resolve_key("ALPACA_SECRET_KEY")

    _from_env_flags = [_ant_env, _or_env, _orm_env, _vu_env, _vt_env, _ak_env, _as_env]
    if any(_from_env_flags):
        st.caption("🚂 Le chiavi contrassegnate con ✅ provengono da variabili d'ambiente (Railway).")

    st.caption("🤖 Agent AI")
    if _ant_env:
        st.caption("✅ ANTHROPIC_API_KEY — da Railway")
    else:
        _ant_key = st.text_input(
            "ANTHROPIC_API_KEY", value=_ant_key,
            type="password", placeholder="sk-ant-…",
            help="Claude claude-opus-4-7 con adaptive thinking",
        )

    if _or_env:
        st.caption("✅ OPENROUTER_API_KEY — da Railway")
    else:
        _or_key = st.text_input(
            "OPENROUTER_API_KEY", value=_or_key,
            type="password", placeholder="sk-or-…",
            help="Alternativa: Claude/GPT-4o/Gemini via OpenRouter",
        )

    if _orm_env:
        st.caption(f"✅ OPENROUTER_MODEL — da Railway (`{_or_model}`)")
    else:
        _or_model = st.text_input(
            "OPENROUTER_MODEL", value=_or_model,
            help="Ignorato se si usa Anthropic diretto",
        )

    st.caption("🚂 Vibe-Trading (Railway)")
    if _vu_env:
        st.caption("✅ VIBE_TRADING_API_URL — da Railway")
    else:
        _vibe_url = st.text_input(
            "VIBE_TRADING_API_URL", value=_vibe_url,
            placeholder="https://your-service.up.railway.app",
            help="URL del microservizio Vibe-Trading su Railway. "
                 "Lascia vuoto per usare la CLI locale (o il fallback AI).",
        )

    if _vt_env:
        st.caption("✅ VIBE_SERVICE_TOKEN — da Railway")
    else:
        _vibe_token = st.text_input(
            "VIBE_SERVICE_TOKEN", value=_vibe_token,
            type="password", placeholder="token opzionale",
            help="SERVICE_TOKEN configurato sul servizio Railway (opzionale).",
        )

    st.caption("📡 Dati (Alpaca Markets)")
    if _ak_env:
        st.caption("✅ ALPACA_API_KEY — da Railway")
    else:
        _alp_key = st.text_input(
            "ALPACA_API_KEY", value=_alp_key,
            type="password", placeholder="PK…",
            help="Fallback se Yahoo Finance non è disponibile",
        )

    if _as_env:
        st.caption("✅ ALPACA_SECRET_KEY — da Railway")
    else:
        _alp_sec = st.text_input(
            "ALPACA_SECRET_KEY", value=_alp_sec,
            type="password", placeholder="…",
        )

    # Save button only when at least one key is entered via the UI (not env)
    if not all(_from_env_flags):
        if st.button("💾 Salva tutte le chiavi", use_container_width=True,
                     help="Salva in output/api_keys.json (escluso da git)"):
            _to_save = dict(_sk)
            if not _ant_env: _to_save["ANTHROPIC_API_KEY"]    = _ant_key
            if not _or_env:  _to_save["OPENROUTER_API_KEY"]   = _or_key
            if not _orm_env: _to_save["OPENROUTER_MODEL"]     = _or_model
            if not _vu_env:  _to_save["VIBE_TRADING_API_URL"] = _vibe_url
            if not _vt_env:  _to_save["VIBE_SERVICE_TOKEN"]   = _vibe_token
            if not _ak_env:  _to_save["ALPACA_API_KEY"]       = _alp_key
            if not _as_env:  _to_save["ALPACA_SECRET_KEY"]    = _alp_sec
            _save_api_keys(_to_save)
            st.success("Chiavi salvate.")

    st.divider()

    # ── Agent AI — step separati ──────────────────────────────────────────────
    st.subheader("🤖 Agent AI")
    st.caption(f"Config attuale: `{_cur_src}` | asset: `{_cur_asset}`")

    # ── Direction filter (persistent — applied to every backtest run) ────────────
    _direction_filter = st.radio(
        "📊 Direzione segnali",
        options=["ALL", "LONG", "SHORT"],
        format_func=lambda d: {
            "ALL":   "🔀 Tutti (LONG + SHORT)",
            "LONG":  "🟢 Solo LONG",
            "SHORT": "🔴 Solo SHORT",
        }[d],
        horizontal=True,
        key="direction_filter",
    )

    # ── WFO window sizes ──────────────────────────────────────────────────────
    st.markdown("**⏱️ Finestre Walk-Forward**")
    _wfo_mode = st.radio(
        "Tipo di finestra",
        options=["pct", "bars"],
        format_func=lambda x: "📊 % del dataset" if x == "pct" else "📏 Numero di periodi",
        horizontal=True,
        key="wfo_mode",
        help="pct: percentuale del dataset totale (funziona con qualsiasi timeframe); bars: numero fisso di periodi",
    )
    _wfo_env = {"WFO_MODE": _wfo_mode}
    if _wfo_mode == "pct":
        _wfo_is_pct  = st.slider(
            "IS % (In-Sample)", min_value=10, max_value=80, value=35, step=5,
            key="wfo_is_pct",
            help="Percentuale del dataset usata per l'ottimizzazione In-Sample",
        )
        _wfo_oos_pct = st.slider(
            "OOS % (Out-of-Sample)", min_value=5, max_value=40, value=10, step=5,
            key="wfo_oos_pct",
            help="Percentuale del dataset usata per la validazione Out-of-Sample",
        )
        if _wfo_is_pct + _wfo_oos_pct >= 100:
            st.warning("⚠️ IS% + OOS% deve essere inferiore a 100%.")
        else:
            st.caption(
                f"Fold stimati: ~{max(1, int((100 - _wfo_is_pct) / _wfo_oos_pct))} "
                f"· IS={_wfo_is_pct}% OOS={_wfo_oos_pct}%"
            )
        _wfo_env["WFO_IS_PCT"]  = str(_wfo_is_pct)
        _wfo_env["WFO_OOS_PCT"] = str(_wfo_oos_pct)
    else:
        _wfo_bar_cols = st.columns(2)
        _wfo_is_b  = _wfo_bar_cols[0].number_input(
            "IS (periodi)", min_value=10, max_value=500_000, value=5_000, step=500,
            key="wfo_is_bars",
            help="Numero di barre per la finestra In-Sample",
        )
        _wfo_oos_b = _wfo_bar_cols[1].number_input(
            "OOS (periodi)", min_value=5, max_value=100_000, value=1_000, step=200,
            key="wfo_oos_bars",
            help="Numero di barre per la finestra Out-of-Sample",
        )
        if _wfo_oos_b >= _wfo_is_b:
            st.warning("⚠️ OOS deve essere inferiore a IS.")
        _wfo_env["WFO_IS_BARS"]  = str(_wfo_is_b)
        _wfo_env["WFO_OOS_BARS"] = str(_wfo_oos_b)

    # ── Monte Carlo ───────────────────────────────────────────────────────────
    st.markdown("**🎲 Monte Carlo**")
    _mc_n_sims = st.select_slider(
        "Simulazioni bootstrap",
        options=[1_000, 2_000, 5_000, 10_000, 20_000, 50_000],
        value=5_000,
        key="mc_n_sims",
        help="Numero di simulazioni bootstrap. Valori alti aumentano la precisione ma rallentano l'esecuzione.",
        format_func=lambda v: f"{v:,}",
    )
    _mc_sim_mult = st.select_slider(
        "Periodo di simulazione",
        options=[0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
        value=1.0,
        key="mc_sim_mult",
        help="Moltiplicatore del numero di trade per percorso. 1× = stesso periodo del backtest; 2× = doppio; 0.5× = metà.",
        format_func=lambda v: f"{int(v * 100)}% dei trade" if v < 1.0 else ("= backtest" if v == 1.0 else f"{v:.0f}× trade"),
    )

    _env = {
        "STRATEGY_ASSET":    asset,
        "HOURLY_DAYS":       str(_tf_actual),
        "DIRECTION_FILTER":  _direction_filter,
        "MC_N_SIMS":         str(_mc_n_sims),
        "MC_SIM_MULTIPLIER": str(_mc_sim_mult),
        **_wfo_env,
    }

    def _do_download_module(tickers_list, skip_existing=False):
        """Load 01_data_download.py as module, inject timeframe, run download."""
        import importlib.util as _ilux
        _specx = _ilux.spec_from_file_location(
            "dl01x", os.path.join(BASE, "01_data_download.py"))
        _dlmx = _ilux.module_from_spec(_specx)
        _specx.loader.exec_module(_dlmx)
        _dlmx.HOURLY_DAYS  = _tf_actual
        _dlmx.HOURLY_START = (
            pd.Timestamp.today() - pd.Timedelta(days=_tf_actual)
        ).strftime("%Y-%m-%d")
        return _dlmx.download_all_assets(tickers_list, skip_existing=skip_existing)

    def _ensure_download():
        if not os.path.exists(_asset_csv):
            with st.spinner(f"⬇️ Download dati {asset}…"):
                try:
                    _r2 = _do_download_module([asset], skip_existing=False)
                    _r2_val = _r2.get(asset)
                    if _r2_val is not True:
                        st.error(f"Impossibile scaricare {asset}: {_r2_val or 'errore sconosciuto'}")
                        return False
                    st.cache_data.clear()
                except Exception as _de:
                    st.error(f"Errore download {asset}: {_de}")
                    return False
        return True

    # ── Step 1 ────────────────────────────────────────────────────────────────
    if st.button("📥 1. Download + Analisi Statistica", use_container_width=True,
                 help="Scarica dati OHLCV, calcola Hurst/ACF/GARCH/best hours e "
                      "pre-computa le feature (ATR, RSI, EMA, GARCH) in un unico step."):
        with st.spinner(f"📥 Download + analisi + feature {asset}…"):
            try:
                _do_download_module([asset], skip_existing=False)
                st.cache_data.clear()
                _run_script("02_analyze.py", extra_env=_env)
                _run_script("03_features.py", extra_env=_env)
                st.cache_data.clear()
                st.success(f"✅ Download, analisi e feature completati per **{asset}**. "
                           f"Esegui ora **🤖 2. Elabora Strategia**.")
            except subprocess.CalledProcessError as _e1:
                st.error(f"Analisi fallita:\n```\n{_e1.stderr.decode()[:400]}\n```")
            except Exception as _e1b:
                st.error(f"Errore: {_e1b}")

    # ── Step 1.5: Natural-language strategy input ─────────────────────────────
    with st.expander("✍️ Descrivi la tua strategia in linguaggio naturale (opzionale)", expanded=False):
        st.caption(
            "Scrivi la tua idea di strategia in italiano o inglese. "
            "Vibe-Trading la implementerà e ottimizzerà automaticamente per massimizzare le performance."
        )
        _nl_desc = st.text_area(
            "Descrizione strategia",
            placeholder=(
                "Esempio: Voglio fare trend following su BTC comprando quando il prezzo supera "
                "i massimi delle ultime 6 barre e l'EMA50 è sopra l'EMA200. "
                "Chiudo in profitto a 3× il rischio e taglio le perdite a 1.5× l'ATR."
            ),
            height=120,
            label_visibility="collapsed",
            key="nl_strategy_desc",
        )
        _nl_btn = st.button(
            "✨ Genera da Descrizione",
            use_container_width=True,
            disabled=not _nl_desc.strip(),
            help="Chiama Vibe-Trading passando la tua descrizione + analisi statistica BTC.",
        )

        if _nl_btn and _nl_desc.strip():
            if not _ant_key and not _or_key:
                st.warning("Inserisci almeno una chiave AI (Anthropic o OpenRouter) per generare la strategia.")
            elif _ensure_download():
                import importlib as _il0
                import agent_vibe as _av0;     _il0.reload(_av0)
                import agent_strategy as _ag0; _il0.reload(_ag0)

                with st.status("✨ Generazione strategia da descrizione naturale…", expanded=True) as _nl_status:
                    try:
                        st.write("📝 Descrizione ricevuta, costruisco il prompt ottimizzato…")
                        _nl_prompt = _av0.build_user_description_prompt(_nl_desc.strip(), asset)
                        st.write(f"✅ Prompt costruito ({len(_nl_prompt)} chars) — invio a Vibe-Trading…")

                        _cfg_nl, _code_nl, _report_nl, _engine_nl = _av0.run_vibe_agent(
                            asset=asset,
                            anthropic_key=_ant_key,
                            openrouter_key=_or_key,
                            openrouter_model=_or_model,
                            vibe_api_url=_vibe_url,
                            vibe_service_token=_vibe_token,
                            prompt_override=_nl_prompt,
                        )
                        _ag0.save_outputs(_cfg_nl, _code_nl, _report_nl)
                        st.write(f"✅ Strategia generata via **{_engine_nl}**")
                        st.write(
                            f"`{_cfg_nl.get('strategy_name','?')}` "
                            f"({_cfg_nl.get('strategy_type','?')}) | "
                            f"SL {_cfg_nl.get('sl_mult')}×ATR | "
                            f"TP {_cfg_nl.get('tp_mult')}×ATR"
                        )
                        if _cfg_nl.get("rationale"):
                            st.info(_cfg_nl["rationale"])

                        _nl_status.update(label="✅ Strategia salvata", state="complete", expanded=False)
                        st.success("✅ Strategia salvata. Premi **▶ 3. Analisi Completa** per eseguire backtest + WFO + Monte Carlo.")
                    except Exception as _nl_e:
                        _nl_status.update(label="❌ Generazione fallita", state="error")
                        st.error(f"Errore: {_nl_e}")

    # ── Step 1.6: Standard + custom strategy templates ───────────────────────
    with st.expander("🎯 Scegli una strategia da ottimizzare (opzionale)", expanded=False):
        import importlib as _il1b
        import agent_vibe as _av1b; _il1b.reload(_av1b)

        _all_strat_opts = _av1b.get_all_strategies_options()
        _n_custom = sum(1 for v in _all_strat_opts.values() if v["is_custom"])
        _caption_parts = ["Seleziona un modello classico da ottimizzare con Vibe-Trading."]
        if _n_custom:
            _caption_parts.append(f"Hai **{_n_custom}** strategi{'a' if _n_custom == 1 else 'e'} nel catalogo personale — vengono applicate direttamente senza rigenerare il codice.")
        st.caption(" ".join(_caption_parts))

        _sel_strat = st.selectbox(
            "Strategia",
            options=list(_all_strat_opts.keys()),
            format_func=lambda k: (
                f"⭐ {_all_strat_opts[k]['icon']}  {_all_strat_opts[k]['name']}  [personale]"
                if _all_strat_opts[k]["is_custom"]
                else f"{_all_strat_opts[k]['icon']}  {_all_strat_opts[k]['name']}"
            ),
            label_visibility="collapsed",
            key="std_strat_sel",
        )
        if _sel_strat:
            _sel_data = _all_strat_opts[_sel_strat]
            if _sel_data["is_custom"]:
                st.info(
                    f"**Strategia personale** — asset: `{_sel_data.get('asset','?')}` · "
                    f"salvata il {_sel_data.get('added_at','')[:10]}  \n"
                    f"{_sel_data.get('description','')}"
                )
            else:
                st.info(_sel_data["description"])

        _is_custom_sel = _sel_strat and _all_strat_opts[_sel_strat]["is_custom"]

        if _is_custom_sel:
            # Custom strategy: apply saved config+code directly
            if st.button(
                "✅ Applica strategia personale",
                use_container_width=True,
                help="Carica la configurazione e il codice salvati nel catalogo, poi esegui il backtest.",
            ):
                if _ensure_download():
                    import importlib as _il1d
                    import agent_strategy as _ag1d; _il1d.reload(_ag1d)
                    import agent_vibe as _av1d;     _il1d.reload(_av1d)

                    _cust_data = _av1d.get_all_strategies_options()[_sel_strat]
                    _cust_cfg  = _cust_data.get("config", {})
                    _cust_code = _cust_data.get("code", "")
                    _cust_name = _cust_data.get("name", "?")

                    with st.status(f"✅ Applicazione {_cust_name}…", expanded=True) as _cust_status:
                        try:
                            st.write(f"📋 Carico configurazione **{_cust_name}**…")
                            _cust_report = (
                                f"# Strategy Report — {asset}\n"
                                f"*Fonte: catalogo personale*\n\n"
                                f"**{_cust_cfg.get('strategy_name', _cust_name)}** "
                                f"({_cust_cfg.get('strategy_type', '—')})\n"
                                f"SL {_cust_cfg.get('sl_mult')}×ATR | TP {_cust_cfg.get('tp_mult')}×ATR | "
                                f"active_hours {_cust_cfg.get('active_hours')}\n\n"
                                f"---\n\n```python\n{_cust_code}\n```"
                            )
                            _ag1d.save_outputs(_cust_cfg, _cust_code, _cust_report)
                            st.write("✅ Config e codice caricati.")
                            st.write("📈 Eseguo backtest…")
                            _run_script("04_backtest.py", extra_env=_env)
                            st.cache_data.clear()
                            _cust_status.update(
                                label=f"✅ {_cust_name} applicata",
                                state="complete", expanded=False,
                            )
                            st.success("Strategia applicata e testata. Consulta i grafici nella pagina principale.")
                        except Exception as _cust_e:
                            _cust_status.update(label="❌ Applicazione fallita", state="error")
                            st.error(f"Errore: {_cust_e}")
        else:
            # Standard strategy: generate+optimise via Vibe-Trading
            _std_btn = st.button(
                "🎯 Ottimizza Strategia Standard",
                use_container_width=True,
                help="Vibe-Trading implementa e ottimizza la strategia selezionata per questo asset.",
            )

            if _std_btn and _sel_strat:
                if not _ant_key and not _or_key:
                    st.warning("Inserisci almeno una chiave AI (Anthropic o OpenRouter).")
                elif _ensure_download():
                    import importlib as _il1c
                    import agent_vibe as _av1c;     _il1c.reload(_av1c)
                    import agent_strategy as _ag1c; _il1c.reload(_ag1c)

                    _strat_label = _av1c.STANDARD_STRATEGIES[_sel_strat]["name"]
                    with st.status(f"🎯 Ottimizzazione {_strat_label}…", expanded=True) as _std_status:
                        try:
                            st.write(f"📐 Costruisco prompt per **{_strat_label}**…")
                            _std_prompt = _av1c.build_standard_strategy_prompt(_sel_strat, asset)
                            st.write(f"✅ Prompt pronto ({len(_std_prompt)} chars) — invio a Vibe-Trading…")

                            _cfg_std, _code_std, _report_std, _engine_std = _av1c.run_vibe_agent(
                                asset=asset,
                                anthropic_key=_ant_key,
                                openrouter_key=_or_key,
                                openrouter_model=_or_model,
                                vibe_api_url=_vibe_url,
                                vibe_service_token=_vibe_token,
                                prompt_override=_std_prompt,
                            )
                            _ag1c.save_outputs(_cfg_std, _code_std, _report_std)
                            st.write(f"✅ Strategia generata via **{_engine_std}**")
                            st.write(
                                f"`{_cfg_std.get('strategy_name','?')}` "
                                f"({_cfg_std.get('strategy_type','?')}) | "
                                f"SL {_cfg_std.get('sl_mult')}×ATR | "
                                f"TP {_cfg_std.get('tp_mult')}×ATR"
                            )
                            if _cfg_std.get("rationale"):
                                st.info(_cfg_std["rationale"])

                            st.write("📈 Eseguo backtest…")
                            _run_script("04_backtest.py", extra_env=_env)
                            st.cache_data.clear()

                            _std_status.update(
                                label=f"✅ {_strat_label} ottimizzata",
                                state="complete", expanded=False,
                            )
                            st.success("Strategia ottimizzata e testata. Consulta i grafici nella pagina principale.")
                        except Exception as _std_e:
                            _std_status.update(label="❌ Ottimizzazione fallita", state="error")
                            st.error(f"Errore: {_std_e}")

    # ── Step 2 ────────────────────────────────────────────────────────────────
    if st.button("🤖 2. Elabora Strategia", use_container_width=True,
                 help="Genera generate_signals_agent() via Vibe-Trading (Railway/CLI). "
                      "Richiede VIBE_TRADING_API_URL oppure vibe-trading-ai installato localmente."):
        if not _ant_key and not _or_key:
            st.warning("Inserisci almeno una chiave AI (Anthropic o OpenRouter) per l'adattamento codice.")
        elif _ensure_download():
            import importlib as _il
            import agent_vibe as _av;     _il.reload(_av)
            import agent_strategy as _ag; _il.reload(_ag)

            if _vibe_url:
                _vibe_label = "Vibe-Trading in esecuzione via Railway (~5-10 min)…"
                _vibe_mode  = "Railway"
            elif _av._is_vibe_installed():
                _vibe_label = "Vibe-Trading in esecuzione (CLI locale)…"
                _vibe_mode  = "CLI"
            else:
                _vibe_label = "Avvio generazione strategia…"
                _vibe_mode  = "—"

            with st.status(f"🤖 {_vibe_label}", expanded=True) as _status:
                try:
                    st.write(f"Asset: **{asset}**  |  Motore previsto: **{_vibe_mode}**")
                    _cfg_r, _code_r, _report_r, _engine_r = _av.run_vibe_agent(
                        asset=asset,
                        anthropic_key=_ant_key,
                        openrouter_key=_or_key,
                        openrouter_model=_or_model,
                        vibe_api_url=_vibe_url,
                        vibe_service_token=_vibe_token,
                    )
                    _ag.save_outputs(_cfg_r, _code_r, _report_r)
                    st.write(f"✅ Motore effettivo: **{_engine_r}**")
                    st.write(
                        f"`{_cfg_r.get('strategy_name','?')}` "
                        f"({_cfg_r.get('strategy_type','?')}) | "
                        f"SL {_cfg_r.get('sl_mult')}×ATR | "
                        f"TP {_cfg_r.get('tp_mult')}×ATR"
                    )
                    _status.update(
                        label=f"✅ Strategia generata — {_engine_r}",
                        state="complete", expanded=False,
                    )
                    st.success("✅ Strategia salvata. Premi **▶ 3. Analisi Completa** per eseguire backtest + WFO + Monte Carlo.")
                except Exception as _ae:
                    _status.update(label="❌ Generazione fallita", state="error")
                    st.error(f"Errore: {_ae}")

    # ── Step 3: Analisi Completa (Backtest + WFO + Monte Carlo) ──────────────────
    if st.button("▶ 3. Analisi Completa", use_container_width=True,
                 help="Backtest V1/V2/V4/V_Agent + Walk-Forward (4 finestre) + Monte Carlo. "
                      "Applica il filtro direzione selezionato sopra."):
        if _ensure_download():
            with st.status(
                f"▶ Analisi Completa — {asset} | {_direction_filter}",
                expanded=True,
            ) as _run_status:
                try:
                    st.write(f"📈 Backtest + Walk-Forward ({asset}, {_direction_filter})…")
                    _run_script("04_backtest.py", extra_env=_env)
                    st.cache_data.clear()
                    st.write("✅ Backtest + WFO completati.")

                    st.write("🎲 Monte Carlo (bootstrap + stress)…")
                    _run_script("05_montecarlo.py", extra_env=_env)
                    st.cache_data.clear()
                    st.write("✅ Monte Carlo completato.")

                    _run_status.update(
                        label="✅ Analisi Completa terminata — vedi le tab per i risultati",
                        state="complete", expanded=False,
                    )
                except subprocess.CalledProcessError as _re:
                    _run_status.update(label="❌ Analisi fallita", state="error")
                    st.error(f"Errore:\n```\n{_re.stderr.decode()[:400]}\n```")

    st.divider()

    # ── Step 4: Migliora strategia ────────────────────────────────────────────
    if st.button("🧠 4. Migliora Strategia", use_container_width=True,
                 help="Analizza trade IS/OOS, identifica debolezze e chiama Vibe-Trading "
                      "per generare una strategia migliorata con rendimento OOS positivo."):
        _trades_path = os.path.join(OUTPUT, "trades.csv")
        if not os.path.exists(_trades_path):
            st.warning("Esegui prima **▶ 3. Analisi Completa** per generare i dati dei trade.")
        else:
            import importlib as _il2
            import trade_analysis as _ta; _il2.reload(_ta)
            import agent_vibe as _av2;    _il2.reload(_av2)
            import agent_strategy as _ag2; _il2.reload(_ag2)

            with st.status("🧠 Analisi debolezze + generazione strategia migliorata…",
                           expanded=True) as _imp_status:
                try:
                    st.write("📊 Analisi trade LONG/SHORT per fold IS/OOS…")
                    _imp_prompt = _ta.build_improvement_prompt(asset)
                    st.write(f"✅ Prompt costruito ({len(_imp_prompt)} chars)")

                    st.write("🤖 Chiamo Vibe-Trading per la strategia migliorata…")
                    _cfg_imp, _code_imp, _report_imp, _engine_imp = _av2.run_vibe_agent(
                        asset=asset,
                        anthropic_key=_ant_key,
                        openrouter_key=_or_key,
                        openrouter_model=_or_model,
                        vibe_api_url=_vibe_url,
                        vibe_service_token=_vibe_token,
                        prompt_override=_imp_prompt,
                    )
                    _ag2.save_outputs(_cfg_imp, _code_imp, _report_imp)
                    st.write(f"✅ Strategia migliorata: **{_engine_imp}**")
                    st.write(
                        f"`{_cfg_imp.get('strategy_name','?')}` — "
                        f"SL {_cfg_imp.get('sl_mult')}×ATR | "
                        f"TP {_cfg_imp.get('tp_mult')}×ATR | "
                        f"ore {_cfg_imp.get('active_hours')}"
                    )
                    st.write(f"▶ Analisi Completa con nuova strategia ({_direction_filter})…")
                    _run_script("04_backtest.py", extra_env=_env)
                    st.cache_data.clear()
                    _run_script("05_montecarlo.py", extra_env=_env)
                    st.cache_data.clear()
                    _imp_status.update(
                        label="✅ Strategia migliorata — backtest + MC completati",
                        state="complete", expanded=False,
                    )
                except Exception as _ie:
                    _imp_status.update(label="❌ Miglioramento fallito", state="error")
                    st.error(f"Errore: {_ie}")

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
    path_daily  = os.path.join(OUTPUT, f"{fname}_daily.csv")
    path_hourly = os.path.join(OUTPUT, f"{fname}_hourly.csv")
    if os.path.exists(path_daily):
        df = pd.read_csv(path_daily, index_col=0, parse_dates=True)
    elif os.path.exists(path_hourly):
        df_h = pd.read_csv(path_hourly, index_col=0, parse_dates=True)
        df = df_h.resample("1D").agg({
            "Open": "first", "High": "max",
            "Low": "min",    "Close": "last",
            "Volume": "sum",
        }).dropna()
    else:
        raise FileNotFoundError(f"No data found for {sym}: {path_daily}")
    df.index.name = "Date"
    return df

@st.cache_data
def load_ohlcv_hourly(sym: str) -> pd.DataFrame:
    path = os.path.join(OUTPUT, f"{ticker_to_fname(sym)}_hourly.csv")
    df   = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index.name = "Date"
    return df

_RESAMPLE_AGG = {"Open": "first", "High": "max", "Low": "min",
                 "Close": "last", "Volume": "sum"}

@st.cache_data
def load_ohlcv_interval(sym: str, interval: str) -> pd.DataFrame:
    """Load OHLCV at any supported interval.
    1h   → hourly CSV
    4h   → resample from hourly
    1d   → daily CSV (or resample from hourly)
    1m/15m/30m → dedicated CSV (must be downloaded first)
    """
    fname = ticker_to_fname(sym)
    if interval == "1h":
        return load_ohlcv_hourly(sym)
    if interval == "4h":
        df = load_ohlcv_hourly(sym)
        return df.resample("4h").agg(_RESAMPLE_AGG).dropna()
    if interval == "1d":
        return load_ohlcv_daily(sym)
    # Fine-grain: 1m, 15m, 30m
    path = os.path.join(OUTPUT, f"{fname}_{interval}.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Dati {interval} non trovati per {sym}: {path}")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index.name = "Date"
    return df

def download_fine_grain(sym: str, interval: str, max_days: int) -> str | bool:
    """Download fine-grain data and save as {fname}_{interval}.csv.
    Returns True on success or an error string.
    """
    import yfinance as yf
    fname = ticker_to_fname(sym)
    fpath = os.path.join(OUTPUT, f"{fname}_{interval}.csv")
    try:
        period_str = f"{max_days}d"
        df = yf.download(sym, period=period_str, interval=interval,
                         auto_adjust=True, progress=False)
        if df.empty:
            return f"Nessun dato ricevuto per {sym} ({interval})"
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df.index.name = "Date"
        df.dropna(inplace=True)
        df.to_csv(fpath)
        return True
    except Exception as exc:
        return str(exc)

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

def _strategy_asset() -> str:
    """Return the asset the last strategy run was calculated on."""
    import json as _json
    _meta = os.path.join(OUTPUT, "strategy_meta.json")
    try:
        with open(_meta) as _f:
            return _json.load(_f).get("asset", "BTC-USD")
    except Exception:
        return "BTC-USD"

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

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📊 Prezzi & Rendimenti",
    "📈 Strategia V5",
    "🔄 Walk-Forward",
    "🎲 Monte Carlo",
    "🌐 Multi-Asset",
    "🤖 Agent Strategy",
    "🔍 Analisi Trade",
    "⚙️ Parametri Strategia",
])


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — Prezzi & Rendimenti
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    from scipy import stats as scipy_stats
    import json as _t1json

    a_color = ASSET_COLORS.get(asset, C_LINE)
    _t1_report_path = os.path.join(OUTPUT, "analysis_report.json")

    # ── Action bar ────────────────────────────────────────────────────────────
    if not os.path.exists(_asset_csv):
        st.info(f"Dati per **{_CATALOG_FLAT.get(asset, asset)} ({asset})** non ancora scaricati.")
        _t1c1, _t1c2 = st.columns(2)
        with _t1c1:
            if st.button("⬇️ Scarica Dati", use_container_width=True, key="t1_download"):
                with st.spinner(f"⬇️ Download {asset} ({_tf_actual} gg)…"):
                    try:
                        _t1r = _do_download_module([asset], skip_existing=False)
                        _t1_val = _t1r.get(asset)
                        if _t1_val is True:
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(f"Impossibile scaricare {asset}: {_t1_val or 'errore sconosciuto'}")
                    except Exception as _t1e:
                        st.error(f"Errore download: {_t1e}")
        with _t1c2:
            if st.button("📊 Esegui Analisi", use_container_width=True, key="t1_analyze_nodata"):
                st.warning("Scarica prima i dati con **⬇️ Scarica Dati**.")
    else:
        if st.button("📊 Esegui Analisi", use_container_width=True, key="t1_analyze"):
            with st.spinner(f"📊 Analisi statistica {asset}…"):
                try:
                    _run_script("02_analyze.py", extra_env=_env)
                    st.cache_data.clear()
                    st.rerun()
                except subprocess.CalledProcessError as _t1ae:
                    st.error(f"Analisi fallita:\n```\n{_t1ae.stderr.decode()[:400]}\n```")

    # ── Price charts ──────────────────────────────────────────────────────────
    # Warn + auto-cap when display window exceeds interval's data limit
    if _interval_max_days is not None and _chart_days is not None and _chart_days > _interval_max_days:
        st.warning(
            f"⚠️ L'intervallo **{chart_interval_label.strip()}** supporta al massimo "
            f"**{_interval_max_days} giorni** di storia. "
            f"Il timeframe verrà ridotto da {_chart_days} a {_interval_max_days} giorni."
        )
        _effective_start = pd.Timestamp.today() - pd.Timedelta(days=_interval_max_days)
    else:
        _effective_start = chart_start

    # Fine-grain intervals need a separate download
    _fine_grain = chart_interval in ("1m", "15m", "30m")
    _fine_path  = os.path.join(OUTPUT, f"{ticker_to_fname(asset)}_{chart_interval}.csv")

    if _fine_grain and not os.path.exists(_fine_path):
        st.info(
            f"I dati **{chart_interval_label.strip()}** per {asset} non sono ancora stati scaricati."
        )
        if st.button(f"⬇️ Scarica dati {chart_interval}", key="t1_dl_fine"):
            with st.spinner(f"Download {chart_interval} {asset} (max {_interval_max_days} gg)…"):
                _fg_res = download_fine_grain(asset, chart_interval, _interval_max_days)
                if _fg_res is True:
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Download fallito: {_fg_res}")

    _chart_data = None
    if not _fine_grain or os.path.exists(_fine_path):
        try:
            _chart_data = load_ohlcv_interval(asset, chart_interval)
        except FileNotFoundError:
            _chart_data = None

    if _chart_data is not None:
        d = _chart_data[_chart_data.index >= _effective_start] if _effective_start is not None else _chart_data
        if d.empty:
            st.warning("Nessun dato per il timeframe selezionato. Prova 'Max disponibile' o scarica più dati.")
        else:
            _title_suffix = f" — {chart_interval_label.strip()}"
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
                              title=f"{asset}/USD — Candlestick{_title_suffix}")
            fig.update_yaxes(title_text="Prezzo (USD)", row=1, col=1)
            fig.update_yaxes(title_text="Volume",       row=2, col=1)
            st.plotly_chart(fig, use_container_width=True)

            # ── Log-returns + Distribuzione ───────────────────────────────────
            log_ret = np.log(d["Close"] / d["Close"].shift(1)).dropna()
            # Annualisation factor depends on interval
            _bars_per_year = {"1m": 525_600, "15m": 35_040, "30m": 17_520,
                              "1h": 8_760,   "4h": 2_190,   "1d": 365}
            _ann_factor = _bars_per_year.get(chart_interval, 8_760)
            col_l, col_r = st.columns(2)
            with col_l:
                fig2 = go.Figure(go.Scatter(
                    x=log_ret.index, y=log_ret.values,
                    mode="lines", line=dict(color=a_color, width=1),
                    name="Log-return",
                ))
                fig2.update_layout(height=300, template="plotly_dark",
                                    title=f"Log-returns ({chart_interval})",
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

            # ── Statistiche base ──────────────────────────────────────────────
            kurt    = float(scipy_stats.kurtosis(log_ret, fisher=True))
            skew_v  = float(scipy_stats.skew(log_ret))
            _, jb_p = scipy_stats.jarque_bera(log_ret)
            ann_vol = log_ret.std() * np.sqrt(_ann_factor) * 100
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Volatilità annua",  f"{ann_vol:.1f}%")
            c2.metric("Curtosi (excess)",  f"{kurt:.2f}")
            c3.metric("Skewness",          f"{skew_v:.3f}")
            c4.metric("Jarque-Bera p-val", f"{jb_p:.4f}")

            # ── Pattern intraday (sempre su dati orari, indipendente dall'intervallo)
            st.subheader(f"Pattern intraday {asset} (dati orari)")
            try:
                hourly = load_ohlcv_hourly(asset)
                if _effective_start is not None:
                    hourly = hourly[hourly.index >= _effective_start]
                hourly["log_ret"] = np.log(hourly["Close"] / hourly["Close"].shift(1))
                by_hour = hourly.groupby(hourly.index.hour)["log_ret"].mean() * 1e4
                _tf_note = f" · ultimi {chart_tf_label}" if chart_start is not None else ""
                fig4 = go.Figure(go.Bar(
                    x=by_hour.index, y=by_hour.values,
                    marker_color=[C_UP if v >= 0 else C_DOWN for v in by_hour.values],
                ))
                fig4.update_layout(height=280, template="plotly_dark",
                                    title=f"Rendimento medio per ora del giorno (UTC) — {asset}{_tf_note}",
                                    xaxis_title="Ora (UTC)",
                                    yaxis_title="Rendimento medio (bp)",
                                    margin=dict(l=0, r=0, t=40, b=0))
                st.plotly_chart(fig4, use_container_width=True)
            except Exception:
                st.info("Dati orari non disponibili.")

    # ── Analisi statistica (da analysis_report.json) ──────────────────────────
    if os.path.exists(_t1_report_path):
        try:
            with open(_t1_report_path) as _f:
                _rpt = _t1json.load(_f)
            _rpt_asset = _rpt.get("asset", "?")
        except Exception:
            _rpt = None

        if _rpt and _rpt_asset == asset:
            st.divider()
            st.subheader(f"📊 Analisi statistica — {_CATALOG_FLAT.get(asset, asset)}")
            _s = _rpt["statistics"]
            _g = _rpt["garch"]
            _v4 = _rpt["v4_baseline"]

            # Regime + Hurst
            _regime_color = {"trend_following": "success",
                             "mean_reversion": "info",
                             "breakout": "warning"}.get(_s["regime"], "info")
            getattr(st, _regime_color)(
                f"**Regime:** {_s['regime'].replace('_', ' ').title()} "
                f"(Hurst = {_s['hurst_exponent']:.4f}) — {_s['regime_description']}"
            )

            # Key stats
            _sa1, _sa2, _sa3, _sa4 = st.columns(4)
            _sa1.metric("Hurst exponent",  f"{_s['hurst_exponent']:.4f}")
            _sa2.metric("ACF lag-1",        f"{_s['acf_lag1']:.4f}",
                        help="Positivo = momentum, Negativo = mean-reversion")
            _sa3.metric("Kurtosis (exc)",   f"{_s['excess_kurtosis']:.2f}")
            _sa4.metric("Vol annualizzata", f"{_s['ann_vol_pct']:.1f}%")

            # GARCH + best hours
            _sg1, _sg2 = st.columns(2)
            with _sg1:
                st.caption("**GARCH(1,1)**")
                _gc1, _gc2, _gc3 = st.columns(3)
                _gc1.metric("alpha (shock)", f"{_g['alpha']:.4f}")
                _gc2.metric("beta (persist)", f"{_g['beta']:.4f}")
                _gc3.metric("α+β", f"{_g['persistence']:.4f}",
                            delta="stazionario" if _g['persistence'] < 1 else "non stazionario",
                            delta_color="normal" if _g['persistence'] < 1 else "inverse")
            with _sg2:
                st.caption("**Finestre orarie migliori/peggiori (UTC)**")
                st.write(f"Migliori: `{_s['best_hours_utc']}`")
                st.write(f"Peggiori: `{_s['worst_hours_utc']}`")

            # V4 baseline — prefer enhanced_strategy_comparison.csv (same as Tab 2)
            _cmp_path = os.path.join(OUTPUT, "enhanced_strategy_comparison.csv")
            _v4_src   = None
            if os.path.exists(_cmp_path):
                try:
                    _cmp_df = pd.read_csv(_cmp_path)
                    _v4_row = _cmp_df[_cmp_df["version"] == "V4 +GARCH+Costi"]
                    if not _v4_row.empty:
                        _r = _v4_row.iloc[0]
                        _v4_src = {
                            "cagr_pct":         _r["cagr_pct"],
                            "sharpe_ratio":      _r["sharpe_ratio"],
                            "max_drawdown_pct":  _r["max_drawdown_pct"],
                            "win_rate_pct":      _r["win_rate_pct"],
                            "n_trades":          int(_r["n_trades"]),
                        }
                except Exception:
                    pass
            if _v4_src is None:
                _v4_src = _v4   # fallback to analysis_report.json
            st.caption("**Baseline V4** (ATR breakout + GARCH, commissioni 0.04%)")
            _vb1, _vb2, _vb3, _vb4, _vb5 = st.columns(5)
            _vb1.metric("CAGR",         f"{_v4_src['cagr_pct']:.1f}%")
            _vb2.metric("Sharpe",       f"{_v4_src['sharpe_ratio']:.2f}")
            _vb3.metric("Max DD",       f"{_v4_src['max_drawdown_pct']:.1f}%")
            _vb4.metric("Win Rate",     f"{_v4_src['win_rate_pct']:.1f}%")
            _vb5.metric("N. Trade",     str(_v4_src['n_trades']))
        elif _rpt and _rpt_asset != asset:
            st.caption(
                f"📊 L'ultima analisi disponibile è per **{_rpt_asset}** (non {asset}). "
                "Clicca **📊 Esegui Analisi** per aggiornare."
            )


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — Strategia V5
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    _strat_asset = _strategy_asset()
    _strat_name  = _CATALOG_FLAT.get(_strat_asset, _strat_asset)
    if _strat_asset != asset:
        st.info(
            f"Il backtest è calcolato su **{_strat_name}** ({_strat_asset}). "
            f"Per calcolarlo su **{_CATALOG_FLAT.get(asset, asset)}** ({asset}), "
            "esegui **Step 1** (Download + Analisi) e **Step 2** (Elabora Strategia) nella sidebar."
        )
    elif _strat_asset != "BTC-USD":
        st.success(f"Backtest calcolato su **{_strat_name}** ({_strat_asset}).")
    try:
        trades = load_trades()
        cmp    = load_strategy_comparison()
        optim  = load_optimization()

        # Apply chart timeframe filter
        _t2_note = f" · ultimi {chart_tf_label}" if chart_start is not None else ""
        trades_view = (
            trades[trades["exit_time"] >= chart_start]
            if chart_start is not None else trades
        )

        # ── Equity curve + Drawdown ───────────────────────────────────────────
        eq_full = equity_curve(trades)
        dd_full = drawdown_series(eq_full)
        eq = eq_full[eq_full.index >= chart_start] if chart_start is not None else eq_full
        dd = dd_full[dd_full.index >= chart_start] if chart_start is not None else dd_full

        fig_eq = make_subplots(rows=2, cols=1, shared_xaxes=True,
                               row_heights=[0.7, 0.3], vertical_spacing=0.04)
        fig_eq.add_trace(go.Scatter(x=eq.index, y=eq.values, mode="lines",
                                    line=dict(color=C_UP, width=2),
                                    fill="tozeroy", fillcolor="rgba(38,166,154,0.1)",
                                    name="Equity"), row=1, col=1)
        _eq_start = float(eq.iloc[0]) if len(eq) > 0 else 10_000
        fig_eq.add_hline(y=_eq_start, line_dash="dash",
                         line_color="gray", row=1, col=1)
        fig_eq.add_trace(go.Scatter(x=dd.index, y=dd.values, mode="lines",
                                    line=dict(color=C_DOWN, width=1.5),
                                    fill="tozeroy", fillcolor="rgba(239,83,80,0.2)",
                                    name="Drawdown %"), row=2, col=1)
        fig_eq.update_layout(height=480, template="plotly_dark",
                              title=f"Equity curve & Drawdown — Strategia V5{_t2_note}",
                              margin=dict(l=0, r=0, t=40, b=0))
        fig_eq.update_yaxes(title_text="Capitale (USDT)", row=1, col=1)
        fig_eq.update_yaxes(title_text="Drawdown %", row=2, col=1)
        st.plotly_chart(fig_eq, use_container_width=True)

        # ── Trade scatter: P&L nel tempo ──────────────────────────────────────
        col_l, col_r = st.columns([2, 1])

        with col_l:
            fig_tr = go.Figure()
            wins  = trades_view[trades_view["pnl"] > 0]
            loss  = trades_view[trades_view["pnl"] <= 0]
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
                                 title=f"P&L per trade{_t2_note}",
                                 margin=dict(l=0, r=0, t=40, b=0),
                                 yaxis_title="P&L (USDT)")
            st.plotly_chart(fig_tr, use_container_width=True)

        with col_r:
            pnl_arr = trades_view["pnl"].values
            wins_n  = (pnl_arr > 0).sum()
            loss_n  = (pnl_arr <= 0).sum()
            fig_pie = go.Figure(go.Pie(
                labels=["Win", "Loss"],
                values=[wins_n, loss_n],
                marker_colors=[C_UP, C_DOWN],
                hole=0.5,
            ))
            fig_pie.update_layout(height=300, template="plotly_dark",
                                  title=f"Win / Loss ratio{_t2_note}",
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
                                  values="sharpe_ratio", aggfunc="mean")
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
    _strat_asset3 = _strategy_asset()
    _strat_name3  = _CATALOG_FLAT.get(_strat_asset3, _strat_asset3)
    if _strat_asset3 != asset:
        st.info(
            f"La Walk-Forward è calcolata su **{_strat_name3}** ({_strat_asset3}). "
            f"Per calcolarla su **{_CATALOG_FLAT.get(asset, asset)}** ({asset}), "
            "esegui **Step 1** e **Step 2** nella sidebar."
        )
    elif _strat_asset3 != "BTC-USD":
        st.success(f"Walk-Forward calcolata su **{_strat_name3}** ({_strat_asset3}).")
    try:
        import json as _t3json

        # ── Show active WFO config ────────────────────────────────────────────
        _wfo_meta_path = os.path.join(OUTPUT, "wfo_meta.json")
        _wm = {}
        if os.path.exists(_wfo_meta_path):
            try:
                with open(_wfo_meta_path) as _wf:
                    _wm = _t3json.load(_wf)
            except Exception:
                pass
        _wfo_configs_run = _wm.get("configs", [])
        _wfo_mode_val = _wm.get("mode", "")
        _mode_label = "📊 % del dataset" if _wfo_mode_val == "pct" else ("📏 Numero di periodi" if _wfo_mode_val == "bars" else "—")
        if _wfo_mode_val == "pct":
            _window_desc = f"IS={_wm.get('is_pct', '?')}% · OOS={_wm.get('oos_pct', '?')}%"
        elif _wfo_mode_val == "bars":
            _window_desc = f"IS={_wm.get('is_bars', '?')} barre · OOS={_wm.get('oos_bars', '?')} barre"
        else:
            _window_desc = "—"
        if _wfo_mode_val:
            _t3k1, _t3k2, _t3k3 = st.columns(3)
            _t3k1.metric("Modalità finestre", _mode_label)
            _t3k2.metric("Configurazione", _wm.get("label", "—"))
            _t3k3.metric("Fold eseguiti", _wm.get("n_folds", "—"))
            st.caption(
                f"Dataset: **{_wm.get('n_total', 0):,} periodi** · {_window_desc} "
                f"· Per modificare usa i controlli nella sidebar e riesegui **▶ 3. Analisi Completa**."
            )

        wfo_all = load_wfo()

        # ── Window config selector (when multiple configs in CSV) ─────────────
        if "window_config" in wfo_all.columns:
            _avail_configs = wfo_all["window_config"].unique().tolist()
            if len(_avail_configs) > 1:
                _sel_wfo_cfg = st.selectbox(
                    "Configurazione finestre",
                    options=_avail_configs,
                    index=len(_avail_configs) - 1,  # default: last (IS=8m OOS=2m)
                    key="wfo_cfg_sel",
                )
                wfo = wfo_all[wfo_all["window_config"] == _sel_wfo_cfg].copy()
                st.caption(f"Mostrando: **{_sel_wfo_cfg}** ({len(wfo)} fold)")
            else:
                wfo = wfo_all.copy()
        else:
            wfo = wfo_all.copy()

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
                     "oos_trades", "oos_n_trades",
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
    _strat_asset4 = _strategy_asset()
    _strat_name4  = _CATALOG_FLAT.get(_strat_asset4, _strat_asset4)
    if _strat_asset4 != asset:
        st.info(
            f"Il Monte Carlo è calcolato su **{_strat_name4}** ({_strat_asset4}). "
            f"Per calcolarlo su **{_CATALOG_FLAT.get(asset, asset)}** ({asset}), "
            "esegui **Step 1** e **Step 2** nella sidebar."
        )
    elif _strat_asset4 != "BTC-USD":
        st.success(f"Monte Carlo calcolato su **{_strat_name4}** ({_strat_asset4}).")
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
                y=stress["total_return_pct"],
                marker_color=[C_UP if v >= 0 else C_DOWN for v in stress["total_return_pct"]],
                text=[f"{v:.1f}%" for v in stress["total_return_pct"]],
                textposition="outside",
            ))
            fig_st.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_st.update_layout(
                height=320, template="plotly_dark",
                title="Stress test — Return totale per scenario",
                yaxis_title="Return totale %",
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
            "Nessuna strategia generata. Nella sidebar esegui **Step 1** (Download + Analisi) "
            "poi **Step 2** (Elabora Strategia), oppure lancia `run_all.py` da terminale."
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
                        st.info("Esegui **Step 2 (Elabora Strategia)** nella sidebar per calcolare il backtest V_Agent.")
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

            st.divider()

            # ── Add to custom catalogue ───────────────────────────────────────
            st.subheader("💾 Aggiungi al catalogo strategie")
            st.caption(
                "Salva questa strategia nel catalogo personale per poterla riapplicare "
                "in futuro senza doverla rigenerare con Vibe-Trading."
            )
            import importlib as _t6il
            import agent_vibe as _t6av; _t6il.reload(_t6av)

            with st.form("t6_add_catalogue"):
                _cat_name = st.text_input(
                    "Nome strategia",
                    value=_cfg.get("strategy_name", ""),
                    max_chars=80,
                )
                _cat_col1, _cat_col2 = st.columns([1, 5])
                _cat_icon = _cat_col1.text_input("Icona", value="⭐", max_chars=2)
                _cat_col2.text_input(
                    "Tipo", value=_cfg.get("strategy_type", ""), disabled=True
                )
                _cat_desc = st.text_area(
                    "Descrizione (mostrata nel catalogo)",
                    value=_cfg.get("rationale", ""),
                    height=80,
                )
                _cat_submit = st.form_submit_button(
                    "💾 Salva nel catalogo", use_container_width=True, type="primary"
                )
                if _cat_submit:
                    if not _cat_name.strip():
                        st.error("Il nome è obbligatorio.")
                    else:
                        _cat_code_content = (
                            open(_code_path, encoding="utf-8").read()
                            if os.path.exists(_code_path) else ""
                        )
                        _cat_slug = (
                            _cat_name.strip().lower()
                            .replace(" ", "_")
                            .replace("-", "_")
                            .replace("/", "_")
                        )
                        _cat_slug = "".join(c for c in _cat_slug if c.isalnum() or c == "_")
                        _cat_entry = {
                            "key":         _cat_slug,
                            "name":        _cat_name.strip(),
                            "icon":        _cat_icon.strip() or "⭐",
                            "description": _cat_desc.strip(),
                            "added_at":    __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                            "asset":       _cfg.get("asset", asset),
                            "config":      dict(_cfg),
                            "code":        _cat_code_content,
                        }
                        _t6av.add_to_catalogue(_cat_entry)
                        st.success(
                            f"✅ **{_cat_name.strip()}** salvata nel catalogo! "
                            "Troverai questa strategia nel selettore 'Scegli una strategia' nella sidebar."
                        )

            # ── Catalogue management ──────────────────────────────────────────
            _t6_custom = _t6av.load_custom_strategies()
            if _t6_custom:
                with st.expander(f"📋 Catalogo personale ({len(_t6_custom)} strategie)", expanded=True):
                    for _t6_entry in _t6_custom:
                        _t6c1, _t6c2 = st.columns([6, 1])
                        _t6c1.markdown(
                            f"**{_t6_entry.get('icon','⭐')} {_t6_entry.get('name','?')}**  "
                            f"`{_t6_entry.get('asset','?')}` · "
                            f"{_t6_entry.get('added_at','')[:10]}  \n"
                            f"{_t6_entry.get('description','')[:120]}"
                        )
                        if _t6c2.button("🗑️", key=f"del_{_t6_entry.get('key')}", help="Rimuovi dal catalogo"):
                            _t6av.delete_from_catalogue(_t6_entry.get("key"))
                            st.rerun()

        except Exception as _e:
            st.error(f"Errore lettura output agent: {_e}")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 7 — Analisi Trade
# ══════════════════════════════════════════════════════════════════════════════

with tab7:
    import json as _t7json
    import importlib as _t7il

    st.header("🔍 Analisi Trade — LONG vs SHORT per fold IS/OOS")
    st.markdown(
        "Analisi dettagliata dei trade eseguiti: performance LONG vs SHORT, "
        "per ora UTC, per regime GARCH e per fold walk-forward (IS vs OOS). "
        "Identifica le debolezze della strategia attuale e usa il bottone "
        "**🧠 5. Migliora Strategia** nella sidebar per generare una versione migliorata."
    )

    _trades_csv = os.path.join(OUTPUT, "trades.csv")
    _wfo_csv    = os.path.join(OUTPUT, "wfo_IS8m_OOS2m.csv")

    if not os.path.exists(_trades_csv):
        st.info(
            "Nessun dato di trade disponibile. "
            "Esegui **📈 3. Backtest + Walk-Forward** dalla sidebar."
        )
    else:
        try:
            import trade_analysis as _ta7; _t7il.reload(_ta7)

            _t7_trades = _ta7.load_trades(asset)
            _t7_wfo    = _ta7.load_wfo("IS8m_OOS2m")

            if _t7_trades.empty:
                st.warning("Il file trades.csv è vuoto.")
            else:
                # ── KPI row ───────────────────────────────────────────────────
                _dir_df  = _ta7.direction_stats(_t7_trades)
                _all_row = _dir_df[_dir_df["Direzione"] == "ALL"]
                _lng_row = _dir_df[_dir_df["Direzione"] == "LONG"]
                _sht_row = _dir_df[_dir_df["Direzione"] == "SHORT"]

                def _v(row_df, col):
                    return row_df.iloc[0][col] if not row_df.empty else "—"

                _k1, _k2, _k3, _k4, _k5, _k6 = st.columns(6)
                _k1.metric("Trade totali",  _v(_all_row, "N trade"))
                _k2.metric("Win rate ALL",  f"{_v(_all_row, 'Win rate %')}%")
                _k3.metric("Profit Factor", _v(_all_row, "Profit Factor"))
                _k4.metric("Win% LONG",     f"{_v(_lng_row, 'Win rate %')}%",
                           delta=f"PF {_v(_lng_row,'Profit Factor')}")
                _k5.metric("Win% SHORT",    f"{_v(_sht_row, 'Win rate %')}%",
                           delta=f"PF {_v(_sht_row,'Profit Factor')}")
                _k6.metric("SL hit%",       f"{_v(_all_row, 'SL hit %')}%")

                st.divider()

                # ── Debolezze identificate ────────────────────────────────────
                _issues = _ta7.identify_weaknesses(_t7_trades, _t7_wfo)
                _issue_color = "🔴" if len(_issues) > 1 else "🟢"
                with st.expander(f"{_issue_color} Debolezze identificate ({len(_issues)})", expanded=True):
                    for _iss in _issues:
                        st.markdown(f"- {_iss.strip()}")

                st.divider()

                # ── Direction comparison ──────────────────────────────────────
                st.subheader("📊 LONG vs SHORT — confronto completo")
                _t7c1, _t7c2 = st.columns([1, 1])
                with _t7c1:
                    st.dataframe(_dir_df.set_index("Direzione"), use_container_width=True)

                with _t7c2:
                    # Bar chart: Win rate + PF by direction
                    _dir_plot = _dir_df[_dir_df["Direzione"] != "ALL"]
                    _fig_dir = go.Figure()
                    _fig_dir.add_bar(
                        x=_dir_plot["Direzione"], y=_dir_plot["Win rate %"],
                        name="Win rate %", marker_color=["#26a69a", "#ef5350"],
                        yaxis="y",
                    )
                    _fig_dir.add_bar(
                        x=_dir_plot["Direzione"], y=_dir_plot["Profit Factor"],
                        name="Profit Factor", marker_color=["#80cbc4", "#ef9a9a"],
                        yaxis="y2",
                    )
                    _fig_dir.update_layout(
                        template="plotly_dark", height=280, barmode="group",
                        margin=dict(l=0, r=0, t=30, b=0),
                        yaxis=dict(title="Win rate %"),
                        yaxis2=dict(title="Profit Factor", overlaying="y", side="right"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    )
                    st.plotly_chart(_fig_dir, use_container_width=True)

                # P&L distribution LONG vs SHORT
                _fig_pnl = go.Figure()
                for _dir, _col in [("LONG", "#26a69a"), ("SHORT", "#ef5350")]:
                    _sub = _t7_trades[_t7_trades["direction"] == _dir]["pnl_pct"] * 100
                    _fig_pnl.add_trace(go.Histogram(
                        x=_sub, name=_dir, marker_color=_col,
                        opacity=0.7, nbinsx=40,
                    ))
                _fig_pnl.update_layout(
                    barmode="overlay", template="plotly_dark", height=260,
                    margin=dict(l=0, r=0, t=30, b=0),
                    title="Distribuzione P&L % per direzione",
                    xaxis_title="P&L %", yaxis_title="N trade",
                )
                st.plotly_chart(_fig_pnl, use_container_width=True)

                st.divider()

                # ── Fold IS/OOS ───────────────────────────────────────────────
                st.subheader("🔄 Trade per fold OOS — LONG vs SHORT")
                _fold_df = _ta7.fold_direction_stats(_t7_trades, _t7_wfo)

                if not _fold_df.empty:
                    # Summary table (only ALL direction per fold)
                    _fold_all = _fold_df[_fold_df["Direzione"] == "ALL"].copy()
                    st.markdown("**Riepilogo fold OOS (tutte le direzioni)**")
                    st.dataframe(
                        _fold_all.drop(columns=["Direzione"]).set_index("Fold"),
                        use_container_width=True,
                    )

                    # Grouped bar: LONG vs SHORT win rate per fold
                    _fold_dir = _fold_df[_fold_df["Direzione"] != "ALL"]
                    if not _fold_dir.empty:
                        _fig_fold = go.Figure()
                        for _fd, _fc in [("LONG", "#26a69a"), ("SHORT", "#ef5350")]:
                            _sub_fd = _fold_dir[_fold_dir["Direzione"] == _fd]
                            _fig_fold.add_bar(
                                x=_sub_fd["Fold"].astype(str) + " " + _sub_fd["Periodo OOS"].astype(str),
                                y=_sub_fd["Win rate %"],
                                name=f"{_fd} Win%", marker_color=_fc,
                            )
                        _fig_fold.update_layout(
                            barmode="group", template="plotly_dark", height=320,
                            margin=dict(l=0, r=0, t=40, b=80),
                            title="Win rate % LONG vs SHORT per fold OOS",
                            xaxis_tickangle=-35,
                        )
                        st.plotly_chart(_fig_fold, use_container_width=True)

                    # OOS Sharpe per fold
                    if not _fold_all.empty and "OOS Sharpe" in _fold_all.columns:
                        _fig_sharpe = go.Figure()
                        _sharpe_colors = [
                            "#26a69a" if v >= 0 else "#ef5350"
                            for v in _fold_all["OOS Sharpe"].fillna(0)
                        ]
                        _fig_sharpe.add_bar(
                            x=_fold_all["Fold"].astype(str) + " " + _fold_all["Periodo OOS"].astype(str),
                            y=_fold_all["OOS Sharpe"],
                            marker_color=_sharpe_colors, name="OOS Sharpe",
                        )
                        _fig_sharpe.add_hline(y=0, line_dash="dash",
                                              line_color="white", opacity=0.5)
                        _fig_sharpe.add_hline(y=0.5, line_dash="dot",
                                              line_color="#ffeb3b", opacity=0.7,
                                              annotation_text="Target 0.5")
                        _fig_sharpe.update_layout(
                            template="plotly_dark", height=280,
                            margin=dict(l=0, r=0, t=40, b=80),
                            title="OOS Sharpe per fold",
                            xaxis_tickangle=-35,
                        )
                        st.plotly_chart(_fig_sharpe, use_container_width=True)

                    with st.expander("📋 Dettaglio fold × direzione"):
                        st.dataframe(_fold_df, use_container_width=True)

                st.divider()

                # ── Hour heatmap ──────────────────────────────────────────────
                st.subheader("⏰ Performance per ora UTC")
                _hour_df = _ta7.hourly_stats(_t7_trades)

                if not _hour_df.empty:
                    _t7h1, _t7h2 = st.columns(2)
                    with _t7h1:
                        # Heatmap: hour × direction → Win%
                        _hmap_wr = _hour_df.pivot(
                            index="Ora UTC", columns="Direzione", values="Win%"
                        ).reindex(range(24)).fillna(0)
                        _fig_hmap = go.Figure(go.Heatmap(
                            z=_hmap_wr.values,
                            x=_hmap_wr.columns.tolist(),
                            y=[f"{h:02d}:00" for h in _hmap_wr.index],
                            colorscale="RdYlGn", zmin=0, zmax=100,
                            text=_hmap_wr.values.round(0),
                            texttemplate="%{text}%",
                        ))
                        _fig_hmap.update_layout(
                            template="plotly_dark", height=500,
                            margin=dict(l=40, r=0, t=40, b=0),
                            title="Win rate % per ora UTC",
                        )
                        st.plotly_chart(_fig_hmap, use_container_width=True)

                    with _t7h2:
                        # Bar: avg P&L per hour
                        _fig_hour_pnl = go.Figure()
                        for _hd, _hc in [("LONG", "#26a69a"), ("SHORT", "#ef5350")]:
                            _sub_h = _hour_df[_hour_df["Direzione"] == _hd]
                            _fig_hour_pnl.add_bar(
                                x=_sub_h["Ora UTC"].apply(lambda h: f"{h:02d}:00"),
                                y=_sub_h["P&L medio"],
                                name=_hd, marker_color=_hc,
                            )
                        _fig_hour_pnl.add_hline(y=0, line_dash="dash",
                                                line_color="white", opacity=0.4)
                        _fig_hour_pnl.update_layout(
                            barmode="group", template="plotly_dark", height=500,
                            margin=dict(l=0, r=0, t=40, b=60),
                            title="P&L medio per ora UTC",
                            xaxis_tickangle=-45,
                        )
                        st.plotly_chart(_fig_hour_pnl, use_container_width=True)

                st.divider()

                # ── Regime GARCH ──────────────────────────────────────────────
                _reg_df = _ta7.regime_stats(_t7_trades)
                if not _reg_df.empty:
                    st.subheader("📉 Performance per regime GARCH")
                    _t7r1, _t7r2 = st.columns([1, 2])
                    with _t7r1:
                        st.dataframe(_reg_df.set_index("Regime GARCH"),
                                     use_container_width=True)
                    with _t7r2:
                        _fig_reg = go.Figure()
                        _reg_colors = {"LOW": "#78909c", "MED": "#ffb300", "HIGH": "#ef5350"}
                        _fig_reg.add_bar(
                            x=_reg_df["Regime GARCH"],
                            y=_reg_df["Win rate %"],
                            marker_color=[_reg_colors.get(r, "#aaa") for r in _reg_df["Regime GARCH"]],
                            name="Win rate %",
                        )
                        _fig_reg.add_bar(
                            x=_reg_df["Regime GARCH"],
                            y=_reg_df["PF"],
                            name="Profit Factor",
                            yaxis="y2",
                            opacity=0.7,
                        )
                        _fig_reg.update_layout(
                            barmode="group", template="plotly_dark", height=280,
                            margin=dict(l=0, r=0, t=30, b=0),
                            yaxis2=dict(overlaying="y", side="right", title="PF"),
                        )
                        st.plotly_chart(_fig_reg, use_container_width=True)

                st.divider()

                # ── Streak analysis ───────────────────────────────────────────
                _streaks = _ta7.streak_stats(_t7_trades)
                if _streaks:
                    st.subheader("🎯 Streak analysis")
                    _s1, _s2, _s3, _s4 = st.columns(4)
                    _s1.metric("Max winning streak",  _streaks.get("max_win_streak",  "—"))
                    _s2.metric("Max losing streak",   _streaks.get("max_loss_streak", "—"))
                    _s3.metric("# serie vincenti",    _streaks.get("n_win_streaks",   "—"))
                    _s4.metric("# serie perdenti",    _streaks.get("n_loss_streaks",  "—"))

                    # Equity step chart colored by win/loss
                    _t7_trades_s = _t7_trades.sort_values("entry_time").reset_index(drop=True)
                    _cum_pnl = _t7_trades_s["pnl"].cumsum()
                    _fig_eq = go.Figure()
                    _fig_eq.add_trace(go.Scatter(
                        x=_t7_trades_s["entry_time"],
                        y=_cum_pnl,
                        mode="lines",
                        line=dict(color="#26a69a", width=2),
                        name="P&L cumulato",
                    ))
                    # Color wins/losses
                    for _idx, row in _t7_trades_s.iterrows():
                        _fig_eq.add_vrect(
                            x0=row["entry_time"], x1=row["exit_time"],
                            fillcolor="#26a69a" if row["win"] else "#ef5350",
                            opacity=0.07, layer="below", line_width=0,
                        )
                    _fig_eq.update_layout(
                        template="plotly_dark", height=280,
                        margin=dict(l=0, r=0, t=30, b=0),
                        title="P&L cumulato (verde=win, rosso=loss)",
                    )
                    st.plotly_chart(_fig_eq, use_container_width=True)

        except Exception as _t7e:
            st.error(f"Errore analisi trade: {_t7e}")
            import traceback
            st.code(traceback.format_exc())


with tab8:
    import json as _t8json

    st.header("⚙️ Parametri Strategia")
    st.markdown(
        "Modifica i parametri della strategia corrente e ricalcola backtest, "
        "walk-forward e Monte Carlo per vedere come variano le performance."
    )

    _cfg_path = os.path.join(OUTPUT, "agent_strategy_config.json")

    if not os.path.exists(_cfg_path):
        st.info("Nessuna strategia configurata. Genera prima una strategia dalla tab **🤖 Agent Strategy**.")
    else:
        try:
            with open(_cfg_path) as _f8:
                _t8_cfg = _t8json.load(_f8)

            # ── Strategy info ─────────────────────────────────────────────────
            _t8_name = _t8_cfg.get("strategy_name", "Strategia corrente")
            _t8_type = _t8_cfg.get("strategy_type", "—")
            _t8_rationale = _t8_cfg.get("rationale", "")

            st.subheader(f"📋 {_t8_name}")
            _t8i1, _t8i2 = st.columns([1, 3])
            _t8i1.markdown(f"**Tipo:** `{_t8_type}`")
            _t8i1.markdown(f"**Asset:** `{_t8_cfg.get('asset', asset)}`")
            _t8i1.markdown(f"**Fonte:** `{_t8_cfg.get('source', '—')}`")
            if _t8_rationale:
                _t8i2.info(_t8_rationale)

            st.divider()

            # ── Baseline metrics ──────────────────────────────────────────────
            _t8_cmp_path = os.path.join(OUTPUT, "enhanced_strategy_comparison.csv")
            _t8_baseline = None
            if os.path.exists(_t8_cmp_path):
                _t8_cmp = pd.read_csv(_t8_cmp_path)
                _t8_vagent = _t8_cmp[_t8_cmp["version"] == "V_Agent"]
                if not _t8_vagent.empty:
                    _t8_baseline = _t8_vagent.iloc[0]

            if _t8_baseline is not None:
                st.subheader("📊 Performance corrente (baseline)")
                _b1, _b2, _b3, _b4, _b5 = st.columns(5)
                _b1.metric("CAGR %",         f"{_t8_baseline.get('cagr_pct', 0):.1f}%")
                _b2.metric("Sharpe",          f"{_t8_baseline.get('sharpe_ratio', 0):.2f}")
                _b3.metric("Max DD %",        f"{_t8_baseline.get('max_drawdown_pct', 0):.1f}%")
                _b4.metric("Win rate %",      f"{_t8_baseline.get('win_rate_pct', 0):.1f}%")
                _b5.metric("N trade",         int(_t8_baseline.get('n_trades', 0)))
                st.divider()

            # ── Parameter editor ──────────────────────────────────────────────
            st.subheader("🔧 Modifica Parametri")

            _t8c1, _t8c2 = st.columns(2)

            with _t8c1:
                st.markdown("**Stop-Loss & Take-Profit (× ATR)**")
                _t8_sl = st.number_input(
                    "SL moltiplicatore ATR",
                    min_value=0.5, max_value=10.0,
                    value=float(_t8_cfg.get("sl_mult", 2.5)),
                    step=0.5,
                    key="t8_sl_mult",
                    help="Distanza dello stop-loss dall'entry in multipli dell'ATR",
                )
                _t8_tp = st.number_input(
                    "TP moltiplicatore ATR",
                    min_value=0.5, max_value=20.0,
                    value=float(_t8_cfg.get("tp_mult", 7.0)),
                    step=0.5,
                    key="t8_tp_mult",
                    help="Distanza del take-profit dall'entry in multipli dell'ATR",
                )

                _t8_rr = _t8_tp / _t8_sl if _t8_sl > 0 else 0
                _orig_rr = _t8_cfg.get("tp_mult", 7.0) / max(_t8_cfg.get("sl_mult", 2.5), 0.01)
                _rr_delta = f"{_t8_rr - _orig_rr:+.2f}" if abs(_t8_rr - _orig_rr) > 0.01 else None
                st.metric("R:R ratio (TP/SL)", f"{_t8_rr:.2f}", delta=_rr_delta)

                st.markdown("**Ore attive UTC**")
                _t8_active = _t8_cfg.get("active_hours", [6, 17])
                _t8c1a, _t8c1b = st.columns(2)
                _t8_h_start = _t8c1a.number_input(
                    "Ora inizio", min_value=0, max_value=23,
                    value=int(_t8_active[0]) if len(_t8_active) > 0 else 6,
                    step=1, key="t8_h_start",
                    help="Prima ora UTC in cui i segnali sono attivi",
                )
                _t8_h_end = _t8c1b.number_input(
                    "Ora fine", min_value=0, max_value=23,
                    value=int(_t8_active[1]) if len(_t8_active) > 1 else 17,
                    step=1, key="t8_h_end",
                    help="Ultima ora UTC in cui i segnali sono attivi",
                )
                if _t8_h_end <= _t8_h_start:
                    st.warning("⚠️ L'ora di fine deve essere maggiore dell'ora di inizio.")

            with _t8c2:
                st.markdown("**Gestione del rischio**")
                _t8_risk = st.number_input(
                    "Rischio per trade (%)",
                    min_value=0.1, max_value=5.0,
                    value=float(_t8_cfg.get("risk_per_trade", 0.01)) * 100,
                    step=0.1, format="%.1f",
                    key="t8_risk",
                    help="Percentuale del capitale rischiata per ogni trade",
                ) / 100

                st.markdown("**Costi di transazione**")
                _t8_comm = st.number_input(
                    "Commissione (%)",
                    min_value=0.0, max_value=1.0,
                    value=float(_t8_cfg.get("commission", 0.0004)) * 100,
                    step=0.01, format="%.3f",
                    key="t8_commission",
                    help="Commissione applicata per ogni trade (entry + exit)",
                ) / 100
                _t8_slip = st.number_input(
                    "Slippage (%)",
                    min_value=0.0, max_value=1.0,
                    value=float(_t8_cfg.get("slippage", 0.0001)) * 100,
                    step=0.005, format="%.4f",
                    key="t8_slippage",
                    help="Slippage stimato per ogni trade",
                ) / 100

                st.markdown("**Riepilogo modifiche**")
                _t8_changes = []
                if abs(_t8_sl - _t8_cfg.get("sl_mult", 2.5)) > 0.01:
                    _t8_changes.append(f"SL: {_t8_cfg['sl_mult']} → **{_t8_sl}**")
                if abs(_t8_tp - _t8_cfg.get("tp_mult", 7.0)) > 0.01:
                    _t8_changes.append(f"TP: {_t8_cfg['tp_mult']} → **{_t8_tp}**")
                if _t8_h_start != int(_t8_active[0] if len(_t8_active) > 0 else 6):
                    _t8_changes.append(f"Ora inizio: {_t8_active[0]} → **{_t8_h_start}**")
                if _t8_h_end != int(_t8_active[1] if len(_t8_active) > 1 else 17):
                    _t8_changes.append(f"Ora fine: {_t8_active[1]} → **{_t8_h_end}**")
                if abs(_t8_risk - _t8_cfg.get("risk_per_trade", 0.01)) > 0.0001:
                    _t8_changes.append(f"Rischio: {_t8_cfg.get('risk_per_trade',0.01)*100:.1f}% → **{_t8_risk*100:.1f}%**")
                if abs(_t8_comm - _t8_cfg.get("commission", 0.0004)) > 0.000001:
                    _t8_changes.append(f"Comm: {_t8_cfg.get('commission',0.0004)*100:.3f}% → **{_t8_comm*100:.3f}%**")
                if abs(_t8_slip - _t8_cfg.get("slippage", 0.0001)) > 0.000001:
                    _t8_changes.append(f"Slip: {_t8_cfg.get('slippage',0.0001)*100:.4f}% → **{_t8_slip*100:.4f}%**")

                if _t8_changes:
                    for _ch in _t8_changes:
                        st.markdown(f"- {_ch}")
                else:
                    st.caption("Nessuna modifica rispetto alla configurazione corrente.")

            st.divider()

            # ── Recalculate button ────────────────────────────────────────────
            _t8_btn_disabled = (_t8_h_end <= _t8_h_start)
            if st.button(
                "▶ Ricalcola Analisi",
                use_container_width=True,
                type="primary",
                disabled=_t8_btn_disabled,
                key="t8_recalc",
            ):
                # Save updated config
                _t8_new_cfg = dict(_t8_cfg)
                _t8_new_cfg["sl_mult"]        = _t8_sl
                _t8_new_cfg["tp_mult"]        = _t8_tp
                _t8_new_cfg["active_hours"]   = [_t8_h_start, _t8_h_end]
                _t8_new_cfg["risk_per_trade"] = _t8_risk
                _t8_new_cfg["commission"]     = _t8_comm
                _t8_new_cfg["slippage"]       = _t8_slip

                with open(_cfg_path, "w") as _f8w:
                    _t8json.dump(_t8_new_cfg, _f8w, indent=2)

                with st.status(
                    f"▶ Ricalcolo Analisi — {asset} | SL={_t8_sl} TP={_t8_tp} "
                    f"ore={_t8_h_start}-{_t8_h_end}",
                    expanded=True,
                ) as _t8_status:
                    try:
                        st.write(f"📈 Backtest + Walk-Forward ({asset}, {_direction_filter})…")
                        _run_script("04_backtest.py", extra_env=_env)
                        st.cache_data.clear()
                        st.write("✅ Backtest + WFO completati.")
                        st.write("🎲 Monte Carlo (bootstrap + stress)…")
                        _run_script("05_montecarlo.py", extra_env=_env)
                        st.cache_data.clear()
                        _t8_status.update(label="✅ Ricalcolo completato", state="complete", expanded=False)
                        st.success(
                            "Analisi aggiornata con i nuovi parametri. "
                            "Consulta le tab 📈 Strategia V5, 🔄 Walk-Forward e 🎲 Monte Carlo per i risultati."
                        )
                    except subprocess.CalledProcessError as _t8e:
                        _t8_status.update(label="❌ Ricalcolo fallito", state="error")
                        st.error(f"Errore:\n```\n{_t8e.stderr.decode()[:400]}\n```")

        except Exception as _t8ex:
            st.error(f"Errore caricamento parametri: {_t8ex}")
            import traceback
            st.code(traceback.format_exc())


# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(f"{_CATALOG_FLAT.get(asset, asset)} Strategy Dashboard · Dati: Yahoo Finance via yfinance · "
           "Agent Strategy: parametri ottimizzati da Claude claude-opus-4-7")
