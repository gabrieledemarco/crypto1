"""
Integration test: verifies the full backfill → auto-stats pipeline.

Tests:
1. After backfill, _meta.json + parquet written → list_assets() returns ticker
2. load_and_resample() returns data from Parquet for that ticker
3. AssetsScreen SSE handler logic auto-selects ticker on phase=done
"""
import json
import pathlib
import sys
import tempfile

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(REPO))


def _make_ohlcv(n: int = 200) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
    rng = np.random.default_rng(42)
    close = 50000.0 + rng.normal(0, 200, n).cumsum()
    return pd.DataFrame({
        "Open":   close - 10,
        "High":   close + 20,
        "Low":    close - 20,
        "Close":  close,
        "Volume": rng.integers(1, 100, n).astype(float),
    }, index=idx)


# ── Test 1: _meta.json + parquet make ticker visible in list_assets ──────────

def test_meta_json_makes_ticker_visible(tmp_path):
    import engine.storage.parquet_store as ps_mod
    original = ps_mod.DATA_DIR
    ps_mod.DATA_DIR = tmp_path
    try:
        sym = ps_mod._normalise_symbol("BTC-USD")
        parquet_dir = tmp_path / "crypto" / sym
        parquet_dir.mkdir(parents=True)

        # Write a parquet file (backfill output)
        df = _make_ohlcv(200)
        df.to_parquet(parquet_dir / "2024_01.parquet")

        # Write _meta.json (written by _run_backfill_thread on success)
        (parquet_dir / "_meta.json").write_text(
            json.dumps({"ticker": "BTC-USD", "asset_class": "crypto"})
        )

        # Import list_assets and patch DATA_DIR inside that module too
        import api.routers.assets as assets_mod
        original_assets = getattr(assets_mod, "DATA_DIR", None)

        # list_assets imports DATA_DIR from parquet_store at call-time via:
        #   from engine.storage.parquet_store import DATA_DIR, list_available
        # So patching ps_mod.DATA_DIR is sufficient since it's a module-level import
        results = assets_mod.list_assets()
        tickers = [r["ticker"] for r in results]
        assert "BTC-USD" in tickers, f"BTC-USD not in asset list: {tickers}"
        entry = next(r for r in results if r["ticker"] == "BTC-USD")
        assert entry["source"] == "m1:1m"
        print(f"  PASS: BTC-USD visible with source={entry['source']}, interval={entry['interval']}")
    finally:
        ps_mod.DATA_DIR = original


# ── Test 2: load_and_resample returns data from Parquet ──────────────────────

def test_load_series_from_parquet(tmp_path):
    import engine.storage.parquet_store as ps_mod
    original = ps_mod.DATA_DIR
    ps_mod.DATA_DIR = tmp_path
    try:
        sym = ps_mod._normalise_symbol("ETH-USD")
        parquet_dir = tmp_path / "crypto" / sym
        parquet_dir.mkdir(parents=True)
        df = _make_ohlcv(500)
        df.to_parquet(parquet_dir / "2024_01.parquet")

        result = ps_mod.load_and_resample(
            "crypto", "ETH-USD",
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-31"),
            interval="1h",
        )
        assert not result.empty, "load_and_resample returned empty DataFrame"
        assert "Close" in result.columns
        print(f"  PASS: load_and_resample returned {len(result)} bars at 1h")
    finally:
        ps_mod.DATA_DIR = original


# ── Test 3: SSE handler logic auto-selects ticker on phase=done ──────────────

def test_sse_done_sets_selected_ticker():
    """
    Python translation of the SSE onmessage handler in AssetsScreen.tsx.
    Verifies that on phase='done', selectedTicker and viewInterval are updated.
    """
    state = {
        "selectedTicker": None,
        "viewInterval": "1d",
        "bfRunning": True,
        "fetchTicker": "ETH-USD",
        "bfInterval": "1h",
        "_assets_invalidated": False,
    }

    def handle_sse_event(ev: dict):
        # Mirrors lines 380-389 of AssetsScreen.tsx
        if ev.get("phase") in ("done", "error"):
            state["bfRunning"] = False
            if ev["phase"] == "done":
                state["_assets_invalidated"] = True   # qc.invalidateQueries(["assets"])
                if state["fetchTicker"]:
                    state["selectedTicker"] = state["fetchTicker"]
                    state["viewInterval"] = state["bfInterval"] or "1h"

    handle_sse_event({"phase": "done", "pct": 100, "msg": "Backfill complete"})

    assert state["selectedTicker"] == "ETH-USD", (
        f"Expected selectedTicker='ETH-USD', got {state['selectedTicker']!r}"
    )
    assert state["viewInterval"] == "1h"
    assert state["bfRunning"] is False
    assert state["_assets_invalidated"] is True
    print(f"  PASS: selectedTicker='{state['selectedTicker']}', viewInterval='{state['viewInterval']}'")


# ── Test 4: SSE error does NOT auto-select ───────────────────────────────────

def test_sse_error_does_not_set_ticker():
    state = {
        "selectedTicker": None,
        "viewInterval": "1d",
        "bfRunning": True,
        "fetchTicker": "ETH-USD",
        "bfInterval": "1h",
        "_assets_invalidated": False,
    }

    def handle_sse_event(ev: dict):
        if ev.get("phase") in ("done", "error"):
            state["bfRunning"] = False
            if ev["phase"] == "done":
                state["_assets_invalidated"] = True
                if state["fetchTicker"]:
                    state["selectedTicker"] = state["fetchTicker"]
                    state["viewInterval"] = state["bfInterval"] or "1h"

    handle_sse_event({"phase": "error", "msg": "Download failed"})

    assert state["selectedTicker"] is None, "Should not auto-select on error"
    assert state["bfRunning"] is False
    assert state["_assets_invalidated"] is False
    print("  PASS: error phase does NOT set selectedTicker")


# ── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import traceback

    tests = [
        test_meta_json_makes_ticker_visible,
        test_load_series_from_parquet,
        test_sse_done_sets_selected_ticker,
        test_sse_error_does_not_set_ticker,
    ]
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        for fn in tests:
            sig = fn.__code__.co_varnames[:fn.__code__.co_argcount]
            try:
                if "tmp_path" in sig:
                    fn(tmp_path)
                else:
                    fn()
                print(f"PASS  {fn.__name__}")
            except Exception as exc:
                print(f"FAIL  {fn.__name__}: {exc}")
                traceback.print_exc()
                failures += 1

    print(f"\n{'All tests passed ✓' if not failures else f'{failures} test(s) FAILED'}")
    sys.exit(failures)
