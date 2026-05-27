"""
Cleanup Library: delete strategies with sharpe < min_sharpe.
Reads min_sharpe from .library-cleanup-trigger (push) or env var MIN_SHARPE.
Writes result to /tmp/cleanup_result.json.
"""
import json, os, sys, urllib.request

API_BASE = os.environ.get("API_BASE", "https://illustrious-inspiration-production.up.railway.app")

# Determine min_sharpe
min_sharpe = float(os.environ.get("MIN_SHARPE", "1.0"))
if os.path.exists(".library-cleanup-trigger"):
    try:
        with open(".library-cleanup-trigger") as f:
            t = json.load(f)
        min_sharpe = float(t.get("min_sharpe", min_sharpe))
    except Exception:
        pass

print(f"Fetching strategies (keeping sharpe >= {min_sharpe})...")
try:
    with urllib.request.urlopen(
        urllib.request.Request(f"{API_BASE}/strategies"), timeout=30
    ) as r:
        strategies = json.loads(r.read())
except Exception as e:
    print(f"FAILED to fetch strategies: {e}")
    sys.exit(1)

print(f"Total in Library: {len(strategies)}")

deleted, kept = [], []
for s in strategies:
    sid   = s.get("id", "")
    name  = s.get("name", "?")
    cfg   = s.get("config") or {}
    perf  = cfg.get("perf") or {}
    sharpe = perf.get("sharpe")
    if sharpe is None:
        sharpe = (s.get("metrics") or {}).get("sharpe")

    if sharpe is None or float(sharpe) < min_sharpe:
        try:
            urllib.request.urlopen(
                urllib.request.Request(f"{API_BASE}/strategies/{sid}", method="DELETE"),
                timeout=10
            )
            print(f"  DEL {sid}  {name}  sharpe={sharpe}")
            deleted.append({"id": sid, "name": name, "sharpe": sharpe})
        except Exception as e:
            print(f"  ERR {sid}: {e}")
    else:
        print(f"  KEEP {sid}  {name}  sharpe={sharpe}")
        kept.append({"id": sid, "name": name, "sharpe": sharpe})

result = {
    "min_sharpe": min_sharpe,
    "total": len(strategies),
    "deleted": len(deleted),
    "kept": len(kept),
    "kept_strategies": kept,
}
os.makedirs("/tmp", exist_ok=True)
with open("/tmp/cleanup_result.json", "w") as f:
    json.dump(result, f, indent=2)
print(f"\nDone: deleted={len(deleted)}  kept={len(kept)}")
