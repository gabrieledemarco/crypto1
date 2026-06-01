#!/usr/bin/env python3
"""
scripts/migrate_strategy_types.py
=================================
Migra le strategie esistenti nel DB aggiornando il campo strategy_type
con il valore corretto (archetype per vibe_loop, inferito per vibe_v2).

Usage:
    cd /workspace/project
    python scripts/migrate_strategy_types.py [--dry-run] [--batch-size 100]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.db import get_conn

# Mappatura archetype index -> nome (da strategies.py)
_ARCHETYPES = [
    "ema_cross_fast",       # 0
    "ema_cross_rsi",        # 1
    "rsi_reversion",        # 2
    "rsi_trend",            # 3
    "bb_reversion",         # 4
    "macd_cross",           # 5
    "donchian_20",          # 6
    "donchian_10_trend",    # 7
    "momentum_5bar",        # 8
    "vwap_reversion",       # 9
    "bb_squeeze",           # 10
    "adaptive_regime",      # 11
    "ema_scalp_3_8",        # 12
    "vwap_scalp",           # 13
    "order_flow_imbalance", # 14
    "rsi_fast_7",           # 15
    "bb_tight_scalp",       # 16
    "volume_breakout",      # 17
    "tick_direction_momentum",  # 18
    "spread_capture",      # 19
]

# Pattern per estrarre archetype index da nome vibe_loop
# Pattern: vibe_XXX_TF_TICKER dove XXX è il numero di iterazione (1-based)
_VIBE_LOOP_PATTERN = re.compile(r"^vibe_(\d+)_(\w+)_(.+)$")

# Strategie Vibe_v2: mappatura basata su pattern nel codice
_VIBE_V2_CODE_PATTERNS = {
    r"ema_cross|EMA.*fast.*slow|fast.*ema.*slow": "ema_cross_fast",
    r"rsi.*<.*\d+|rsi.*reversion|overbought.*oversold": "rsi_reversion",
    r"bollinger|BB.*lower|upper.*band": "bb_reversion",
    r"macd.*cross|MACD.*signal": "macd_cross",
    r"donchian|breakout.*high.*low": "donchian_20",
    r"momentum.*\d+.*bar|ret.*\d+": "momentum_5bar",
    r"vwap.*reversion|de.*<.*\-": "vwap_reversion",
    r"squeeze|bw.*<.*quantile": "bb_squeeze",
    r"adaptive|regime.*switch": "adaptive_regime",
}


def extract_archetype_from_vibe_loop_name(name: str) -> str | None:
    """Estrae l'archetype name dal nome di una strategia vibe_loop."""
    match = _VIBE_LOOP_PATTERN.match(name)
    if not match:
        return None
    iteration = int(match.group(1))
    # Calcola archetype index come in get_archetype()
    arch_idx = (iteration - 1) % len(_ARCHETYPES)
    return _ARCHETYPES[arch_idx]


def infer_strategy_type_from_code(code: str) -> str | None:
    """Prova a inferire il strategy_type dal codice."""
    if not code:
        return None
    for pattern, archetype in _VIBE_V2_CODE_PATTERNS.items():
        if re.search(pattern, code, re.IGNORECASE):
            return archetype
    return None


def migrate_strategies(dry_run: bool = True, batch_size: int = 100) -> dict:
    """Migra tutte le strategie con strategy_type generico."""
    conn = get_conn()
    
    # Trova tutte le strategie da migrare
    rows = conn.execute(
        "SELECT id, name, strategy_type, config, code FROM strategies "
        "WHERE strategy_type IN ('pipeline', 'vibe_v2', 'vibe_loop', 'unknown')"
    ).fetchall()
    
    results = {
        "total": len(rows),
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "details": [],
    }
    
    for row in rows:
        sid, name, current_type, config_json, code = row
        new_type = None
        reason = ""
        
        # Determina il nuovo strategy_type
        if current_type == "vibe_loop" or name.startswith("vibe_"):
            # Per vibe_loop: estrai dall'iteration number
            new_type = extract_archetype_from_vibe_loop_name(name)
            reason = "extracted from iteration number"
        elif current_type == "vibe_v2" or name.startswith("vibev2_"):
            # Per vibe_v2: prova a inferire dal codice
            new_type = infer_strategy_type_from_code(code)
            if new_type:
                reason = "inferred from code pattern"
            else:
                # Fallback: prova a estrarre dal brief in config
                try:
                    if config_json:
                        cfg = json.loads(config_json)
                        if "evaluation" in cfg and "strategy_type" not in cfg["evaluation"]:
                            # Il brief potrebbe essere in evaluation.strdict
                            pass
                except Exception:
                    pass
                reason = "could not infer from code"
        elif current_type in ("pipeline", "unknown"):
            # Per altri tipi generici: prova entrambi i metodi
            new_type = extract_archetype_from_vibe_loop_name(name)
            if not new_type:
                new_type = infer_strategy_type_from_code(code)
            reason = "fallback inference"
        
        if new_type and new_type != current_type:
            if dry_run:
                print(f"  [DRY-RUN] Would update: {name}")
                print(f"    {current_type} -> {new_type} ({reason})")
                results["updated"] += 1
            else:
                try:
                    conn.execute(
                        "UPDATE strategies SET strategy_type=? WHERE id=?",
                        [new_type, sid],
                    )
                    print(f"  [OK] Updated: {name} -> {new_type}")
                    results["updated"] += 1
                except Exception as e:
                    print(f"  [FAIL] {name}: {e}")
                    results["failed"] += 1
            results["details"].append({
                "id": sid,
                "name": name,
                "old": current_type,
                "new": new_type,
                "reason": reason,
            })
        else:
            results["skipped"] += 1
            if new_type == current_type:
                print(f"  [SKIP] {name}: already correct ({new_type})")
            else:
                print(f"  [SKIP] {name}: could not determine new type")
    
    return results


def print_summary(results: dict) -> None:
    """Stampa un riepilogo della migrazione."""
    print(f"\n{'='*60}")
    print("  MIGRATION SUMMARY")
    print(f"{'='*60}")
    print(f"  Total strategies checked : {results['total']}")
    print(f"  Updated                 : {results['updated']}")
    print(f"  Skipped (no change)     : {results['skipped']}")
    print(f"  Failed                 : {results['failed']}")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate strategy types in DB")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Show changes without applying them (default: True)")
    parser.add_argument("--apply", action="store_true",
                        help="Actually apply changes (overrides dry-run)")
    parser.add_argument("--batch-size", type=int, default=100,
                        help="Batch size for processing")
    args = parser.parse_args()
    
    dry_run = not args.apply
    
    print(f"\n{'='*60}")
    print(f"  STRATEGY TYPE MIGRATION")
    print(f"  Mode: {'DRY-RUN' if dry_run else 'APPLY'}")
    print(f"{'='*60}\n")
    
    results = migrate_strategies(dry_run=dry_run, batch_size=args.batch_size)
    print_summary(results)
    
    if dry_run:
        print("  Use --apply to actually update the database.")
    
    if results["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()