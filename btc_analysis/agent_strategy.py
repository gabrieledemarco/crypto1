"""
agent_strategy.py
=================
Claude AI agent that reads statistical analysis results and proposes the
optimal trading strategy configuration.

Runs after: 01_data_download → 02_timeseries_analysis → 03_pattern_analysis
Outputs:    output/agent_strategy_config.json

If ANTHROPIC_API_KEY is not set, falls back to V5 default parameters
(SL=2×ATR, TP=5×ATR, maker fee, GARCH filter, active hours 06-22 UTC).
"""

import os
import json
import re
import warnings

warnings.filterwarnings("ignore")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

V5_DEFAULT = {
    "sl_mult": 2.0,
    "tp_mult": 5.0,
    "active_hours": [6, 22],
    "rsi_ob": 70.0,
    "rsi_os": 30.0,
    "min_atr_pct": 0.003,
    "use_garch_filter": True,
    "commission": 0.0001,
    "slippage": 0.0001,
    "risk_per_trade": 0.01,
    "rationale": (
        "Default V5: ATR breakout + GARCH filter, SL=2×ATR, TP=5×ATR, "
        "maker fee 0.01%/side, active hours 06-22 UTC."
    ),
    "source": "default",
}

SYSTEM_PROMPT = """You are an expert quantitative trading strategist specialising in crypto markets.

Your task: analyse the BTC/USD statistical results below and output the optimal
configuration for an ATR-based intraday breakout strategy.

Strategy mechanics:
• Entry  : close breaks above (LONG) or below (SHORT) the rolling 6-bar high/low
• Trend  : EMA50 vs EMA200 alignment
• Vol    : optional GARCH(1,1) regime filter — skip trades in LOW-vol regime
• SL     : entry ± sl_mult × ATR14
• TP     : entry ± tp_mult × ATR14
• Hours  : only trade within [active_hours[0], active_hours[1]] UTC
• RSI    : skip longs when RSI ≥ rsi_ob; skip shorts when RSI ≤ rsi_os

Respond with ONLY a JSON object in this exact format (no prose, no markdown):
{
  "sl_mult": <float 0.5–5.0>,
  "tp_mult": <float > sl_mult, max 10.0>,
  "active_hours": [<start 0–23>, <end 0–23>],
  "rsi_ob": <float 60–90>,
  "rsi_os": <float 10–40>,
  "min_atr_pct": <float 0.001–0.02>,
  "use_garch_filter": <true|false>,
  "commission": <float, e.g. 0.0001 maker or 0.0004 taker>,
  "slippage": <float, e.g. 0.0001>,
  "risk_per_trade": <float 0.005–0.05>,
  "rationale": "<one concise sentence explaining the choices>"
}"""


def _read_safe(path: str, max_chars: int = 6000) -> str:
    if not os.path.exists(path):
        return f"[not found: {os.path.basename(path)}]"
    try:
        with open(path, encoding="utf-8") as f:
            txt = f.read(max_chars)
        return txt + ("\n[truncated]" if len(txt) == max_chars else "")
    except Exception as exc:
        return f"[error reading {os.path.basename(path)}: {exc}]"


def _build_context() -> str:
    files = [
        ("Statistical Report",         "REPORT.txt"),
        ("Enhanced Strategy Comparison","enhanced_strategy_comparison.csv"),
        ("Walk-Forward Results",        "walk_forward_results.csv"),
        ("Monte Carlo Bootstrap",       "mc_bootstrap_results.csv"),
        ("Grid-Search Optimization",    "optimization_results.csv"),
    ]
    parts = []
    for title, fname in files:
        content = _read_safe(os.path.join(OUTPUT_DIR, fname))
        parts.append(f"### {title}\n```\n{content}\n```")
    return "\n\n".join(parts)


def _extract_json(text: str) -> dict:
    for pat in [r"```json\s*([\s\S]+?)\s*```", r"```\s*([\s\S]+?)\s*```", r"\{[\s\S]+\}"]:
        m = re.search(pat, text)
        if m:
            try:
                raw = m.group(1) if "```" in pat else m.group(0)
                return json.loads(raw)
            except json.JSONDecodeError:
                continue
    raise ValueError("No valid JSON found in response")


