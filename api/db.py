"""DuckDB single-connection wrapper + schema init."""
import os
import duckdb

DB_PATH = os.environ.get("DUCKDB_PATH", "/tmp/pareto.db")
_conn: duckdb.DuckDBPyConnection | None = None


def get_conn() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = duckdb.connect(DB_PATH)
        _init_schema(_conn)
    return _conn


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
    # Migrate: add strategy_id if missing (existing DB)
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN strategy_id TEXT")
    except Exception:
        pass
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
