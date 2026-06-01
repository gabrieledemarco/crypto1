"""
/strategies router — library CRUD
"""
import json, uuid, traceback as _tb
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from api.db import get_conn
from api.models import StrategyCreate

router = APIRouter()


@router.get("")
def list_strategies():
    try:
        conn = get_conn()
        rows = conn.execute("""
            SELECT id, name, strategy_type, config,
                   CASE WHEN code IS NOT NULL AND length(code) > 10 THEN true ELSE false END AS has_code,
                   starred, status, run_ref, created_at
            FROM strategies
            ORDER BY starred DESC, created_at DESC
        """).fetchall()

        result = []
        for r in rows:
            cfg = {}
            try:
                cfg = json.loads(r[3]) if r[3] else {}
            except Exception:
                pass

            perf = cfg.get("perf") or {}

            def _safe_float(v, default=0.0):
                if isinstance(v, dict):
                    v = v.get("point", default)
                try:
                    return float(v or default)
                except (TypeError, ValueError):
                    return float(default)

            metrics = {
                "sharpe": round(_safe_float(perf.get("sharpe", 0)), 3),
                "cagr":   round(_safe_float(perf.get("cagr_pct", 0)), 2),
                "maxDD":  round(_safe_float(perf.get("max_dd", perf.get("dd", 0))), 2),
                "pf":     round(_safe_float(perf.get("profit_factor", 0)), 2),
                "trades": int(_safe_float(perf.get("n_trades", 0))),
            }

            result.append({
                "id":       r[0],
                "name":     r[1],
                "strategy": r[2] or "vibe_loop",
                "author":   "",
                "created":  str(r[8]),
                "tags":     _tags(cfg),
                "starred":  bool(r[5]),
                "status":   r[6] or "research",
                "metrics":  metrics,
                "desc":     "",
                "runRef":   r[7],
                "config":   cfg,
                "has_code": bool(r[4]),
            })
        return result
    except Exception as exc:
        detail = _tb.format_exc()
        return JSONResponse(status_code=500, content={"detail": detail})


@router.get("/{strategy_id}")
def get_strategy(strategy_id: str):
    """Return full strategy including code — used when loading into Vibe/Setup."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, name, strategy_type, config, code, starred, status, run_ref, created_at "
        "FROM strategies WHERE id=?",
        [strategy_id]
    ).fetchone()
    if not row:
        raise HTTPException(404, "Strategy not found")
    cfg = {}
    try:
        cfg = json.loads(row[3]) if row[3] else {}
    except Exception:
        pass
    return {
        "id":       row[0],
        "name":     row[1],
        "strategy": row[2] or "vibe_loop",
        "config":   cfg,
        "code":     row[4] or "",
        "has_code": bool(row[4] and len(row[4]) > 10),
        "starred":  bool(row[5]),
        "status":   row[6] or "research",
        "runRef":   row[7],
        "created":  str(row[8]),
    }


def _best_metrics(metrics_dict: dict) -> dict:
    """Return the metrics dict with the highest Sharpe from a version map."""
    if not metrics_dict:
        return {}
    if "sharpe_ratio" in metrics_dict or "sharpe" in metrics_dict:
        return metrics_dict
    best, best_sharpe = {}, float("-inf")
    for v in metrics_dict.values():
        if isinstance(v, dict):
            s = float(v.get("sharpe_ratio", v.get("sharpe", float("-inf"))) or float("-inf"))
            if s > best_sharpe:
                best_sharpe, best = s, v
    return best


def _tags(cfg: dict) -> list:
    tags = []
    ticker = cfg.get("ticker", "")
    tf     = cfg.get("timeframe", "")
    if ticker:
        tags.append(ticker)
    if tf:
        tags.append(tf)
    dirn = cfg.get("direction", "")
    if dirn and dirn != "ALL":
        tags.append(dirn.lower())
    return tags



@router.post("")
def create_strategy(body: StrategyCreate):
    sid = str(uuid.uuid4())[:8]
    conn = get_conn()
    conn.execute(
        "INSERT INTO strategies (id, name, strategy_type, config, code, status) VALUES (?,?,?,?,?,?)",
        [sid, body.name, body.strategy_type, json.dumps(body.config), body.code, body.status]
    )
    conn.commit()
    return {"id": sid, "name": body.name}


@router.put("/{strategy_id}/star")
def toggle_star(strategy_id: str):
    conn = get_conn()
    row = conn.execute("SELECT starred FROM strategies WHERE id=?", [strategy_id]).fetchone()
    if not row:
        raise HTTPException(404, "Strategy not found")
    new_val = not bool(row[0])
    conn.execute("UPDATE strategies SET starred=? WHERE id=?", [new_val, strategy_id])
    conn.commit()
    return {"id": strategy_id, "starred": new_val}


@router.delete("/{strategy_id}")
def delete_strategy(strategy_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM strategies WHERE id=?", [strategy_id])
    conn.commit()
    return {"deleted": strategy_id}


@router.post("/prune")
def prune_strategies(min_sharpe: float = 0.0):
    """Delete all strategies whose config.perf.sharpe < min_sharpe."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, config FROM strategies"
    ).fetchall()

    deleted, kept = [], []
    for sid, name, config_raw in rows:
        cfg = {}
        try:
            cfg = json.loads(config_raw) if config_raw else {}
        except Exception:
            pass
        sharpe = (cfg.get("perf") or {}).get("sharpe")
        if sharpe is None:
            sharpe = cfg.get("sharpe")

        if sharpe is None or float(sharpe) < min_sharpe:
            conn.execute("DELETE FROM strategies WHERE id=?", [sid])
            deleted.append({"id": sid, "name": name, "sharpe": sharpe})
        else:
            kept.append({"id": sid, "name": name, "sharpe": sharpe})

    if deleted:
        conn.commit()
    return {
        "min_sharpe": min_sharpe,
        "total":   len(rows),
        "deleted": len(deleted),
        "kept":    len(kept),
        "kept_strategies": kept,
    }