def _validate(cfg: dict) -> dict:
    d = V5_DEFAULT.copy()
    sl = float(cfg.get("sl_mult", d["sl_mult"]))
    sl = max(0.5, min(5.0, sl))
    tp = float(cfg.get("tp_mult", d["tp_mult"]))
    tp = max(sl + 0.5, min(10.0, tp))

    ah = cfg.get("active_hours", d["active_hours"])
    if isinstance(ah, (list, tuple)) and len(ah) == 2:
        h0 = max(0, min(23, int(ah[0])))
        h1 = max(h0 + 1, min(23, int(ah[1])))
    else:
        h0, h1 = d["active_hours"]

    return {
        "sl_mult":        sl,
        "tp_mult":        tp,
        "active_hours":   [h0, h1],
        "rsi_ob":         max(60.0, min(90.0, float(cfg.get("rsi_ob",  d["rsi_ob"])))),
        "rsi_os":         max(10.0, min(40.0, float(cfg.get("rsi_os",  d["rsi_os"])))),
        "min_atr_pct":    max(0.001, min(0.02, float(cfg.get("min_atr_pct", d["min_atr_pct"])))),
        "use_garch_filter": bool(cfg.get("use_garch_filter", d["use_garch_filter"])),
        "commission":     max(0.0, min(0.005, float(cfg.get("commission", d["commission"])))),
        "slippage":       max(0.0, min(0.005, float(cfg.get("slippage",   d["slippage"])))),
        "risk_per_trade": max(0.005, min(0.05, float(cfg.get("risk_per_trade", d["risk_per_trade"])))),
        "rationale":      str(cfg.get("rationale", d["rationale"])),
        "source":         "agent",
    }


def run_agent() -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("  [agent_strategy] ANTHROPIC_API_KEY not set — using V5 defaults.")
        return {**V5_DEFAULT, "source": "default"}

    try:
        import anthropic
    except ImportError:
        print("  [agent_strategy] 'anthropic' not installed — using V5 defaults.")
        print("  Install with: pip install anthropic")
        return {**V5_DEFAULT, "source": "default"}

    print("  [agent_strategy] Building analysis context...")
    context = _build_context()

    user_msg = (
        "Analyse the BTC/USD statistical results and return the optimal strategy "
        "configuration JSON.\n\n"
        + context
        + "\n\nReturn ONLY the JSON object, no other text."
    )

    client = anthropic.Anthropic(api_key=api_key)
    print("  [agent_strategy] Calling claude-opus-4-7 with adaptive thinking...")

    try:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_msg,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            ],
        )

        text_out = next(
            (b.text for b in response.content if b.type == "text"), ""
        )
        if not text_out:
            raise ValueError("Empty text response from Claude")

        usage = response.usage
        print(
            f"  [agent_strategy] Tokens in={usage.input_tokens} "
            f"out={usage.output_tokens}"
            + (
                f" cache_read={usage.cache_read_input_tokens}"
                if getattr(usage, "cache_read_input_tokens", 0)
                else ""
            )
        )

        raw = _extract_json(text_out)
        return _validate(raw)

    except Exception as exc:
        print(f"  [agent_strategy] API error: {exc}")
        print("  [agent_strategy] Falling back to V5 defaults.")
        return {**V5_DEFAULT, "source": "default_fallback"}


def main():
    print("=" * 60)
    print("  AGENT STRATEGY — Analisi e configurazione ottimale")
    print("=" * 60)

    cfg = run_agent()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "agent_strategy_config.json")
    with open(out_path, "w") as f:
        json.dump(cfg, f, indent=2)

    print(f"\n  Config salvata: {out_path}")
    print(f"\n  Parametri strategia suggeriti:")
    print(f"    SL multiplier   : {cfg['sl_mult']:.2f}×ATR")
    print(f"    TP multiplier   : {cfg['tp_mult']:.2f}×ATR")
    ah = cfg["active_hours"]
    print(f"    Ore attive (UTC): {ah[0]:02d}:00 – {ah[1]:02d}:00")
    print(f"    RSI overbought  : {cfg['rsi_ob']:.0f}")
    print(f"    RSI oversold    : {cfg['rsi_os']:.0f}")
    print(f"    Min ATR%%        : {cfg['min_atr_pct']:.4f}")
    print(f"    GARCH filter    : {cfg['use_garch_filter']}")
    print(f"    Commission/side : {cfg['commission']*100:.3f}%%")
    print(f"    Slippage/side   : {cfg['slippage']*100:.3f}%%")
    print(f"    Risk/trade      : {cfg['risk_per_trade']*100:.1f}%%")
    print(f"    Source          : {cfg['source']}")
    print(f"\n  Rationale: {cfg['rationale']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
