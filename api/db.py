"""DuckDB per-thread connection wrapper + schema init."""
import os
import threading
import duckdb

DB_PATH = os.environ.get("DUCKDB_PATH", "/tmp/pareto.db")
_local = threading.local()


def get_conn() -> duckdb.DuckDBPyConnection:
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = duckdb.connect(DB_PATH)
        _init_schema(_local.conn)
    return _local.conn


def close_conn() -> None:
    """Close the thread-local DuckDB connection if open."""
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None


def _init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            ticker TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'yfinance',
            ts     TIMESTAMP NOT NULL,
            open   DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
            PRIMARY KEY (ticker, ts)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id          TEXT PRIMARY KEY,
            name        TEXT,
            ticker      TEXT,
            timeframe   TEXT DEFAULT '1h',
            params      JSON,
            status      TEXT DEFAULT 'pending',
            strategy_id TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migrate existing DB: add strategy_id only if the column is truly missing
    existing_cols = {row[0] for row in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='runs'"
    ).fetchall()}
    if "strategy_id" not in existing_cols:
        conn.execute("ALTER TABLE runs ADD COLUMN strategy_id TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_results (
            run_id    TEXT PRIMARY KEY,
            metrics   JSON,
            equity    JSON,
            trades    JSON,
            wfo       JSON,
            sweep     JSON,
            mc        JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id            TEXT PRIMARY KEY,
            name          TEXT,
            strategy_type TEXT,
            config        JSON,
            code          TEXT,
            starred       BOOLEAN DEFAULT FALSE,
            status        TEXT DEFAULT 'research',
            run_ref       TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS brain_chunks (
            id         TEXT PRIMARY KEY,
            title      TEXT,
            content    TEXT,
            tags       JSON,
            synced_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migrate brain_chunks: add learning columns if missing
    _bc_cols = {row[0] for row in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='brain_chunks'"
    ).fetchall()}
    for _col, _def in [
        ("source",         "TEXT DEFAULT 'theory'"),
        ("scope",          "TEXT DEFAULT 'universal'"),
        ("asset",          "TEXT"),
        ("timeframe",      "TEXT"),
        ("verdict",        "TEXT"),
        ("regime_vector",  "JSON"),
        ("run_id",         "TEXT"),
    ]:
        if _col not in _bc_cols:
            conn.execute(f"ALTER TABLE brain_chunks ADD COLUMN {_col} {_def}")
