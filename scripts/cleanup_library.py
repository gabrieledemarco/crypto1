"""
Cleanup Library: call POST /strategies/prune?min_sharpe=X
Writes result to /tmp/cleanup_result.json.
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

# Write placeholder immediately so commit step always has a file
result = {"min_sharpe": min_sharpe, "status": "started", "total": 0,
          "deleted": 0, "kept": 0, "kept_strategies": [], "error": None}
os.makedirs("/tmp", exist_ok=True)
with open("/tmp/cleanup_result.json", "w") as f:
    json.dump(result, f, indent=2)

url = f"{API_BASE}/strategies/prune?min_sharpe={min_sharpe}"
print(f"POST {url}")
try:
    req = urllib.request.Request(url, data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read()
        print(f"Response status: {r.status}  size: {len(body)} bytes")
        data = json.loads(body)
except urllib.error.HTTPError as e:
    msg = f"HTTP {e.code}: {e.reason}  body={e.read()[:500]}"
    print(f"FAILED: {msg}")
    result.update({"status": "prune_failed", "error": msg})
    with open("/tmp/cleanup_result.json", "w") as f:
        json.dump(result, f, indent=2)
    sys.exit(1)
except Exception as e:
    msg = traceback.format_exc()
    print(f"FAILED: {msg}")
    result.update({"status": "prune_failed", "error": str(e)})
    with open("/tmp/cleanup_result.json", "w") as f:
        json.dump(result, f, indent=2)
    sys.exit(1)

result.update({
    "status": "complete",
    "total":   data.get("total", 0),
    "deleted": data.get("deleted", 0),
    "kept":    data.get("kept", 0),
    "kept_strategies": data.get("kept_strategies", []),
    "error": None,
})
with open("/tmp/cleanup_result.json", "w") as f:
    json.dump(result, f, indent=2)
print(f"\nDone: total={result['total']}  deleted={result['deleted']}  kept={result['kept']}")
for s in result["kept_strategies"]:
    print(f"  KEEP {s['id']}  {s['name']:<42}  sharpe={s.get('sharpe')}")
