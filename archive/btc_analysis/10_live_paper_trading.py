"""
10_live_paper_trading.py
========================
Live Paper Trading — Strategia V5 su BTC/USDT (Binance)

Architettura:
  Config          — parametri strategia e connessione
  BinanceFeed     — REST polling API pubblica Binance (no auth per dati)
  LiveIndicators  — calcolo rolling ATR/EMA/RSI/GARCH su finestra scorrevole
  PaperBroker     — simula ordini, traccia posizioni, P&L in tempo reale
  main()          — event loop: attende chiusura candela 1h → segnale → order

Avvio:
  python3 10_live_paper_trading.py              # live su Binance
  python3 10_live_paper_trading.py --dry-run    # replay su dati storici locali

Log output:
  output/paper_trades.csv   — storico trade simulati
  output/paper_equity.csv   — equity campionata ogni candela
"""

import sys, os, time, logging, argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import requests
from scipy.optimize import minimize

sys.path.insert(0, os.path.dirname(__file__))
from strategy_core import OUTPUT_DIR

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(OUTPUT_DIR, "paper_trading.log"),
                            encoding="utf-8"),
    ],
)
log = logging.getLogger("PaperTrader")


# ══════════════════════════════════════════════════════════════════════════════
# T1-A  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    # Exchange
    symbol:            str   = "BTCUSDT"
    interval:          str   = "1h"
    base_url:          str   = "https://api.binance.com"
    warmup_candles:    int   = 300      # candele per warmup indicatori

    # Strategia V5
    sl_mult:           float = 2.0
    tp_mult:           float = 5.0
    active_hours:      tuple = (6, 22)  # UTC
    rsi_ob:            float = 70.0
    rsi_os:            float = 30.0
    min_atr_pct:       float = 0.003
    breakout_lookback: int   = 6        # ore per rolling max/min

    # Risk management
    initial_capital:   float = 10_000.0
    risk_per_trade:    float = 0.01     # 1% del capitale per trade
    max_leverage:      float = 3.0
    commission:        float = 0.0001   # 0.01% maker
    slippage:          float = 0.0001   # 0.01% market impact

    # GARCH
    garch_refit_bars:  int   = 24       # refit ogni N candele

    # Output
    output_dir:        str   = OUTPUT_DIR

    # Timeout REST
    request_timeout:   int   = 10       # secondi
    retry_attempts:    int   = 3
    retry_delay:       float = 2.0      # secondi tra retry


# ══════════════════════════════════════════════════════════════════════════════
# T1-B  BINANCE FEED
# ══════════════════════════════════════════════════════════════════════════════

