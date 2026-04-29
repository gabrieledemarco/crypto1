"""
Entry point — esegue tutta la pipeline di analisi in sequenza.

Pipeline:
  01  Generazione dati sintetici BTC/USD (daily 10y + hourly 2y)
  02  Analisi serie storica: stazionarietà, distribuzione, ACF
  03  Pattern analysis: DOW, mensile, ora del giorno, Hurst
  04  Strategia base: backtest + grid search parametri
  05  Report testuale (aggiornato dopo ogni run avanzato)
  06  Strategia avanzata: GARCH filter + commissioni/slippage
  07  Walk-Forward Optimization (validazione OOS)
  08  Multi-asset portfolio: BTC + ETH + SOL
"""

import subprocess, sys, os

scripts = [
    ("01_data_download.py",     "Generazione dati sintetici BTC/ETH/SOL"),
    ("02_timeseries_analysis.py","Analisi serie storica"),
    ("03_pattern_analysis.py",  "Pattern analysis"),
    ("04_strategy.py",          "Strategia base + grid search"),
    ("06_enhanced_strategy.py", "GARCH filter + costi realistici"),
    ("07_walk_forward.py",      "Walk-Forward Optimization"),
    ("08_multi_asset.py",       "Portfolio multi-asset"),
    ("05_report.py",            "Generazione report finale"),
]

base = os.path.dirname(__file__)

for script, desc in scripts:
    path = os.path.join(base, script)
    print(f"\n{'━'*60}")
    print(f"  [{desc}]")
    print(f"  RUNNING: {script}")
    print(f"{'━'*60}")
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
    print(f"    {f:<45} {size/1024:>7.1f} KB")
print(f"{'━'*60}")
