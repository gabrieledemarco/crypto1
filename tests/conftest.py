"""
Pytest configuration — resets api.db singleton state before each test
so tests that import api.db always get a fresh in-memory connection.
"""
import os
import pytest

os.environ.setdefault("DUCKDB_PATH", ":memory:")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")


@pytest.fixture(autouse=True)
def reset_db_singleton():
    """Force api.db to reinitialize schema on the next get_conn() call."""
    import importlib
    try:
        import api.db as db
        db._schema_done = False
        if hasattr(db._local, "conn") and db._local.conn is not None:
            try:
                db._local.conn.close()
            except Exception:
                pass
            db._local.conn = None
    except ImportError:
        pass
    yield
