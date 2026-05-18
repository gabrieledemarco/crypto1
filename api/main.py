from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Pareto API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/runs")
def list_runs():
    return []

@app.post("/runs")
def create_run(body: dict):
    return {"id": "placeholder", "status": "queued"}

@app.get("/runs/{run_id}")
def get_run(run_id: str):
    return {"id": run_id}

@app.get("/runs/{run_id}/equity")
def get_equity(run_id: str):
    return []

@app.get("/runs/{run_id}/trades")
def get_trades(run_id: str):
    return []

@app.get("/runs/{run_id}/sweep")
def get_sweep(run_id: str):
    return []

@app.get("/runs/{run_id}/mc")
def get_mc(run_id: str):
    return {}

@app.get("/runs/{run_id}/wfo")
def get_wfo(run_id: str):
    return []

@app.get("/strategies")
def list_strategies():
    return []

@app.post("/strategies")
def create_strategy(body: dict):
    return {"id": "placeholder"}

@app.get("/assets/{ticker}/stats")
def get_asset_stats(ticker: str):
    return {}

@app.post("/assets/fetch")
def fetch_asset(body: dict):
    return {"status": "ok"}

@app.post("/runs/preview")
def preview_run(body: dict):
    return {"sharpe": 0, "trades": 0, "exposure": 0}

@app.post("/vibe/generate")
def vibe_generate(body: dict):
    return {"strategy": {}}
