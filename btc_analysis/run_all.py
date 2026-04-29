"""
Entry point — esegue tutta la pipeline di analisi in sequenza.
"""

import subprocess, sys, os

scripts = [
    "01_data_download.py",
    "02_timeseries_analysis.py",
    "03_pattern_analysis.py",
    "04_strategy.py",
    "05_report.py",
]

base = os.path.dirname(__file__)

for script in scripts:
    path = os.path.join(base, script)
    print(f"\n{'━'*60}")
    print(f"  RUNNING: {script}")
    print(f"{'━'*60}")
    result = subprocess.run([sys.executable, path], capture_output=False)
    if result.returncode != 0:
        print(f"\n  [ERRORE] {script} terminato con codice {result.returncode}")
        sys.exit(result.returncode)

print(f"\n{'━'*60}")
print("  PIPELINE COMPLETATA — output/ contiene tutti i risultati")
print(f"{'━'*60}")
