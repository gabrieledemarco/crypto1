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
import os
import re
import requests
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

# Per i capitoli non in ML_for_Algorithmic_Trading, mappa l'ID al path relativo
# nella repo Trading_agent_brain (e nella cartella locale api/brain_chapters/).
_CHAPTER_PATH_OVERRIDE: dict[str, str] = {
    "lorenz_01_esecuzione_ottimale":  "Optimal_Execution_Lorenz/01_optimal_execution_almgren_chriss.md",
    "cartea_01_mercati_lob":          "Algorithmic_HFT_Cartea/01_mercati_elettronici_lob.md",
    "cartea_02_hjb":                  "Algorithmic_HFT_Cartea/02_controllo_stocastico_hjb.md",
    "cartea_03_esecuzione":           "Algorithmic_HFT_Cartea/03_esecuzione_ottimale.md",
    "cartea_04_market_making":        "Algorithmic_HFT_Cartea/04_market_making.md",
    "cartea_05_pairs_oi":             "Algorithmic_HFT_Cartea/05_pairs_trading_order_imbalance.md",
}

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
    # ── Nuovi libri: Lorenz (2008) + Cartea-Jaimungal-Penalva (2015) ──────────
    ("lorenz_01_esecuzione_ottimale", [
        "optimal execution", "implementation shortfall", "market impact",
        "almgren", "chriss", "lorenz", "traiettoria", "urgenza", "kappa",
        "liquidazione", "execution cost", "slippage", "sinh", "frontiera efficiente",
        "aggressive in the money", "adattivo", "market power",
    ]),
    ("cartea_01_mercati_lob", [
        "limit order book", "LOB", "midprice", "microprice", "spread", "bid ask",
        "mercato elettronico", "maker taker", "dark pool", "colocation",
        "microstruttura", "market microstructure", "tassonomia trader",
        "informed trader", "market maker", "noise trader", "U-shape volume",
        "price impact", "square root law",
    ]),
    ("cartea_02_hjb", [
        "HJB", "Hamilton-Jacobi-Bellman", "controllo stocastico", "stochastic control",
        "programmazione dinamica", "dynamic programming", "Bellman",
        "optimal stopping", "Riccati", "funzione valore", "value function",
        "processo di salto", "Poisson",
    ]),
    ("cartea_03_esecuzione", [
        "esecuzione ottimale", "cartea jaimungal", "tasso di esecuzione",
        "VWAP", "order flow signal", "adverse selection esecuzione",
        "dark pool esecuzione", "limit order esecuzione", "price limiter",
        "IS minimizzazione", "implementation shortfall continuo",
    ]),
    ("cartea_04_market_making", [
        "market making", "avellaneda stoikov", "quote ottimali", "delta ottimale",
        "reservation price", "skew inventario", "adverse selection",
        "short term alpha", "fill rate", "Lambda kappa", "inventory risk",
        "spread cattura", "market maker", "bid ask posting",
    ]),
    ("cartea_05_pairs_oi", [
        "pairs trading", "cointegrazione", "cointegration", "spread stazionario",
        "ornstein uhlenbeck", "OU", "mean reversion spread", "emivita",
        "order imbalance", "OI", "flusso ordini", "order flow",
        "segnale breve termine", "Markov chain ordini", "segnale imbalance",
        "statarb", "statistical arbitrage",
    ]),
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


