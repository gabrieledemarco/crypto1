"""DuckDB per-thread connection wrapper + schema init."""
import os
import threading
import duckdb

DB_PATH = os.environ.get("DUCKDB_PATH", "/tmp/pareto.db")
_local = threading.local()
_schema_lock = threading.Lock()
_schema_ready = threading.Event()  # set once schema init is fully committed

# Schema version — bump when adding new migrations so deploys are visible in logs
_SCHEMA_VERSION = "2"


def get_conn() -> duckdb.DuckDBPyConnection:
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = duckdb.connect(DB_PATH)
        if not _schema_ready.is_set():
            with _schema_lock:
                if not _schema_ready.is_set():
                    _init_schema(_local.conn)
                    _schema_ready.set()   # signal only after commit inside _init_schema
    return _local.conn


def close_conn() -> None:
    """Commit pending writes and close the thread-local DuckDB connection."""
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        try:
            conn.commit()
        except Exception:
            pass
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
    # (already guarded by _schema_lock in get_conn via double-checked locking)
    existing_cols = {row[0] for row in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='runs'"
    ).fetchall()}
    if "strategy_id" not in existing_cols:
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN strategy_id TEXT")
        except Exception as _e:
            if "already exists" not in str(_e).lower():
                raise
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
    # Migrate existing strategies table: add columns added after initial deploy
    _st_cols = {row[0] for row in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='strategies'"
    ).fetchall()}
    for _col, _def in [
        ("code",     "TEXT"),
        ("starred",  "BOOLEAN DEFAULT FALSE"),
        ("status",   "TEXT DEFAULT 'research'"),
        ("run_ref",  "TEXT"),
    ]:
        if _col not in _st_cols:
            try:
                conn.execute(f"ALTER TABLE strategies ADD COLUMN {_col} {_def}")
            except Exception as _e:
                if "already exists" not in str(_e).lower():
                    raise
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
            try:
                conn.execute(f"ALTER TABLE brain_chunks ADD COLUMN {_col} {_def}")
            except Exception as _e:
                if "already exists" not in str(_e).lower():
                    raise
    # Commit all DDL so other threads immediately see the final schema
    conn.commit()
