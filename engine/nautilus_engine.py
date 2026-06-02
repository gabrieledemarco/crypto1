"""
engine/nautilus_engine.py
=========================
NautilusTrader BacktestEngine wrapper — Phase 1 integration.

run_nautilus_backtest(df_ind, cfg) → dict compatible with backtest_v2():
  {"trades": DataFrame, "equity": Series, "final_capital": float}

Activate:  USE_NAUTILUS_ENGINE=1 (environment variable)
Install:   pip install "nautilus_trader>=1.200.0"
"""
from __future__ import annotations

import logging
import os
from decimal import Decimal

import numpy as np
import pandas as pd

log = logging.getLogger("nautilus_engine")

# ── Availability ──────────────────────────────────────────────────────────────

NAUTILUS_AVAILABLE = False
try:
    import nautilus_trader as _nt_pkg  # noqa: F401
    NAUTILUS_AVAILABLE = True
except ImportError:
    log.debug("nautilus_trader not installed — NautilusEngine disabled")


def is_enabled() -> bool:
    """Return True when nautilus_trader is installed and USE_NAUTILUS_ENGINE=1."""
    return NAUTILUS_AVAILABLE and os.getenv("USE_NAUTILUS_ENGINE", "").lower() in (
        "1", "true", "yes"
    )


# ── Signal registry (bypasses msgspec serialisation limits) ──────────────────
# Maps a run-unique key → payload dict so the Strategy can access the
# pre-computed signal map without embedding it in StrategyConfig.

_SIGNAL_REGISTRY: dict[str, dict] = {}

# ── Conditional imports + Strategy class ─────────────────────────────────────

