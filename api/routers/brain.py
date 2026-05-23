"""
api/routers/brain.py — Second-brain knowledge base (Karpathy method)
=====================================================================
Syncs dense ML-trading notes from Trading_agent_brain repo into DuckDB.
Provides keyword-based retrieval to inject relevant chapters as context
into the Vibe agent before every Claude call.

POST /brain/sync      → download all chapters from GitHub → DuckDB
GET  /brain/chunks    → list available synced chapters
GET  /brain/query?q=  → show which chapters would be selected for a query
"""
import json
import re
from datetime import datetime
from typing import Optional

import httpx
import numpy as np
from fastapi import APIRouter, HTTPException

from api.db import get_conn

router = APIRouter()

_BRAIN_REPO  = "gabrieledemarco/Trading_agent_brain"
_RAW_BASE    = f"https://raw.githubusercontent.com/{_BRAIN_REPO}/main"
_BOOK_PATH   = "ML_for_Algorithmic_Trading"

# (chapter_id, keywords) — used for both sync and retrieval routing
_CHAPTERS: list[tuple[str, list[str]]] = [
    ("01_ml_for_trading",      ["trading", "overview", "introduction", "framework"]),
    ("02_market_data",         ["market data", "OHLCV", "data", "price", "volume", "feature"]),
    ("03_alternative_data",    ["alternative data", "sentiment", "news", "NLP data"]),
    ("04_alpha_factors",       ["alpha", "factor", "signal", "momentum", "mean reversion",
                                "trend", "cross-sectional", "feature engineering"]),
    ("05_strategy_evaluation", ["backtest", "evaluation", "overfitting", "sharpe", "calmar",
                                "validation", "drawdown", "risk", "walk-forward", "performance"]),
    ("06_ml_process",          ["ML process", "cross-validation", "pipeline", "preprocessing",
                                "feature selection", "hyperparameter", "regularisation"]),
    ("07_linear_models",       ["linear", "regression", "lasso", "ridge", "logistic",
                                "OLS", "penalized"]),
    ("08_time_series",         ["time series", "ARIMA", "autocorrelation", "stationarity",
                                "VAR", "Granger"]),
    ("09_bayesian",            ["Bayesian", "probabilistic", "prior", "posterior",
                                "inference", "uncertainty"]),
    ("10_decision_trees",      ["decision tree", "tree", "classification", "CART"]),
    ("11_random_forests",      ["random forest", "ensemble", "bagging", "bootstrap aggregating"]),
    ("12_gradient_boosting",   ["gradient boosting", "XGBoost", "LightGBM", "CatBoost",
                                "boosting", "GBDT"]),
    ("13_text_data",           ["text", "NLP", "natural language", "corpus", "tokenization"]),
    ("14_topic_modeling",      ["topic modeling", "LDA", "NMF", "latent"]),
    ("15_word_embeddings",     ["word2vec", "embeddings", "word vectors", "GloVe", "FastText"]),
    ("16_deep_learning",       ["deep learning", "neural network", "DNN", "MLP",
                                "activation", "optimizer"]),
    ("17_cnn",                 ["CNN", "convolutional", "image", "2D"]),
    ("18_rnn",                 ["RNN", "LSTM", "GRU", "recurrent", "sequence", "temporal"]),
    ("19_autoencoders",        ["autoencoder", "GAN", "generative", "variational", "VAE"]),
    ("20_reinforcement_learning", ["reinforcement learning", "RL", "Q-learning", "reward",
                                   "policy", "agent", "DQN", "PPO", "A3C"]),
    ("21_next_steps",          ["deployment", "production", "live trading", "next steps"]),
]

_DEFAULT_CHAPTERS = ["04_alpha_factors", "05_strategy_evaluation"]
_CHARS_PER_CHAPTER = 4000   # ~1000 tokens per chapter injected


def select_chapters(prompt: str, max_chapters: int = 3) -> list[str]:
    """Return up to max_chapters chapter IDs most relevant to the prompt."""
    prompt_lower = prompt.lower()
    scores: list[tuple[int, str]] = []
    for chapter_id, keywords in _CHAPTERS:
        score = sum(1 for kw in keywords if kw.lower() in prompt_lower)
        if score > 0:
            scores.append((score, chapter_id))
    scores.sort(reverse=True)
    selected = [ch for _, ch in scores[:max_chapters]]
    return selected if selected else list(_DEFAULT_CHAPTERS)


def get_brain_context(prompt: str, max_chapters: int = 3) -> str:
    """
    Build a <second_brain> context block for the given prompt.
    Returns empty string if no chapters are synced yet.
    """
    conn = get_conn()
    chapter_ids = select_chapters(prompt, max_chapters)

    chunks: list[str] = []
    for ch_id in chapter_ids:
        rows = conn.execute(
            "SELECT title, content FROM brain_chunks WHERE id = ?", [ch_id]
        ).fetchall()
        if not rows:
            continue
        title, content = rows[0]
        body = content[:_CHARS_PER_CHAPTER]
        if len(content) > _CHARS_PER_CHAPTER:
            body += "\n…[truncated — full chapter in knowledge base]"
        chunks.append(f"#### {title}\n{body}")

    if not chunks:
        return ""

    return (
        "<second_brain>\n"
        "Use the following knowledge from your ML-trading knowledge base to inform "
        "your strategy design. Apply relevant concepts, formulas, and heuristics.\n\n"
        + "\n\n---\n\n".join(chunks)
        + "\n</second_brain>\n\n"
    )


# ── REST endpoints ─────────────────────────────────────────────────────────────

@router.post("/sync")
def sync_brain():
    """Download all chapters from Trading_agent_brain and store in DuckDB."""
    conn = get_conn()
    synced: list[str] = []
    errors: list[dict] = []

    for chapter_id, keywords in _CHAPTERS:
        url = f"{_RAW_BASE}/{_BOOK_PATH}/{chapter_id}.md"
        try:
            resp = httpx.get(url, timeout=15.0, follow_redirects=True)
            if resp.status_code == 404:
                errors.append({"chapter": chapter_id, "error": "404 not found"})
                continue
            resp.raise_for_status()
            content = resp.text

            title_match = re.search(r"^#+\s+(.+)", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else chapter_id

            conn.execute(
                "INSERT OR REPLACE INTO brain_chunks (id, title, content, tags, synced_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [chapter_id, title, content, json.dumps(keywords), str(datetime.utcnow())]
            )
            synced.append(chapter_id)
        except Exception as exc:
            errors.append({"chapter": chapter_id, "error": str(exc)})

    return {
        "synced": len(synced),
        "errors": len(errors),
        "chapters": synced,
        "error_details": errors,
    }


@router.get("/chunks")
def list_chunks():
    """List all synced brain chapters."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, title, LENGTH(content) as chars, synced_at "
        "FROM brain_chunks ORDER BY id"
    ).fetchall()
    return [
        {"id": r[0], "title": r[1], "chars": r[2], "synced_at": str(r[3])}
        for r in rows
    ]


@router.get("/query")
def query_brain(q: str):
    """Preview which chapters would be selected for a given query."""
    selected = select_chapters(q)
    conn = get_conn()
    result = []
    for ch_id in selected:
        rows = conn.execute(
            "SELECT id, title, LENGTH(content) as chars FROM brain_chunks WHERE id = ?",
            [ch_id]
        ).fetchall()
        if rows:
            result.append({"id": rows[0][0], "title": rows[0][1],
                           "chars": rows[0][2], "synced": True})
        else:
            result.append({"id": ch_id, "synced": False})
    return {"query": q, "selected_chapters": result}
