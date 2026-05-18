import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # allow `import engine`

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.db import get_conn
from api.routers import runs, assets, strategies, vibe

app = FastAPI(title="Pareto API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    get_conn()  # init schema


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0"}


app.include_router(runs.router,       prefix="/runs",       tags=["runs"])
app.include_router(assets.router,     prefix="/assets",     tags=["assets"])
app.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
app.include_router(vibe.router,       prefix="/vibe",       tags=["vibe"])