if NAUTILUS_AVAILABLE:
    try:
        from nautilus_trader.config import StrategyConfig
        from nautilus_trader.model.identifiers import InstrumentId
        from nautilus_trader.model.data import BarType
        from nautilus_trader.model.enums import OrderSide, OrderType
        from nautilus_trader.model.events import OrderFilled, PositionClosed
        from nautilus_trader.model.objects import Price, Quantity
        from nautilus_trader.trading.strategy import Strategy

        class _ParetoConfig(StrategyConfig, frozen=True):
            """Minimal strategy config — signal data lives in _SIGNAL_REGISTRY."""
            instrument_id: InstrumentId
            bar_type: BarType
            registry_key: str
            commission: float = 0.0004
            leverage: float = 1.0
            position_size_method: str = "risk_pct"
            price_precision: int = 2
            size_precision: int = 8

        class _ParetoStrategy(Strategy):
            """
            Event-driven strategy that reads pre-computed signals and submits
            bracket orders (market entry + SL stop + TP limit) via the simulated
            NautilusTrader venue.  Tracks fills to build a backtest_v2-compatible
            trade log and equity curve.
            """

            def __init__(self, config: _ParetoConfig) -> None:
                super().__init__(config)
                reg = _SIGNAL_REGISTRY.get(config.registry_key, {})
                self._signal_map: dict[int, tuple] = reg.get("signal_map", {})
                self._capital: float = float(reg.get("capital", 10_000.0))
                self._risk_pct: float = float(reg.get("risk_pct", 0.01))
                self._ps_method: str = str(reg.get("ps_method", "risk_pct"))
                # Mutable state
                self._realized_pnl: float = 0.0
                self._in_position: bool = False
                self._entry_info: dict = {}   # entry_order_id → metadata
                self._trades: list = []
                self._equity_ts: list = []    # [(ts_ns, equity_value), ...]

            # ── Lifecycle ─────────────────────────────────────────────────────

            def on_start(self) -> None:
                self.subscribe_bars(self.config.bar_type)

            def on_stop(self) -> None:
                self.unsubscribe_bars(self.config.bar_type)

            # ── Bar handler ───────────────────────────────────────────────────

            def on_bar(self, bar) -> None:
                ts_ns = bar.ts_event
                current_equity = self._capital + self._realized_pnl
                self._equity_ts.append((ts_ns, current_equity))

                if self._in_position:
                    return

                sig_data = self._signal_map.get(ts_ns)
                if not sig_data:
                    return

                sig, sl_dist, tp_dist = sig_data
                close = float(bar.close)
                lever = float(self.config.leverage)

                # Position sizing
                if self._ps_method == "fixed_pct":
                    qty = (current_equity * self._risk_pct * lever) / close if close > 0 else 0.0
                else:
                    risk_amount = current_equity * self._risk_pct
                    qty = risk_amount / sl_dist if sl_dist > 0 else 0.0
                max_qty = (current_equity * lever) / close if close > 0 else 0.0
                qty = min(qty, max_qty)
                if qty <= 0.0:
                    return

                order_side = OrderSide.BUY if sig == 1 else OrderSide.SELL
                sl_price = close - sl_dist if sig == 1 else close + sl_dist
                tp_price = close + tp_dist if sig == 1 else close - tp_dist

                p = self.config.price_precision
                s = self.config.size_precision
                min_qty = 10 ** (-s)

                try:
                    bracket = self.order_factory.bracket(
                        instrument_id=self.config.instrument_id,
                        order_side=order_side,
                        quantity=Quantity.from_str(f"{max(qty, min_qty):.{s}f}"),
                        sl_trigger_price=Price.from_str(f"{max(sl_price, 10**-p):.{p}f}"),
                        tp_price=Price.from_str(f"{max(tp_price, 10**-p):.{p}f}"),
                        entry_order_type=OrderType.MARKET,
                    )
                    entry_oid = str(bracket.first.client_order_id)
                    self._entry_info[entry_oid] = {
                        "sig": sig,
                        "close": close,
                        "qty": qty,
                        "sl_price": sl_price,
                        "tp_price": tp_price,
                        "ts": ts_ns,
                        "actual_entry": None,
                    }
                    self.submit_order_list(bracket)
                    self._in_position = True
                except Exception as exc:
                    log.debug("Bracket order skipped at ts=%d: %s", ts_ns, exc)

            # ── Fill handler ──────────────────────────────────────────────────

            def on_order_filled(self, event: OrderFilled) -> None:
                order_id = str(event.client_order_id)

                if order_id in self._entry_info:
                    # Entry fill: record actual fill price
                    self._entry_info[order_id]["actual_entry"] = float(event.last_px)
                    return

                # Exit fill (SL or TP)
                entry = next(iter(self._entry_info.values()), None)
                if entry is None:
                    self._in_position = False
                    return

                ep = entry.get("actual_entry") or entry["close"]
                exit_price = float(event.last_px)
                qty = float(event.last_qty)
                sig = entry["sig"]
                comm = float(self.config.commission)

                gross_pnl = sig * qty * (exit_price - ep)
                costs = qty * ep * comm + qty * exit_price * comm
                net_pnl = gross_pnl - costs
                self._realized_pnl += net_pnl

                # Infer exit reason: whichever level the fill price is closer to
                sl_dist = abs(exit_price - entry["sl_price"])
                tp_dist = abs(exit_price - entry["tp_price"])
                exit_reason = "TP" if tp_dist <= sl_dist else "SL"
                notional = ep * qty
                log_ret = float(np.log1p(net_pnl / notional)) * 100 if notional > 0 else 0.0

                self._trades.append({
                    "entry_time":  pd.Timestamp(entry["ts"]),
                    "exit_time":   pd.Timestamp(event.ts_event),
                    "direction":   "LONG" if sig == 1 else "SHORT",
                    "entry_price": ep,
                    "exit_price":  exit_price,
                    "qty":         qty,
                    "gross_pnl":   round(gross_pnl, 6),
                    "costs":       round(costs, 6),
                    "pnl":         round(net_pnl, 6),
                    "pnl_pct":     round(log_ret, 4),
                    "exit_reason": exit_reason,
                })
                self._entry_info.clear()
                self._in_position = False

            def on_position_closed(self, event: PositionClosed) -> None:
                """Failsafe: ensure state is cleared if fill handler missed the exit."""
                self._in_position = False
                self._entry_info.clear()

    except Exception as _init_exc:
        NAUTILUS_AVAILABLE = False
        log.warning("NautilusTrader strategy init failed: %s", _init_exc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _price_prec(sample: float) -> int:
    if sample >= 10_000: return 1
    if sample >= 1_000:  return 2
    if sample >= 100:    return 3
    if sample >= 1:      return 4
    if sample >= 0.01:   return 6
    return 8


def _timeframe_to_bar_spec(tf: str):
    from nautilus_trader.model.enums import BarAggregation, PriceType
    from nautilus_trader.model.data import BarSpecification
    _map = {
        "1m":  (1,  BarAggregation.MINUTE),
        "5m":  (5,  BarAggregation.MINUTE),
        "15m": (15, BarAggregation.MINUTE),
        "30m": (30, BarAggregation.MINUTE),
        "1h":  (1,  BarAggregation.HOUR),
        "4h":  (4,  BarAggregation.HOUR),
        "1d":  (1,  BarAggregation.DAY),
        "1wk": (1,  BarAggregation.WEEK),
    }
    step, agg = _map.get(tf, (1, BarAggregation.HOUR))
    return BarSpecification(step, agg, PriceType.LAST)


def _make_instrument(ticker: str, venue, p_prec: int, s_prec: int):
    from nautilus_trader.model.identifiers import InstrumentId, Symbol
    from nautilus_trader.model.currencies import USD, USDT
    from nautilus_trader.model.objects import Price, Quantity

    sym = ticker.replace("-", "").upper()[:20]
    inst_id = InstrumentId(Symbol(sym), venue)
    p_inc = Price.from_str(f"{10**-p_prec:.{p_prec}f}")
    s_inc = Quantity.from_str(f"{10**-s_prec:.{s_prec}f}")
    is_crypto = any(x in ticker.upper() for x in
                    ["-USD", "-USDT", "BTC", "ETH", "SOL", "BNB", "XRP", "ADA"])

    if is_crypto:
        from nautilus_trader.model.instruments import CryptoPerpetual
        from nautilus_trader.model.currencies import Currency as _Ccy
        base_str = ticker.split("-")[0].upper() if "-" in ticker else ticker[:3].upper()
        try:
            base_ccy = _Ccy.from_str(base_str)
        except Exception:
            base_ccy = USDT
        return CryptoPerpetual(
            instrument_id=inst_id,
            raw_symbol=Symbol(sym),
            base_currency=base_ccy,
            quote_currency=USDT,
            settlement_currency=USDT,
            is_inverse=False,
            price_precision=p_prec,
            size_precision=s_prec,
            price_increment=p_inc,
            size_increment=s_inc,
            max_quantity=Quantity.from_str("1000000.0"),
            min_quantity=s_inc,
            max_notional=None,
            min_notional=None,
            max_price=Price.from_str(f"{10**7:.{p_prec}f}"),
            min_price=p_inc,
            margin_init=Decimal("0.05"),
            margin_maint=Decimal("0.025"),
            maker_fee=Decimal("0.0002"),
            taker_fee=Decimal("0.0004"),
            ts_event=0,
            ts_init=0,
        )
    else:
        from nautilus_trader.model.instruments import Equity
        return Equity(
            instrument_id=inst_id,
            raw_symbol=Symbol(sym),
            currency=USD,
            price_precision=p_prec,
            price_increment=p_inc,
            lot_size=Quantity.from_str("1"),
            isin=None,
            ts_event=0,
            ts_init=0,
        )


def _df_to_bars(df: pd.DataFrame, bar_type, p_prec: int, s_prec: int) -> list:
    """Convert OHLCV DataFrame to NautilusTrader Bar objects (strictly ascending ts)."""
    from nautilus_trader.model.data import Bar
    from nautilus_trader.model.objects import Price, Quantity

    bars: list = []
    prev_ns: int = 0
    for ts, row in df.iterrows():
        ts_ns = int(pd.Timestamp(ts).value)
        if ts_ns <= prev_ns:
            ts_ns = prev_ns + 1_000_000   # +1 ms jitter
        prev_ns = ts_ns

        o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
        v = float(row.get("Volume", 1.0))
        if h < l:
            h, l = l, h
        if any(x <= 0 for x in (o, h, l, c)):
            continue
        try:
            bars.append(Bar(
                bar_type=bar_type,
                open=Price.from_str(f"{o:.{p_prec}f}"),
                high=Price.from_str(f"{h:.{p_prec}f}"),
                low=Price.from_str(f"{l:.{p_prec}f}"),
                close=Price.from_str(f"{c:.{p_prec}f}"),
                volume=Quantity.from_str(f"{max(v, 10**-s_prec):.{s_prec}f}"),
                ts_event=ts_ns,
                ts_init=ts_ns,
            ))
        except Exception as exc:
            log.debug("Bar conversion skip at %s: %s", ts, exc)

    return bars


# ── Main entry point ──────────────────────────────────────────────────────────

def run_nautilus_backtest(df_ind: pd.DataFrame, cfg: dict) -> dict:
    """
    Run a backtest using NautilusTrader BacktestEngine.

    Parameters
    ----------
    df_ind : pd.DataFrame
        Indicators DataFrame (output of compute_indicators_v2).
    cfg : dict
        Same config dict as run_versions(): sl_mult, tp_mult, active_hours,
        commission, leverage, risk_per_trade, ticker, timeframe, etc.

    Returns
    -------
    dict
        {"trades": pd.DataFrame, "equity": pd.Series, "final_capital": float}
        Identical structure to backtest_v2() output — drop-in compatible
        with compute_metrics().
    """
    if not NAUTILUS_AVAILABLE:
        raise RuntimeError(
            "nautilus_trader is not installed. "
            "Run: pip install 'nautilus_trader>=1.200.0'"
        )

    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.config import BacktestEngineConfig
    from nautilus_trader.model.currencies import USD, USDT
    from nautilus_trader.model.enums import OmsType, AccountType, AggregationSource
    from nautilus_trader.model.identifiers import Venue, TraderId
    from nautilus_trader.model.objects import Money

    ticker    = cfg.get("ticker", "BTCUSD")
    timeframe = cfg.get("timeframe", "1h")
    capital   = float(cfg.get("initial_capital", 10_000))
    sl_mult   = float(cfg.get("sl_mult", 2.0))
    tp_mult   = float(cfg.get("tp_mult", 5.0))
    act_hrs   = tuple(cfg.get("active_hours", [6, 22]))
    risk_pct  = float(cfg.get("risk_per_trade", 0.01))
    leverage  = float(cfg.get("leverage", 1.0))
    direction = cfg.get("direction", "ALL")
    ps_meth   = cfg.get("position_size_method", "risk_pct")
    commission= float(cfg.get("commission", 0.0004))
    use_garch = cfg.get("use_garch_filter", True)

    if df_ind.empty:
        raise ValueError("df_ind is empty — cannot run NautilusTrader backtest")

    sample_price = float(df_ind["Close"].dropna().iloc[0])
    p_prec = _price_prec(sample_price)
    s_prec = 8 if sample_price < 1_000 else 4

    is_crypto = any(x in ticker.upper() for x in ["-USD", "-USDT", "BTC", "ETH", "SOL", "BNB"])
    quote_ccy = USDT if is_crypto else USD

    venue = Venue("SIM")
    instrument = _make_instrument(ticker, venue, p_prec, s_prec)

    bar_spec = _timeframe_to_bar_spec(timeframe)
    from nautilus_trader.model.data import BarType
    bar_type = BarType(instrument.id, bar_spec, AggregationSource.EXTERNAL)

    # Pre-compute signals (same pipeline as run_versions → no lookahead)
    from engine.strategy_core import generate_signals_v2
    df_s = generate_signals_v2(
        df_ind,
        atr_mult_sl=sl_mult,
        atr_mult_tp=tp_mult,
        active_hours=act_hrs,
        use_garch_filter=use_garch,
    )
    if direction == "LONG":
        df_s = df_s.copy()
        df_s.loc[df_s["signal"] == -1, "signal"] = 0
    elif direction == "SHORT":
        df_s = df_s.copy()
        df_s.loc[df_s["signal"] == 1, "signal"] = 0

    # Build signal map: ts_ns → (signal, sl_dist, tp_dist)
    signal_map: dict[int, tuple] = {
        int(pd.Timestamp(ts).value): (int(row["signal"]), float(row["SL_dist"]), float(row["TP_dist"]))
        for ts, row in df_s[df_s["signal"] != 0].iterrows()
    }

    bars = _df_to_bars(df_s, bar_type, p_prec, s_prec)
    if not bars:
        raise ValueError("No valid bars for NautilusTrader backtest")

    reg_key = f"nt_{id(df_ind)}_{id(cfg)}"
    _SIGNAL_REGISTRY[reg_key] = {
        "signal_map": signal_map,
        "capital": capital,
        "risk_pct": risk_pct,
        "commission": commission,
        "leverage": leverage,
        "ps_method": ps_meth,
    }

    try:
        engine_cfg = BacktestEngineConfig(trader_id=TraderId("PARETO-001"))
        engine = BacktestEngine(config=engine_cfg)

        engine.add_venue(
            venue=venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.MARGIN,
            starting_balances=[Money(capital, quote_ccy)],
            base_currency=quote_ccy,
            default_leverage=Decimal(str(leverage)),
        )
        engine.add_instrument(instrument)
        engine.add_data(bars)

        strategy = _ParetoStrategy(
            config=_ParetoConfig(
                instrument_id=instrument.id,
                bar_type=bar_type,
                registry_key=reg_key,
                commission=commission,
                leverage=leverage,
                position_size_method=ps_meth,
                price_precision=p_prec,
                size_precision=s_prec,
            )
        )
        engine.add_strategy(strategy)
        engine.run()

        result = _extract_results(strategy, capital)
        engine.dispose()
        return result

    finally:
        _SIGNAL_REGISTRY.pop(reg_key, None)


def _extract_results(strategy: "_ParetoStrategy", capital: float) -> dict:
    """Convert strategy state to backtest_v2-compatible output dict."""
    trades_df = pd.DataFrame(strategy._trades) if strategy._trades else pd.DataFrame()

    if not strategy._equity_ts:
        equity_s = pd.Series(dtype=float)
        return {"trades": trades_df, "equity": equity_s, "final_capital": capital}

    ts_index = pd.to_datetime([ts for ts, _ in strategy._equity_ts])
    equity_vals = [v for _, v in strategy._equity_ts]
    equity_s = pd.Series(equity_vals, index=ts_index)

    return {
        "trades": trades_df,
        "equity": equity_s,
        "final_capital": float(equity_vals[-1]) if equity_vals else capital,
    }
