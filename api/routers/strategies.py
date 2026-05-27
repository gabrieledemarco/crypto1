"""
/strategies router — library CRUD
"""
import json, uuid
from fastapi import APIRouter, HTTPException
from api.db import get_conn
from api.models import StrategyCreate

router = APIRouter()


@router.get("")
def list_strategies():
    conn = get_conn()
    # Lightweight query: no code column (heavy), metrics from config.perf (set by pipeline)
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

        # Metrics from config.perf (populated by pipeline on every saved strategy)
        perf = cfg.get("perf") or {}
        metrics = {
            "sharpe": round(float(perf.get("sharpe", 0) or 0), 3),
            "cagr":   round(float(perf.get("cagr_pct", 0) or 0), 2),
            "maxDD":  round(float(perf.get("max_dd", 0) or 0), 2),
            "pf":     round(float(perf.get("profit_factor", 0) or 0), 2),
            "trades": int(perf.get("n_trades", 0) or 0),
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
    # Flat dict (already a single metrics object)
    if "sharpe_ratio" in metrics_dict or "sharpe" in metrics_dict:
        return metrics_dict
    # Version map: {"V1 Base": {...}, "V2 +Costi": {...}, ...}
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
    return {"id": sid, "name": body.name}


@router.put("/{strategy_id}/star")
def toggle_star(strategy_id: str):
    conn = get_conn()
    row = conn.execute("SELECT starred FROM strategies WHERE id=?", [strategy_id]).fetchone()
    if not row:
        raise HTTPException(404, "Strategy not found")
    new_val = not bool(row[0])
    conn.execute("UPDATE strategies SET starred=? WHERE id=?", [new_val, strategy_id])
    return {"id": strategy_id, "starred": new_val}


@router.delete("/{strategy_id}")
def delete_strategy(strategy_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM strategies WHERE id=?", [strategy_id])
    return {"deleted": strategy_id}


@router.post("/prune")
def prune_strategies(min_sharpe: float = 0.0):
    """Delete all strategies whose config.perf.sharpe < min_sharpe.
    Much faster than GET /strategies + N×DELETE since it's a single pass."""
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

    return {
        "min_sharpe": min_sharpe,
        "total":   len(rows),
        "deleted": len(deleted),
        "kept":    len(kept),
        "kept_strategies": kept,
    }
