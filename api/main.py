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
from api.routers import runs, assets, strategies, vibe

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        get_conn()
    except Exception as e:
        import logging
        logging.error(f"DB init failed: {e}")
        raise
    yield
    close_conn()


app = FastAPI(title="Pareto API", version="0.2.0", lifespan=lifespan)
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
    return {"status": "ok", "version": "0.2.0"}


app.include_router(runs.router,       prefix="/runs",       tags=["runs"])
app.include_router(assets.router,     prefix="/assets",     tags=["assets"])
app.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
app.include_router(vibe.router,       prefix="/vibe",       tags=["vibe"])
