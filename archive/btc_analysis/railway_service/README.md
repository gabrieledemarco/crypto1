# Vibe-Trading Railway Microservice

FastAPI wrapper around `vibe-trading-ai` for deployment on Railway.
Streamlit Cloud cannot run local subprocesses, so this service handles
strategy generation remotely.

## Deploy on Railway

1. Create a new Railway project
2. Connect this `railway_service/` directory (or the full repo and set root dir)
3. Set environment variables on Railway:
   - `SERVICE_TOKEN` — a random secret to protect the endpoint (recommended)
   - `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY` — NOT needed here; keys are
     sent per-request from the Streamlit app
4. Railway will build the Dockerfile and start the server on `$PORT`

## API

### `GET /health`
Returns `{"status": "ok"}` — used by Railway healthcheck.

### `POST /generate`
**Headers:** `Authorization: Bearer <SERVICE_TOKEN>` (if SERVICE_TOKEN is set)

**Body:**
```json
{
  "prompt": "...",
  "anthropic_key": "sk-ant-...",
  "openrouter_key": "",
  "openrouter_model": ""
}
```

**Response:**
```json
{
  "code": "def generate_signals_agent(df): ...",
  "error": ""
}
```

## Local testing

```bash
cd railway_service
pip install -r requirements.txt
uvicorn server:app --reload --port 8080
```

## Streamlit Cloud configuration

In the Streamlit app sidebar:
- `VIBE_TRADING_API_URL` → `https://your-service.up.railway.app`
- `VIBE_SERVICE_TOKEN` → the token you set on Railway

Or set them as Streamlit Cloud Secrets:
```toml
VIBE_TRADING_API_URL = "https://your-service.up.railway.app"
VIBE_SERVICE_TOKEN   = "your-secret-token"
```
