"""
Entry point — esegue la pipeline completa di analisi e backtesting.

═══════════════════════════════════════════════════════════════
 FASE 1 — Download + Analisi Statistica
   01_data_download.py   Scarica dati OHLCV da Yahoo Finance
   02_analyze.py         Hurst, ACF, kurtosis, GARCH baseline,
                         best_hours_utc → analysis_report.json

 FASE 2 — Elaborazione Strategia (AI Agent)
   agent_strategy.py     Claude analizza il report statistico e
                         scrive generate_signals_agent() +
                         agent_config.json

 FASE 3 — Costruzione Feature
   03_features.py        Calcola ATR, RSI, EMA, GARCH(1,1) e
                         salva {asset}_features.parquet
                         (usato da fase 4 e 5 senza ricalcolo)

 FASE 4 — Backtest
   04_backtest.py        V1/V2/V4/V_Agent + Walk-Forward (rolling
                         window IS/OOS) + grid search SL/TP

 FASE 5 — Monte Carlo
   05_montecarlo.py      Bootstrap 10.000 sim + 4 stress scenarios
                         su trades dell'agent strategy

 REPORT
   05_report.py          Report testuale consolidato
═══════════════════════════════════════════════════════════════
"""

import subprocess, sys, os

PIPELINE = [
    # (script, descrizione, fase)
    ("01_data_download.py",  "Download dati OHLCV (Yahoo Finance)",                1),
    ("02_analyze.py",        "Analisi statistica + baseline V4",                   1),
    ("agent_strategy.py",    "AI Agent — progettazione strategia ottimale",        2),
    ("03_features.py",       "Costruzione feature (ATR, RSI, EMA, GARCH)",         3),
    ("04_backtest.py",       "Backtest V1-V4/Agent + Walk-Forward + Grid Search",  4),
    ("05_montecarlo.py",     "Monte Carlo (bootstrap + stress test)",              5),
    ("05_report.py",         "Generazione report finale",                          0),
]

PHASE_NAMES = {
    1: "FASE 1 — Download + Analisi Statistica",
    2: "FASE 2 — Elaborazione Strategia (Agent)",
    3: "FASE 3 — Costruzione Feature",
    4: "FASE 4 — Backtest",
    5: "FASE 5 — Monte Carlo",
    0: "REPORT",
}

base = os.path.dirname(__file__)
current_phase = None

for script, desc, phase in PIPELINE:
    if phase != current_phase:
        current_phase = phase
        print(f"\n{'━'*60}")
        print(f"  {PHASE_NAMES[phase]}")
        print(f"{'━'*60}")

    path = os.path.join(base, script)
    print(f"\n  ▶ {script}")
    print(f"    {desc}")
    result = subprocess.run([sys.executable, path], capture_output=False)
    if result.returncode != 0:
        print(f"\n  [ERRORE] {script} terminato con codice {result.returncode}")
        sys.exit(result.returncode)

print(f"\n{'━'*60}")
print("  PIPELINE COMPLETATA")
print("  Output files:")
output_dir = os.path.join(base, "output")
for f in sorted(os.listdir(output_dir)):
    size = os.path.getsize(os.path.join(output_dir, f))
    print(f"    {f:<50} {size/1024:>7.1f} KB")
print(f"{'━'*60}")
