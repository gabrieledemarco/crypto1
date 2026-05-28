import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # allow `import engine`

from contextlib import asynccontextmanager
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from api.db import get_conn, close_conn
from api.routers import runs, assets, strategies, vibe, brain, analysis, optimize, download, pipeline

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

limiter = Limiter(key_func=get_remote_address)

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        conn = get_conn()
        _seed_library_if_empty(conn)
    except Exception as e:
        import logging
        logging.error(f"DB init failed: {e}")
        raise
    yield
    close_conn()


app = FastAPI(title="Pareto API", version="0.3.1", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.3.1"}


app.include_router(pipeline.router,   prefix="/runs/pipeline",    tags=["pipeline"])
app.include_router(optimize.router,   prefix="/runs/optimize",    tags=["optimize"])
app.include_router(runs.router,       prefix="/runs",             tags=["runs"])
app.include_router(download.router,   prefix="/assets/download",  tags=["download"])
app.include_router(assets.router,     prefix="/assets",           tags=["assets"])
app.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
app.include_router(vibe.router,       prefix="/vibe",       tags=["vibe"])
app.include_router(brain.router,      prefix="/brain",      tags=["brain"])
app.include_router(analysis.router,   prefix="/analysis",   tags=["analysis"])
