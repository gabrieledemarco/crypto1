"""
api/routers/brain_semantic.py
==============================
TF-IDF semantic search over brain_chunks content.
Replaces keyword scoring in get_brain_context.
Uses sklearn — no external embedding API needed.
"""
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from api.db import get_conn

# Module-level TF-IDF index — rebuilt when brain is synced
_vectorizer: TfidfVectorizer | None = None
_tfidf_matrix = None          # sparse matrix (n_chunks × vocab)
_chunk_ids: list[str] = []    # parallel list of chunk IDs


def _load_corpus() -> list[tuple[str, str, str]]:
    """Load all brain chunks: (id, title, content)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, title, content FROM brain_chunks ORDER BY synced_at DESC"
        ).fetchall()
        return [(r[0], r[1] or "", r[2] or "") for r in rows]
    except Exception:
        return []


def rebuild_index() -> int:
    """Rebuild the TF-IDF index from all brain_chunks. Returns n_chunks indexed."""
    global _vectorizer, _tfidf_matrix, _chunk_ids

    corpus_data = _load_corpus()
    if not corpus_data:
        _vectorizer, _tfidf_matrix, _chunk_ids = None, None, []
        return 0

    _chunk_ids = [row[0] for row in corpus_data]
    texts = [f"{row[1]} {row[2]}" for row in corpus_data]  # title + content

    _vectorizer = TfidfVectorizer(
        max_features=8000,
        ngram_range=(1, 2),          # unigrams + bigrams
        stop_words="english",
        sublinear_tf=True,           # log(1+tf) — dampens high-freq terms
        min_df=1,
    )
    _tfidf_matrix = _vectorizer.fit_transform(texts)
    return len(_chunk_ids)


def semantic_search(
    query: str,
    top_k: int = 6,
    source_filter: str | None = None,    # 'theory' | 'empirical' | None
    asset_filter: str | None = None,
    min_score: float = 0.05,
) -> list[dict]:
    """
    TF-IDF cosine similarity search over brain_chunks.
    Returns top_k chunks above min_score.
    """
    global _vectorizer, _tfidf_matrix, _chunk_ids

    # Lazy build on first call
    if _vectorizer is None or _tfidf_matrix is None:
        n = rebuild_index()
        if n == 0:
            return []

    try:
        q_vec = _vectorizer.transform([query])
        scores = cosine_similarity(q_vec, _tfidf_matrix)[0]
    except Exception:
        return []

    # Load metadata for filtering
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, title, content, source, scope, asset, verdict, tags "
            "FROM brain_chunks ORDER BY synced_at DESC"
        ).fetchall()
        meta = {r[0]: r for r in rows}
    except Exception:
        meta = {}

    ranked = sorted(
        [(float(scores[i]), cid) for i, cid in enumerate(_chunk_ids)],
        reverse=True,
    )

    results = []
    for score, cid in ranked:
        if score < min_score:
            break
        if len(results) >= top_k:
            break
        m = meta.get(cid)
        if m is None:
            continue
        _, title, content, source, scope, asset, verdict, tags_raw = m
        if source_filter and source != source_filter:
            continue
        if asset_filter and asset and asset != asset_filter:
            continue
        results.append({
            "id": cid,
            "title": title or "",
            "content": content or "",
            "score": round(score, 4),
            "source": source or "theory",
            "scope": scope or "universal",
            "asset": asset,
            "verdict": verdict,
        })

    return results


def invalidate_index() -> None:
    """Call after syncing new chunks so the next search rebuilds the index."""
    global _vectorizer, _tfidf_matrix, _chunk_ids
    _vectorizer, _tfidf_matrix, _chunk_ids = None, None, []