@router.post("/migrate-types")
def migrate_strategy_types(dry_run: bool = True):
    """Migrate strategy_type from generic names to archetype-based names.
    
    Args:
        dry_run: If True, only show what would change. If False, apply changes.
    
    Returns:
        Summary of migration results.
    """
    conn = get_conn()
    
    # Archetypes mapping (from strategies.py)
    ARCHETYPES = [
        "ema_cross_fast", "ema_cross_rsi", "rsi_reversion", "rsi_trend",
        "bb_reversion", "macd_cross", "donchian_20", "donchian_10_trend",
        "momentum_5bar", "vwap_reversion", "bb_squeeze", "adaptive_regime",
        "ema_scalp_3_8", "vwap_scalp", "order_flow_imbalance", "rsi_fast_7",
        "bb_tight_scalp", "volume_breakout", "tick_direction_momentum", "spread_capture",
    ]
    
    import re
    VIBE_LOOP_PATTERN = re.compile(r"^vibe_(\d+)_(\w+)_(.+)$")
    
    # Strategy types that need migration
    GENERIC_TYPES = ("pipeline", "vibe_v2", "vibe_loop", "unknown")
    
    # Get all strategies that need migration
    rows = conn.execute(
        "SELECT id, name, strategy_type, config, code FROM strategies "
        "WHERE strategy_type IN (?, ?, ?, ?)",
        list(GENERIC_TYPES)
    ).fetchall()
    
    results = {
        "total": len(rows),
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "details": [],
    }
    
    for sid, name, current_type, config_json, code in rows:
        new_type = None
        reason = ""
        
        # Determine new strategy_type
        if current_type == "vibe_loop" or name.startswith("vibe_"):
            # For vibe_loop: extract from iteration number
            match = VIBE_LOOP_PATTERN.match(name)
            if match:
                iteration = int(match.group(1))
                arch_idx = (iteration - 1) % len(ARCHETYPES)
                new_type = ARCHETYPES[arch_idx]
                reason = "derived from vibe_loop iteration"
        elif current_type == "vibe_v2" or name.startswith("vibev2_"):
            # For vibe_v2: try to infer from config brief
            try:
                if config_json:
                    cfg = json.loads(config_json)
                    brief = cfg.get("evaluation", {}).get("brief", cfg.get("brief", {}))
                    if isinstance(brief, dict):
                        strategy_type = brief.get("strategy_type")
                        if strategy_type:
                            new_type = strategy_type
                            reason = "from Orchestrator brief"
            except Exception:
                pass
            if not new_type:
                reason = "could not determine from config"
        elif current_type in GENERIC_TYPES:
            # For other generic types: try vibe_loop pattern first
            match = VIBE_LOOP_PATTERN.match(name)
            if match:
                iteration = int(match.group(1))
                arch_idx = (iteration - 1) % len(ARCHETYPES)
                new_type = ARCHETYPES[arch_idx]
                reason = "derived from name pattern"
            else:
                reason = "no pattern match"
        
        if new_type and new_type != current_type:
            results["details"].append({
                "id": sid,
                "name": name,
                "old": current_type,
                "new": new_type,
                "reason": reason,
            })
            
            if not dry_run:
                try:
                    conn.execute(
                        "UPDATE strategies SET strategy_type=? WHERE id=?",
                        [new_type, sid]
                    )
                    results["updated"] += 1
                except Exception as e:
                    results["failed"] += 1
                    results["details"][-1]["error"] = str(e)
            else:
                results["updated"] += 1
        else:
            results["skipped"] += 1
            results["details"].append({
                "id": sid,
                "name": name,
                "old": current_type,
                "new": current_type,
                "reason": reason or "no change needed",
            })
    
    if not dry_run and results["updated"] > 0:
        conn.commit()
    
    return {
        "dry_run": dry_run,
        **results,
    }


@router.post("/promote-robust")
def promote_robust(min_sharpe: float = 1.0):
    """Star + set status='live' on every strategy with Sharpe >= min_sharpe.
    Safe to call repeatedly — idempotent."""
    conn = get_conn()
    rows = conn.execute("SELECT id, name, config, starred, status FROM strategies").fetchall()
    promoted, already = [], []
    to_promote_ids: list[str] = []
    for sid, name, config_raw, starred, status in rows:
        cfg = {}
        try:
            cfg = json.loads(config_raw) if config_raw else {}
        except Exception:
            pass
        perf = cfg.get("perf") or {}
        sharpe = float(perf.get("sharpe", perf.get("sharpe_ratio", 0)) or 0)
        if sharpe >= min_sharpe:
            if bool(starred) and status == "live":
                already.append({"id": sid, "name": name, "sharpe": sharpe})
            else:
                to_promote_ids.append(sid)
                promoted.append({"id": sid, "name": name, "sharpe": sharpe})

    if to_promote_ids:
        placeholders = ",".join("?" * len(to_promote_ids))
        conn.execute(
            f"UPDATE strategies SET starred=TRUE, status='live' WHERE id IN ({placeholders})",
            to_promote_ids,
        )
        conn.commit()
    return {
        "min_sharpe": min_sharpe,
        "promoted":  len(promoted),
        "already_ok": len(already),
        "strategies": promoted + already,
    }