def _cosine_sim(v1: dict, v2: dict) -> float:
    """Cosine similarity between two regime vectors."""
    keys = ["hurst", "garch_persistence", "ann_vol_pct", "trending_pct", "high_regime_pct"]
    a = [float(v1.get(k, 0)) for k in keys]
    b = [float(v2.get(k, 0)) for k in keys]
    a, b = np.array(a), np.array(b)
    # Normalize ann_vol to 0-1 range (typical 0-200%)
    a[2] /= 100.0
    b[2] /= 100.0
    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _get_empirical_lessons(
    asset: Optional[str],
    current_regime: Optional[dict],
    top_k: int = 3,
) -> list[dict]:
    """Retrieve empirical lessons from backtests, weighted by regime similarity."""
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT id, title, content, scope, asset, verdict, regime_vector "
            "FROM brain_chunks WHERE source='empirical' "
            "ORDER BY synced_at DESC LIMIT 50"
        ).fetchall()
    except Exception:
        return []

    scored = []
    for row in rows:
        chunk_id, title, content, scope, chunk_asset, verdict, rv_json = row
        # Base score: asset match
        asset_score = 1.0 if (asset and chunk_asset == asset) else 0.5

        # Regime similarity
        regime_score = 0.5
        if current_regime and rv_json:
            try:
                chunk_regime = json.loads(rv_json) if isinstance(rv_json, str) else rv_json
                regime_score = _cosine_sim(current_regime, chunk_regime)
            except Exception:
                pass

        # Scope weight
        scope_w = {"universal": 1.0, "regime": 0.9, "asset": 0.8}.get(scope or "asset", 0.8)

        total = (0.4 * asset_score + 0.4 * regime_score + 0.2 * scope_w)
        scored.append((total, {"title": title, "content": content, "verdict": verdict}))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def get_brain_context(
    prompt: str,
    max_chapters: int = 3,
    asset: Optional[str] = None,
    current_regime: Optional[dict] = None,
) -> str:
    """
    Build a <second_brain> context block for the given prompt.
    Returns empty string if no chapters are synced yet.
    Appends empirical lessons in a <strategy_history> block when available.
    """
    # TF-IDF semantic search — more precise than keyword scoring
    try:
        from api.routers.brain_semantic import semantic_search
        theory_chunks = semantic_search(
            query=prompt,
            top_k=4,
            source_filter="theory",
            min_score=0.03,
        )
        # Format same as before: list of dicts with 'title' and 'content'
        selected = theory_chunks
    except Exception:
        # Fallback to original keyword scoring if semantic search fails
        selected = []
        chapter_ids = select_chapters(prompt, max_chapters)
        conn = get_conn()
        for ch_id in chapter_ids:
            rows = conn.execute(
                "SELECT title, content FROM brain_chunks WHERE id = ?", [ch_id]
            ).fetchall()
            if rows:
                selected.append({"title": rows[0][0], "content": rows[0][1]})

    chunks: list[str] = []
    for item in selected:
        title = item.get("title", "")
        content = item.get("content", "")
        body = content[:_CHARS_PER_CHAPTER]
        if len(content) > _CHARS_PER_CHAPTER:
            body += "\n…[truncated — full chapter in knowledge base]"
        chunks.append(f"#### {title}\n{body}")

    theory_block = ""
    if chunks:
        theory_block = (
            "<second_brain>\n"
            "Use the following knowledge from your ML-trading knowledge base to inform "
            "your strategy design. Apply relevant concepts, formulas, and heuristics.\n\n"
            + "\n\n---\n\n".join(chunks)
            + "\n</second_brain>\n\n"
        )

    empirical_lessons = _get_empirical_lessons(asset, current_regime)
    history_block = ""
    if empirical_lessons:
        lesson_parts = []
        for lesson in empirical_lessons:
            verdict_tag = lesson.get("verdict", "unknown")
            lesson_parts.append(
                f"[{verdict_tag.upper()}] {lesson['title']}\n{lesson['content']}"
            )
        history_block = (
            "<strategy_history>\n"
            "Past backtest results for this asset / regime — use these lessons to "
            "avoid repeating failures and build on what worked.\n\n"
            + "\n\n---\n\n".join(lesson_parts)
            + "\n</strategy_history>\n\n"
        )

    combined = theory_block + history_block
    return combined


# ── REST endpoints ─────────────────────────────────────────────────────────────

@router.post("/sync")
def sync_brain():
    """Download all chapters from Trading_agent_brain and store in DuckDB."""
    conn = get_conn()
    synced: list[str] = []
    errors: list[dict] = []

    _local_base = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "brain_chapters")
    )

    for chapter_id, keywords in _CHAPTERS:
        # Capitoli con path non-standard (nuovi libri fuori da ML_for_Algorithmic_Trading)
        rel_path    = _CHAPTER_PATH_OVERRIDE.get(chapter_id, f"{_BOOK_PATH}/{chapter_id}.md")
        github_url  = f"{_RAW_BASE}/{rel_path}"
        local_path  = os.path.join(_local_base, rel_path)

        try:
            resp = httpx.get(github_url, timeout=15.0, follow_redirects=True)
            if resp.status_code == 404:
                # Fallback: carica dalla cartella locale api/brain_chapters/
                if os.path.exists(local_path):
                    with open(local_path, "r", encoding="utf-8") as fh:
                        content = fh.read()
                else:
                    errors.append({"chapter": chapter_id, "error": "404 not found, no local fallback"})
                    continue
            else:
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

    # Also sync code notebooks (code_01.md … code_22.md)
    BASE_CODE_URL = "https://raw.githubusercontent.com/gabrieledemarco/Trading_agent_brain/main/ML_for_Algorithmic_Trading/"
    for i in range(1, 23):
        code_id = f"code_{i:02d}"
        try:
            url = f"{BASE_CODE_URL}code_{i:02d}.md"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and len(resp.text) > 100:
                existing = conn.execute(
                    "SELECT id FROM brain_chunks WHERE id=?", [code_id]
                ).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT INTO brain_chunks (id, title, content, tags, source) VALUES (?,?,?,?,?)",
                        [code_id, f"Code Implementation: Chapter {i}",
                         resp.text[:6000], json.dumps(["code", f"chapter_{i}", "implementation"]),
                         "theory"]
                    )
        except Exception:
            pass  # individual code file failures are non-blocking

    # Invalidate TF-IDF index so next retrieval rebuilds with new content
    try:
        from api.routers.brain_semantic import invalidate_index
        invalidate_index()
    except Exception:
        pass

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
