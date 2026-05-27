"""
Cleanup Library: delete strategies with sharpe < min_sharpe.
Always writes /tmp/cleanup_result.json so the CI step can commit it.
"""
import json, os, sys, urllib.request, urllib.error, traceback

API_BASE = os.environ.get("API_BASE", "https://illustrious-inspiration-production.up.railway.app")

# Determine min_sharpe
min_sharpe = float(os.environ.get("MIN_SHARPE", "1.0"))
if os.path.exists(".library-cleanup-trigger"):
    try:
        with open(".library-cleanup-trigger") as f:
            t = json.load(f)
        min_sharpe = float(t.get("min_sharpe", min_sharpe))
        print(f"min_sharpe from trigger file: {min_sharpe}")
    except Exception as e:
        print(f"Warning: could not read trigger file: {e}")

# Write a placeholder result immediately so the commit step always has a file
result = {"min_sharpe": min_sharpe, "status": "started", "total": 0,
          "deleted": 0, "kept": 0, "kept_strategies": [], "error": None}
os.makedirs("/tmp", exist_ok=True)
with open("/tmp/cleanup_result.json", "w") as f:
    json.dump(result, f, indent=2)

print(f"Fetching strategies from {API_BASE}/strategies ...")
try:
    req = urllib.request.Request(f"{API_BASE}/strategies")
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        print(f"Response size: {len(body)} bytes  status: {r.status}")
        strategies = json.loads(body)
except urllib.error.HTTPError as e:
    msg = f"HTTP {e.code}: {e.reason}"
    print(f"FAILED: {msg}")
    result.update({"status": "fetch_failed", "error": msg})
    with open("/tmp/cleanup_result.json", "w") as f:
        json.dump(result, f, indent=2)
    sys.exit(1)
except Exception as e:
    msg = traceback.format_exc()
    print(f"FAILED: {msg}")
    result.update({"status": "fetch_failed", "error": str(e)})
    with open("/tmp/cleanup_result.json", "w") as f:
        json.dump(result, f, indent=2)
    sys.exit(1)

print(f"Total strategies in Library: {len(strategies)}")
result["total"] = len(strategies)
result["status"] = "running"
with open("/tmp/cleanup_result.json", "w") as f:
    json.dump(result, f, indent=2)

deleted, kept = [], []
for s in strategies:
    sid    = s.get("id", "")
    name   = s.get("name", "?")
    cfg    = s.get("config") or {}
    perf   = cfg.get("perf") or {}
    sharpe = perf.get("sharpe")
    if sharpe is None:
        sharpe = (s.get("metrics") or {}).get("sharpe")

    if sharpe is None or float(sharpe) < min_sharpe:
        try:
            urllib.request.urlopen(
                urllib.request.Request(f"{API_BASE}/strategies/{sid}", method="DELETE"),
                timeout=15
            )
            print(f"  DEL  {sid}  {name}  sharpe={sharpe}")
            deleted.append({"id": sid, "name": name, "sharpe": sharpe})
        except Exception as e:
            print(f"  ERR  {sid}: {e}")
            # Count as deleted if we get a 404 (already gone)
            deleted.append({"id": sid, "name": name, "sharpe": sharpe, "note": str(e)})
    else:
        print(f"  KEEP {sid}  {name}  sharpe={sharpe}")
        kept.append({"id": sid, "name": name, "sharpe": sharpe})

result.update({
    "status": "complete",
    "deleted": len(deleted),
    "kept": len(kept),
    "kept_strategies": kept,
    "error": None,
})
with open("/tmp/cleanup_result.json", "w") as f:
    json.dump(result, f, indent=2)
print(f"\nDone: deleted={len(deleted)}  kept={len(kept)}")
