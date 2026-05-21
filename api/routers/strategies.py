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
    rows = conn.execute(
        "SELECT id, name, strategy_type, config, code, starred, status, run_ref, created_at FROM strategies ORDER BY created_at DESC"
    ).fetchall()
    return [
        {"id": r[0], "name": r[1], "strategy_type": r[2],
         "config": json.loads(r[3]) if r[3] else {}, "code": r[4] or "",
         "starred": bool(r[5]), "status": r[6], "run_ref": r[7], "created_at": str(r[8])}
        for r in rows
    ]


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
