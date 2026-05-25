"""
Seed the Railway Library with pipeline strategies via POST /strategies.
Works with any Railway deployment — no pipeline endpoint required.
"""
import json
import sys
import os
import urllib.request
import urllib.error

API_BASE = os.environ.get("API_BASE", "https://illustrious-inspiration-production.up.railway.app")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.strategies import get_archetype

TICKERS = [
    ("BTC-USD", "1h"),
    ("ETH-USD", "1h"),
    ("SOL-USD", "1h"),
]


def post_json(url, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def put_json(url):
    req = urllib.request.Request(url, data=b"", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def check_health():
    try:
        req = urllib.request.Request(f"{API_BASE}/health")
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read())
            print(f"Railway health: {d}")
            return True
    except Exception as e:
        print(f"Railway health check failed: {e}")
        return False


def main():
    print(f"Seeding Library at {API_BASE}")

    if not check_health():
        print("ERROR: Railway API is not reachable")
        sys.exit(1)

    created = []
    for idx, (ticker, tf) in enumerate(TICKERS, 1):
        arch_name, code, sl, tp = get_archetype(idx)
        name = f"pipe_001_{tf}_{ticker.replace('-', '_')}"

        config = {
            "ticker": ticker,
            "timeframe": tf,
            "sl_mult": sl,
            "tp_mult": tp,
            "active_hours": [6, 22],
            "commission": 0.0004,
            "slippage": 0.0001,
            "risk_per_trade": 0.01,
            "direction": "ALL",
        }

        payload = {
            "name": name,
            "strategy_type": "pipeline",
            "config": config,
            "code": code,
            "status": "live",
        }

        try:
            result = post_json(f"{API_BASE}/strategies", payload)
            sid = result["id"]
            print(f"  Created: {ticker} → sid={sid}  arch={arch_name}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  ERROR creating {ticker}: HTTP {e.code} — {body}")
            continue
        except Exception as e:
            print(f"  ERROR creating {ticker}: {e}")
            continue

        try:
            put_json(f"{API_BASE}/strategies/{sid}/star")
            print(f"  Starred: {sid}")
        except Exception as e:
            print(f"  Warning: could not star {sid}: {e}")

        created.append({"ticker": ticker, "tf": tf, "sid": sid, "arch": arch_name})

    print(f"\nDone — created {len(created)}/{len(TICKERS)} strategies")
    for s in created:
        print(f"  * {s['ticker']} {s['tf']}  sid={s['sid']}  arch={s['arch']}")

    if created:
        print("\nStrategies are now visible in the Library screen.")
        with open("/tmp/seed_result.json", "w") as f:
            json.dump({"status": "ok", "created": created}, f, indent=2)
    else:
        print("\nERROR: No strategies were created")
        sys.exit(1)


if __name__ == "__main__":
    main()