class BinanceFeed:
    """
    Recupera candele OHLCV dalla API REST pubblica di Binance.
    Non richiede autenticazione — solo dati di mercato pubblici.

    Metodi:
      fetch(n)       → DataFrame con le ultime n candele chiuse
      next_close()   → timestamp UTC della prossima chiusura candela
      wait_close()   → blocca fino alla chiusura della candela corrente
    """

    KLINE_URL = "{base}/api/v3/klines"
    INTERVAL_MS = {
        "1m": 60_000, "5m": 300_000, "15m": 900_000,
        "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
    }

    def __init__(self, cfg: Config):
        self.cfg    = cfg
        self.url    = self.KLINE_URL.format(base=cfg.base_url)
        self.iv_ms  = self.INTERVAL_MS[cfg.interval]

    # ── Fetch storico ─────────────────────────────────────────────────────────

    def fetch(self, limit: int = 300) -> pd.DataFrame:
        """
        Ritorna le ultime `limit` candele chiuse come DataFrame OHLCV.
        Riprova fino a cfg.retry_attempts volte in caso di errore.
        """
        for attempt in range(1, self.cfg.retry_attempts + 1):
            try:
                resp = requests.get(
                    self.url,
                    params={
                        "symbol":   self.cfg.symbol,
                        "interval": self.cfg.interval,
                        "limit":    limit + 1,   # +1: escludi candela aperta
                    },
                    timeout=self.cfg.request_timeout,
                )
                resp.raise_for_status()
                raw = resp.json()
                break
            except Exception as e:
                log.warning(f"Fetch attempt {attempt}/{self.cfg.retry_attempts}: {e}")
                if attempt < self.cfg.retry_attempts:
                    time.sleep(self.cfg.retry_delay * attempt)
                else:
                    raise RuntimeError(f"Fetch fallito dopo {attempt} tentativi") from e

        # Escludi l'ultima riga (candela ancora aperta)
        raw = raw[:-1]
        df = pd.DataFrame(raw, columns=[
            "open_time", "Open", "High", "Low", "Close", "Volume",
            "close_time", "quote_vol", "n_trades",
            "taker_base", "taker_quote", "ignore",
        ])
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = df[col].astype(float)
        df["Date"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df = df.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]]
        return df

    # ── Timing ────────────────────────────────────────────────────────────────

    def next_close_ts(self) -> float:
        """Unix timestamp (secondi) della prossima chiusura candela."""
        now_ms  = time.time() * 1000
        elapsed = now_ms % self.iv_ms
        return (now_ms - elapsed + self.iv_ms) / 1000   # secondi

    def seconds_to_close(self) -> float:
        return max(0.0, self.next_close_ts() - time.time())

    def wait_close(self, buffer_sec: float = 5.0):
        """
        Blocca l'esecuzione fino a `buffer_sec` secondi dopo la chiusura
        della candela corrente, in modo da avere il dato definitivo.
        """
        wait = self.seconds_to_close() + buffer_sec
        close_dt = datetime.fromtimestamp(
            self.next_close_ts(), tz=timezone.utc
        ).strftime("%H:%M UTC")
        log.info(f"Prossima candela chiude alle {close_dt} "
                 f"— attesa {wait:.0f}s...")
        time.sleep(wait)

    # ── Server time check ─────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Verifica connettività con Binance."""
        try:
            r = requests.get(f"{self.cfg.base_url}/api/v3/ping",
                             timeout=self.cfg.request_timeout)
            return r.status_code == 200
        except Exception:
            return False

    def server_time(self) -> Optional[datetime]:
        """Ritorna il timestamp server di Binance."""
        try:
            r = requests.get(f"{self.cfg.base_url}/api/v3/time",
                             timeout=self.cfg.request_timeout)
            ts = r.json()["serverTime"]
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        except Exception:
            return None


# ══════════════════════════════════════════════════════════════════════════════
# T2-A  LIVE INDICATORS
# ══════════════════════════════════════════════════════════════════════════════

