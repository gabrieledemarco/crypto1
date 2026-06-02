import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # allow `import engine`

import uuid
import logging
from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from api.limiter import limiter
from api.db import get_conn, close_conn
from api.routers import runs, assets, strategies, vibe, brain, analysis, optimize, download, pipeline, vibe_pipeline
from api.routers.vibe_v2 import router as vibe_v2_router

log = logging.getLogger("api")

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]


def _seed_library_if_empty(conn) -> None:
    """Insert 3 pipeline strategies on first startup if the Library is empty."""
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM strategies WHERE strategy_type='pipeline'"
        ).fetchone()[0]
        if count > 0:
            return

        import json, uuid
        from api.strategies import get_archetype

        TICKERS = [("BTC-USD", "1h"), ("ETH-USD", "1h"), ("SOL-USD", "1h")]
        for i, (ticker, tf) in enumerate(TICKERS, 1):
            arch_name, code, sl, tp = get_archetype(i)
            sid = uuid.uuid4().hex[:8]
            config = json.dumps({
                "ticker": ticker, "timeframe": tf,
                "sl_mult": sl, "tp_mult": tp,
                "active_hours": [6, 22],
                "commission": 0.0004, "slippage": 0.0001,
                "risk_per_trade": 0.01, "direction": "ALL",
            })
            conn.execute(
                "INSERT INTO strategies (id,name,strategy_type,config,code,starred,status)"
                " VALUES (?,?,?,?,?,true,'live')",
                [sid, f"pipe_seed_{i:02d}_{tf}_{ticker.replace('-','_')}",
                 "pipeline", config, code],
            )
        conn.commit()
    except Exception as e:
        import logging
        logging.warning(f"Library seed skipped: {e}")


def _repair_assets_table(conn) -> None:
    """Remove parquet-cached rows from the assets table on startup.

    Old versions of _load_or_fetch wrote Parquet data into DuckDB as a cache.
    If the process was killed mid-write the table ends up with partial rows.
    We now serve Parquet data directly from files, so these rows are stale.
    """
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM assets WHERE source LIKE 'parquet:%'"
        ).fetchone()[0]
        if n > 0:
            conn.execute("DELETE FROM assets WHERE source LIKE 'parquet:%'")
            conn.commit()
            import logging
            logging.info(f"startup repair: removed {n} stale parquet-cached rows from assets table")
    except Exception as e:
        import logging
        logging.warning(f"startup repair skipped: {e}")


def _prewarm_data_cache() -> None:
    """Preload recent OHLCV data into fast_loader warm cache (daemon threads)."""
    import threading
    try:
        from engine.storage.fast_loader import warm_preload
        tickers = [t.strip() for t in os.getenv("PREWARM_TICKERS", "BTC-USD,ETH-USD,SOL-USD").split(",") if t.strip()]
        intervals = [i.strip() for i in os.getenv("PREWARM_INTERVALS", "1h,4h").split(",") if i.strip()]
        for ticker in tickers:
            asset_class = "crypto" if ticker.endswith("-USD") or ticker.endswith("-USDT") else "stock"
            for iv in intervals:
                threading.Thread(
                    target=warm_preload, args=(asset_class, ticker, iv), daemon=True
                ).start()
    except Exception as exc:
        logging.warning(f"prewarm skipped: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        conn = get_conn()
        _repair_assets_table(conn)
        _seed_library_if_empty(conn)
        _prewarm_data_cache()
    except Exception as e:
        import logging
        logging.error(f"DB init failed: {e}")
        raise
    yield
    close_conn()


app = FastAPI(title="Pareto API", version="0.3.2", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next) -> Response:
    """Attach a UUID4 request ID to every request; propagate it in the response header."""
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    response: Response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    log.debug("request path=%s status=%s rid=%s", request.url.path, response.status_code, rid)
    return response


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.3.2"}


app.include_router(vibe_pipeline.router, prefix="/runs/pipeline/vibe", tags=["vibe-pipeline"])
app.include_router(pipeline.router,   prefix="/runs/pipeline",    tags=["pipeline"])
app.include_router(optimize.router,   prefix="/runs/optimize",    tags=["optimize"])
app.include_router(runs.router,       prefix="/runs",             tags=["runs"])
app.include_router(download.router,   prefix="/assets/download",  tags=["download"])
app.include_router(assets.router,     prefix="/assets",           tags=["assets"])
app.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
app.include_router(vibe.router,       prefix="/vibe",       tags=["vibe"])
app.include_router(vibe_v2_router,    prefix="/vibe",       tags=["vibe-v2"])
app.include_router(brain.router,      prefix="/brain",      tags=["brain"])
app.include_router(analysis.router,   prefix="/analysis",   tags=["analysis"])
