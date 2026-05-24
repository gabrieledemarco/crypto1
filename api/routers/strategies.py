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
    # Join with the most-recent completed run per strategy to get live metrics
    rows = conn.execute("""
        WITH best_run AS (
            SELECT r.strategy_id,
                   rr.metrics,
                   ROW_NUMBER() OVER (
                       PARTITION BY r.strategy_id ORDER BY rr.created_at DESC
                   ) AS rn
            FROM runs r
            JOIN run_results rr ON rr.run_id = r.id
            WHERE r.status IN ('completed', 'done')
        )
        SELECT s.id, s.name, s.strategy_type, s.config, s.code,
               s.starred, s.status, s.run_ref, s.created_at,
               br.metrics AS run_metrics
        FROM strategies s
        LEFT JOIN best_run br ON br.strategy_id = s.id AND br.rn = 1
        ORDER BY s.starred DESC, s.created_at DESC
    """).fetchall()

    result = []
    for r in rows:
        cfg = {}
        try:
            cfg = json.loads(r[3]) if r[3] else {}
        except Exception:
            pass

        # Extract metrics from linked run_results (best available)
        metrics = {"sharpe": 0.0, "cagr": 0.0, "maxDD": 0.0, "pf": 0.0, "trades": 0}
        try:
            rm = json.loads(r[9]) if r[9] else {}
            # run_results.metrics is a dict of version → metrics
            best = _best_metrics(rm)
            if best:
                metrics = {
                    "sharpe": round(float(best.get("sharpe_ratio", best.get("sharpe", 0)) or 0), 3),
                    "cagr":   round(float(best.get("cagr_pct", 0) or 0), 2),
                    "maxDD":  round(float(best.get("max_drawdown_pct", best.get("max_dd", 0)) or 0), 2),
                    "pf":     round(float(best.get("profit_factor", 0) or 0), 2),
                    "trades": int(best.get("n_trades", 0) or 0),
                }
        except Exception:
            pass

        result.append({
            # Fields the frontend LibraryEntryApi interface expects
            "id":       r[0],
            "name":     r[1],
            "strategy": r[2] or "vibe_loop",   # strategy_type → strategy
            "author":   "",
            "created":  str(r[8]),              # created_at → created
            "tags":     _tags(cfg),
            "starred":  bool(r[5]),
            "status":   r[6] or "research",
            "metrics":  metrics,
            "desc":     "",
            "runRef":   r[7],
            # Extra fields kept for other consumers
            "config":   cfg,
            "code":     r[4] or "",
        })
    return result


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