class LiveIndicators:
    """
    Calcola indicatori tecnici su una finestra scorrevole di candele OHLCV.

    Aggiornamento: chiamare update(df) ad ogni nuova candela chiusa.
    L'ultima riga del DataFrame restituito contiene i valori correnti.

    Indicatori prodotti:
      ATR14, RSI14, EMA50, EMA200,
      RollHigh6, RollLow6, ATR_pct,
      garch_h, garch_regime, size_mult
    """

    def __init__(self, cfg: Config):
        self.cfg              = cfg
        self._bars_since_fit  = 0         # contatore per refit GARCH
        self._garch_params    = None      # (omega, alpha, beta) ultimi fittati

    # ── Indicatori tecnici ────────────────────────────────────────────────────

    @staticmethod
    def _atr(df: pd.DataFrame, span: int = 14) -> pd.Series:
        hl = df["High"] - df["Low"]
        hc = (df["High"] - df["Close"].shift(1)).abs()
        lc = (df["Low"]  - df["Close"].shift(1)).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr.ewm(span=span, adjust=False).mean()

    @staticmethod
    def _rsi(close: pd.Series, span: int = 14) -> pd.Series:
        d    = close.diff()
        gain = d.clip(lower=0).ewm(span=span, adjust=False).mean()
        loss = (-d.clip(upper=0)).ewm(span=span, adjust=False).mean()
        rs   = gain / loss.replace(0, np.nan)
        return 100 - 100 / (1 + rs)

    # ── GARCH(1,1) fit ────────────────────────────────────────────────────────

    @staticmethod
    def _fit_garch(log_ret: np.ndarray):
        """MLE GARCH(1,1) — restituisce (omega, alpha, beta)."""
        r    = log_ret.astype(float)
        varr = float(np.var(r)) or 1e-8

        def h_seq(p):
            w, a, b = p
            h = np.empty(len(r))
            h[0] = varr
            for t in range(1, len(r)):
                h[t] = w + a * r[t-1]**2 + b * h[t-1]
            return h

        def neg_ll(p):
            w, a, b = p
            if w <= 0 or a < 0 or b < 0 or a + b >= 0.9999:
                return 1e10
            h = h_seq(p)
            if np.any(h <= 0) or not np.all(np.isfinite(h)):
                return 1e10
            return float(0.5 * np.sum(np.log(h) + r**2 / h))

        res = minimize(neg_ll, [varr * 0.03, 0.05, 0.90],
                       method="L-BFGS-B",
                       bounds=[(1e-10, varr), (0.001, 0.499), (0.001, 0.998)],
                       options={"maxiter": 300})
        return tuple(res.x)

    def _garch_h(self, log_ret: np.ndarray,
                 omega: float, alpha: float, beta: float) -> np.ndarray:
        """Sequenza varianze condizionali dato un set di parametri."""
        r = log_ret.astype(float)
        h = np.empty(len(r))
        h[0] = np.var(r) or 1e-8
        for t in range(1, len(r)):
            h[t] = omega + alpha * r[t-1]**2 + beta * h[t-1]
        return h

    # ── Update principale ─────────────────────────────────────────────────────

    def update(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Riceve il DataFrame OHLCV aggiornato (ultima riga = candela appena chiusa).
        Ritorna lo stesso DataFrame con le colonne indicatore aggiunte.
        La riga [-1] contiene i valori live correnti.
        """
        df = df.copy()

        # Tecnici
        df["ATR14"]    = self._atr(df)
        df["RSI14"]    = self._rsi(df["Close"])
        df["EMA50"]    = df["Close"].ewm(span=50,  adjust=False).mean()
        df["EMA200"]   = df["Close"].ewm(span=200, adjust=False).mean()
        df["RollHigh6"]= df["High"].rolling(self.cfg.breakout_lookback).max().shift(1)
        df["RollLow6"] = df["Low"].rolling(self.cfg.breakout_lookback).min().shift(1)
        df["ATR_pct"]  = df["ATR14"] / df["Close"]
        df["hour"]     = df.index.hour
        df["dow"]      = df.index.dayofweek
        df["log_ret"]  = np.log(df["Close"] / df["Close"].shift(1))

        # ── GARCH regime ───────────────────────────────────────────────────
        self._bars_since_fit += 1
        need_refit = (self._garch_params is None or
                      self._bars_since_fit >= self.cfg.garch_refit_bars)

        log_ret_arr = df["log_ret"].fillna(0).values
        if need_refit and len(log_ret_arr) > 50:
            try:
                self._garch_params = self._fit_garch(log_ret_arr)
                self._bars_since_fit = 0
                log.debug(f"GARCH refit: omega={self._garch_params[0]:.2e} "
                          f"alpha={self._garch_params[1]:.4f} "
                          f"beta={self._garch_params[2]:.4f}")
            except Exception as e:
                log.warning(f"GARCH fit fallito: {e} — uso EWMA fallback")
                self._garch_params = None

        if self._garch_params is not None:
            omega, alpha, beta = self._garch_params
            h = self._garch_h(log_ret_arr, omega, alpha, beta)
            df["garch_h"] = h
        else:
            # Fallback: EWMA varianza
            df["garch_h"] = df["log_ret"].ewm(span=24, adjust=False).var().fillna(1e-6)

        # Regime classification
        h_vals  = df["garch_h"].values
        lo, hi  = np.percentile(h_vals, 25), np.percentile(h_vals, 75)
        regime  = np.full(len(df), "MED", dtype=object)
        regime[h_vals < lo] = "LOW"
        regime[h_vals > hi] = "HIGH"
        df["garch_regime"] = regime
        df["size_mult"] = np.where(regime == "LOW",  0.0,
                          np.where(regime == "HIGH", 0.5, 1.0))

        return df.dropna(subset=["ATR14", "EMA50", "EMA200", "RollHigh6"])

    # ── Signal V5 sulla candela corrente ──────────────────────────────────────

    def signal(self, df: pd.DataFrame) -> dict:
        """
        Calcola il segnale V5 sull'ultima riga del DataFrame.
        Ritorna dict con: signal (1/-1/0), sl_dist, tp_dist, size_mult, regime.
        """
        if len(df) < 2:
            return {"signal": 0}

        row = df.iloc[-1]
        h0, h1 = self.cfg.active_hours

        time_ok  = h0 <= int(row["hour"]) <= h1
        vol_ok   = float(row["ATR_pct"]) > self.cfg.min_atr_pct
        regime   = str(row["garch_regime"])
        sm       = float(row["size_mult"])

        if not time_ok or not vol_ok or regime == "LOW":
            return {"signal": 0, "regime": regime}

        trend_long  = float(row["EMA50"]) > float(row["EMA200"])
        trend_short = float(row["EMA50"]) < float(row["EMA200"])
        bo_long     = float(row["Close"]) > float(row["RollHigh6"])
        bo_short    = float(row["Close"]) < float(row["RollLow6"])
        rsi_ok_l    = float(row["RSI14"]) < self.cfg.rsi_ob
        rsi_ok_s    = float(row["RSI14"]) > self.cfg.rsi_os

        atr = float(row["ATR14"])
        sig = 0
        if bo_long  and trend_long  and rsi_ok_l:
            sig =  1
        elif bo_short and trend_short and rsi_ok_s:
            sig = -1

        return {
            "signal":   sig,
            "sl_dist":  atr * self.cfg.sl_mult,
            "tp_dist":  atr * self.cfg.tp_mult,
            "size_mult": sm,
            "regime":   regime,
            "atr":      atr,
            "rsi":      float(row["RSI14"]),
            "ema_diff": float(row["EMA50"]) - float(row["EMA200"]),
        }


# ══════════════════════════════════════════════════════════════════════════════
# T3-A  PAPER BROKER
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Position:
    direction:   int    # +1 long, -1 short
    entry_price: float
    sl_price:    float
    tp_price:    float
    qty:         float  # BTC
    entry_cost:  float  # commissione + slippage pagata all'entrata
    open_time:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PaperBroker:
    """
    Simula l'esecuzione di ordini, gestisce la posizione aperta,
    calcola P&L, e persiste i trade su CSV.

    Metodi pubblici:
      open_position(sig, price, candle_time)  → apre posizione se flat
      check_exit(high, low, close, ts)        → chiude su SL/TP o candela
      step_equity(close, ts)                  → campiona equity corrente
      summary()                               → stampa riepilogo sessione
    """

    def __init__(self, cfg: Config):
        self.cfg       = cfg
        self.capital   = cfg.initial_capital
        self.position: Optional[Position] = None
        self.trades:   list  = []
        self.equity_ts: list = []

        # File CSV
        self._trades_path = os.path.join(cfg.output_dir, "paper_trades.csv")
        self._equity_path = os.path.join(cfg.output_dir, "paper_equity.csv")

        # Intestazioni CSV se non esistono
        if not os.path.exists(self._trades_path):
            pd.DataFrame(columns=[
                "open_time", "close_time", "direction", "entry_price",
                "exit_price", "qty", "gross_pnl", "costs", "net_pnl",
                "capital_after", "exit_reason",
            ]).to_csv(self._trades_path, index=False)

        if not os.path.exists(self._equity_path):
            pd.DataFrame(columns=["timestamp", "equity"]).to_csv(
                self._equity_path, index=False)

    # ── Position sizing ───────────────────────────────────────────────────────

    def _size(self, sl_dist: float, size_mult: float) -> float:
        """
        Calcola la quantità in BTC rispettando:
          - risk_per_trade × capital = dollari a rischio
          - max_leverage cap
        Ritorna 0.0 se sl_dist <= 0 o size_mult == 0.
        """
        if sl_dist <= 0 or size_mult <= 0:
            return 0.0
        risk_usd   = self.capital * self.cfg.risk_per_trade * size_mult
        qty_risk   = risk_usd / sl_dist                          # da SL
        qty_lev    = (self.capital * self.cfg.max_leverage) / (sl_dist / (self.cfg.sl_mult))
        qty        = min(qty_risk, qty_lev)
        return max(0.0, qty)

    # ── Open ──────────────────────────────────────────────────────────────────

    def open_position(self, sig: dict, price: float, ts: datetime) -> bool:
        """
        Apre una posizione se:
          - nessuna posizione attiva
          - sig["signal"] != 0
          - size calcolata > 0
        Ritorna True se aperta.
        """
        if self.position is not None or sig.get("signal", 0) == 0:
            return False

        direction  = sig["signal"]
        sl_dist    = sig["sl_dist"]
        tp_dist    = sig["tp_dist"]
        sm         = sig.get("size_mult", 1.0)
        qty        = self._size(sl_dist, sm)
        if qty <= 0:
            return False

        # slippage: peggiora il prezzo di entrata
        slip   = price * self.cfg.slippage
        fill   = price + direction * slip
        comm   = fill * qty * self.cfg.commission
        cost   = comm + fill * qty * self.cfg.slippage

        sl_p   = fill - direction * sl_dist
        tp_p   = fill + direction * tp_dist

        self.position = Position(
            direction   = direction,
            entry_price = fill,
            sl_price    = sl_p,
            tp_price    = tp_p,
            qty         = qty,
            entry_cost  = cost,
            open_time   = ts,
        )
        log.info(
            f"OPEN {'LONG' if direction==1 else 'SHORT'}  "
            f"@ {fill:.2f}  qty={qty:.6f}  "
            f"SL={sl_p:.2f}  TP={tp_p:.2f}  "
            f"regime={sig.get('regime','?')}  "
            f"rsi={sig.get('rsi',0):.1f}"
        )
        return True

    # ── Exit check ────────────────────────────────────────────────────────────

    def check_exit(self, high: float, low: float, close: float,
                   ts: datetime) -> Optional[dict]:
        """
        Controlla se la candela ha toccato SL o TP.
        In caso positivo chiude la posizione e ritorna il record trade.
        """
        if self.position is None:
            return None

        p    = self.position
        hit  = None

        if p.direction == 1:    # long
            if low  <= p.sl_price:
                hit = ("SL", p.sl_price)
            elif high >= p.tp_price:
                hit = ("TP", p.tp_price)
        else:                   # short
            if high >= p.sl_price:
                hit = ("SL", p.sl_price)
            elif low  <= p.tp_price:
                hit = ("TP", p.tp_price)

        if hit is None:
            return None

        reason, exit_px = hit
        return self._close(exit_px, reason, ts)

    def _close(self, exit_px: float, reason: str, ts: datetime) -> dict:
        p     = self.position
        slip  = exit_px * self.cfg.slippage
        fill  = exit_px - p.direction * slip        # sfavorevole all'uscita
        comm  = fill * p.qty * self.cfg.commission
        costs = p.entry_cost + comm + fill * p.qty * self.cfg.slippage

        gross_pnl = p.direction * (fill - p.entry_price) * p.qty
        net_pnl   = gross_pnl - costs
        self.capital += net_pnl

        record = {
            "open_time":     p.open_time.isoformat(),
            "close_time":    ts.isoformat(),
            "direction":     p.direction,
            "entry_price":   p.entry_price,
            "exit_price":    fill,
            "qty":           p.qty,
            "gross_pnl":     round(gross_pnl, 4),
            "costs":         round(costs, 4),
            "net_pnl":       round(net_pnl, 4),
            "capital_after": round(self.capital, 4),
            "exit_reason":   reason,
        }
        self.trades.append(record)
        pd.DataFrame([record]).to_csv(
            self._trades_path, mode="a", header=False, index=False)

        log.info(
            f"CLOSE [{reason}]  fill={fill:.2f}  "
            f"pnl={net_pnl:+.2f}  capital={self.capital:.2f}"
        )
        self.position = None
        return record

    # ── Equity snapshot ───────────────────────────────────────────────────────

    def step_equity(self, close: float, ts: datetime):
        """Campiona equity mark-to-market ad ogni candela chiusa."""
        if self.position is not None:
            p        = self.position
            unreal   = p.direction * (close - p.entry_price) * p.qty
            equity   = self.capital + unreal
        else:
            equity = self.capital

        rec = {"timestamp": ts.isoformat(), "equity": round(equity, 4)}
        self.equity_ts.append(rec)
        pd.DataFrame([rec]).to_csv(
            self._equity_path, mode="a", header=False, index=False)
        return equity

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def dashboard(self, close: float, sig: dict, candle_ts: datetime):
        equity = self.step_equity(close, candle_ts)
        pnl    = equity - self.cfg.initial_capital
        pnl_pct = pnl / self.cfg.initial_capital * 100
        n_win  = sum(1 for t in self.trades if t["net_pnl"] > 0)
        n_tot  = len(self.trades)
        wr     = n_win / n_tot * 100 if n_tot else 0.0
        pos    = (f"{'LONG' if self.position.direction==1 else 'SHORT'} "
                  f"@ {self.position.entry_price:.2f}"
                  if self.position else "FLAT")

        print(
            f"\n{'─'*62}\n"
            f"  {candle_ts.strftime('%Y-%m-%d %H:%M UTC')}   BTC={close:.2f}\n"
            f"  Equity : {equity:>10.2f} USDT  ({pnl_pct:+.2f}%)\n"
            f"  Trades : {n_tot}  Win%={wr:.1f}%\n"
            f"  Pos    : {pos}\n"
            f"  Regime : {sig.get('regime','?')}  "
            f"RSI={sig.get('rsi',0):.1f}  "
            f"Signal={'BUY' if sig.get('signal')==1 else 'SELL' if sig.get('signal')==-1 else '—'}\n"
            f"{'─'*62}"
        )

    # ── Summary ───────────────────────────────────────────────────────────────

    def summary(self):
        n   = len(self.trades)
        if n == 0:
            log.info("Nessun trade eseguito.")
            return
        pnl_arr  = np.array([t["net_pnl"] for t in self.trades])
        wins     = (pnl_arr > 0).sum()
        tot_pnl  = pnl_arr.sum()
        avg_pnl  = pnl_arr.mean()
        sharpe   = (pnl_arr.mean() / pnl_arr.std() * np.sqrt(252 * 24)
                    if pnl_arr.std() > 0 else 0.0)
        log.info(
            f"\n{'═'*50}\n"
            f"  SESSIONE TERMINATA\n"
            f"  Trade totali : {n}\n"
            f"  Win rate     : {wins/n*100:.1f}%\n"
            f"  P&L netto    : {tot_pnl:+.2f} USDT\n"
            f"  P&L medio    : {avg_pnl:+.2f} USDT\n"
            f"  Sharpe ann.  : {sharpe:.3f}\n"
            f"  Capitale fin.: {self.capital:.2f} USDT\n"
            f"{'═'*50}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# T3-B  MAIN EVENT LOOP
# ══════════════════════════════════════════════════════════════════════════════

def _load_dry_run_data(cfg: Config) -> pd.DataFrame:
    """Carica dati storici locali per il dry-run."""
    path = os.path.join(cfg.output_dir, "btc_hourly.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"File storico non trovato: {path}\n"
            "Esegui prima: python3 01_data_download.py"
        )
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    # Rinomina colonne se necessario
    df.columns = [c.capitalize() for c in df.columns]
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing  = required - set(df.columns)
    if missing:
        raise ValueError(f"Colonne mancanti nel CSV: {missing}")
    return df[["Open", "High", "Low", "Close", "Volume"]]


def main():
    parser = argparse.ArgumentParser(description="BTC Paper Trader V5")
    parser.add_argument("--dry-run", action="store_true",
                        help="Replay su dati storici locali (nessuna connessione live)")
    parser.add_argument("--candles", type=int, default=0,
                        help="In dry-run: numero candele da simulare (0=tutte)")
    args = parser.parse_args()

    cfg    = Config()
    ind    = LiveIndicators(cfg)
    broker = PaperBroker(cfg)

    os.makedirs(cfg.output_dir, exist_ok=True)

    # ── Dry-run: replay su dati storici ──────────────────────────────────────
    if args.dry_run:
        log.info("DRY-RUN: caricamento dati storici locali...")
        full_df = _load_dry_run_data(cfg)

        warmup = cfg.warmup_candles
        limit  = args.candles if args.candles > 0 else len(full_df) - warmup
        limit  = min(limit, len(full_df) - warmup)

        log.info(f"Warmup={warmup} candele, simulazione={limit} candele, "
                 f"totale disponibili={len(full_df)}")

        for i in range(limit):
            # Finestra scorrevole: warmup + candele già viste
            end   = warmup + i + 1
            slice_df = full_df.iloc[:end].copy()

            df_ind   = ind.update(slice_df)
            if len(df_ind) < 2:
                continue

            last      = df_ind.iloc[-1]
            candle_ts = last.name.to_pydatetime()
            close     = float(last["Close"])
            high      = float(last["High"])
            low       = float(last["Low"])

            # Controlla uscita prima del segnale
            broker.check_exit(high, low, close, candle_ts)

            sig = ind.signal(df_ind)

            # Tenta apertura solo se flat
            broker.open_position(sig, close, candle_ts)

            # Dashboard ogni 24 candele
            if i % 24 == 0:
                broker.dashboard(close, sig, candle_ts)

        broker.summary()
        log.info(f"Trades salvati in: {broker._trades_path}")
        log.info(f"Equity salvata in: {broker._equity_path}")
        return

    # ── Live mode: polling Binance ────────────────────────────────────────────
    feed = BinanceFeed(cfg)

    log.info("Verifica connettività Binance...")
    if not feed.ping():
        log.error("Impossibile raggiungere Binance — abort.")
        sys.exit(1)

    st = feed.server_time()
    log.info(f"Server time Binance: {st}")

    log.info(f"Warmup: scarico {cfg.warmup_candles} candele storiche...")
    df_live = feed.fetch(cfg.warmup_candles)
    log.info(f"Warmup completato: {len(df_live)} candele [fino a {df_live.index[-1]}]")

    bar_count = 0
    try:
        while True:
            feed.wait_close()
            df_live = feed.fetch(cfg.warmup_candles)

            df_ind  = ind.update(df_live)
            if len(df_ind) < 2:
                log.warning("Dati insufficienti dopo warmup — skip.")
                continue

            last      = df_ind.iloc[-1]
            candle_ts = last.name.to_pydatetime()
            close     = float(last["Close"])
            high      = float(last["High"])
            low       = float(last["Low"])

            broker.check_exit(high, low, close, candle_ts)

            sig = ind.signal(df_ind)
            broker.open_position(sig, close, candle_ts)
            broker.dashboard(close, sig, candle_ts)

            bar_count += 1

    except KeyboardInterrupt:
        log.info("Interruzione manuale ricevuta.")
    finally:
        # Chiudi posizione aperta al prezzo corrente
        if broker.position is not None:
            log.warning("Chiusura forzata posizione aperta su CTRL+C...")
            broker._close(close, "FORCED", datetime.now(timezone.utc))
        broker.summary()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
