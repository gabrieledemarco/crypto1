"""
Pareto Terminal — FastAPI entry point
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import assets, runs, strategies, vibe
from api.db import get_conn, close_conn

try:
    from api.routers import brain
    _brain_ok = True
except Exception:
    _brain_ok = False

logger = logging.getLogger("pareto")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_conn()          # init schema on startup
    yield
    close_conn()


app = FastAPI(title="Pareto API", version="0.3.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assets.router,     prefix="/assets",     tags=["assets"])
app.include_router(runs.router,       prefix="/runs",       tags=["runs"])
app.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
app.include_router(vibe.router,       prefix="/vibe",       tags=["vibe"])
if _brain_ok:
    app.include_router(brain.router,  prefix="/brain",      tags=["brain"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.3.1"}
