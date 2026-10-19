import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
for p in (PROJECT_ROOT, BASE_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

VENV_PACKAGES = PROJECT_ROOT / ".mindmeshenv" / "Lib" / "site-packages"
if VENV_PACKAGES.exists() and str(VENV_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_PACKAGES))

import json
from FlagEmbedding import BGEM3FlagModel

CHUNKS_FILE = PROJECT_ROOT / "vector_chunks.json"

# =====================================================================
# QDRANT DATABASE RETRIEVAL CODE COMMENTED OUT FOR FILE STORAGE
# =====================================================================
# from qdrant_client import models
# from databases.Vector_Database.qdrant_setup import client, get_qdrant_client, COLLECTION_NAME
#
# def _original_qdrant_query(qdrant, dense_vector, sparse_vector, query_filter, top_k, CANDIDATE_LIMIT):
#     return qdrant.query_points(
#         collection_name=COLLECTION_NAME,
#         prefetch=[...],
#         query=models.FusionQuery(fusion=models.Fusion.RRF),
#         query_filter=query_filter,
#         limit=top_k,
#     )
# =====================================================================

# Global singleton cache for embedding model to avoid 20+ second reload per query
_MODEL_CACHE: dict = {}


def get_embedding_model(model_name: str = "BAAI/bge-m3") -> BGEM3FlagModel:
    global _MODEL_CACHE
    if model_name not in _MODEL_CACHE:
        print(f"[RAG Retriever] Initializing embedding model: {model_name}...")
        _MODEL_CACHE[model_name] = BGEM3FlagModel(
            model_name,
            use_fp16=False,
        )
        print(f"[RAG Retriever] Embedding model {model_name} successfully cached.")
    return _MODEL_CACHE[model_name]


def _read_chunks() -> list:
    if not CHUNKS_FILE.exists():
        return []
    try:
        with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _cosine_similarity(vec_a: list, vec_b: list) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


def retrieve(
    MODEL_NAME: str = "BAAI/bge-m3",
    question: str = "",
    user_id: str = "",
    CANDIDATE_LIMIT: int = 10,
    top_k: int = 5,
    chat_name: str | None = None,
    max_retries: int = 3,
) -> list[dict]:
    """
    Retrieve relevant communications chunks from vector_chunks.json using
    dense vector cosine similarity and keyword matching.
    Configured for single-user mode.
    """
    if not question.strip():
        raise ValueError("Question cannot be empty.")

    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    all_chunks = _read_chunks()
    if not all_chunks:
        return []

    model = get_embedding_model(MODEL_NAME)

    # 1. Generate query embedding
    embeddings = model.encode(
        [question],
        batch_size=1,
        max_length=8192,
        return_dense=True,
        return_sparse=False,
        return_colbert_vecs=False,
    )
    dense_vector = embeddings["dense_vecs"][0].tolist()

    # 2. Identify allowed user IDs for filtering (with single-user fallback)
    allowed_uids = [str(user_id).strip()] if user_id else []
    try:
        from databases.Normal_database.auth_store import get_user_by_identifier
        user_rec = get_user_by_identifier(user_id)
        if user_rec:
            if user_rec.get("id"):
                allowed_uids.append(str(user_rec["id"]).strip())
            if user_rec.get("username"):
                allowed_uids.append(str(user_rec["username"]).strip())
            if user_rec.get("user"):
                allowed_uids.append(str(user_rec["user"]).strip())
    except Exception:
        pass
    allowed_uids = {u for u in allowed_uids if u}

    # 3. Filter candidates
    candidates = []
    for chunk in all_chunks:
        chunk_uid = str(chunk.get("user_id", "")).strip()
        payload = chunk.get("payload", {})

        # User check (single-user mode: match allowed_uids or fallback)
        if allowed_uids and chunk_uid not in allowed_uids and user_id not in ("single_user", "user_123"):
            # Check payload user_id as well
            payload_uid = str(payload.get("user_id", "")).strip()
            if payload_uid not in allowed_uids and len(all_chunks) > 10:
                continue

        # Optional chat_name filter
        if chat_name and payload.get("chat_name") != chat_name:
            continue

        candidates.append(chunk)

    if not candidates:
        candidates = all_chunks  # Single-user fallback

    # 4. Score candidates via cosine similarity + keyword boost
    q_words = [w.lower() for w in question.split() if len(w) > 2]
    scored_results = []

    for chunk in candidates:
        chunk_dense = chunk.get("dense_vector", [])
        sim = _cosine_similarity(dense_vector, chunk_dense)

        # Lexical keyword bonus
        payload = chunk.get("payload", {})
        text = str(payload.get("actual_text_in_chunk", "")).lower()
        keyword_hits = sum(1 for w in q_words if w in text)
        score = sim + (0.1 * keyword_hits)

        scored_results.append({
            "chunk_id": str(chunk.get("chunk_id")),
            "text": payload.get("actual_text_in_chunk", ""),
            "chat_name": payload.get("chat_name"),
            "source_type": payload.get("source_type"),
            "time": payload.get("time"),
            "score": score,
            "payload": payload,
        })

    # Sort descending by score
    scored_results.sort(key=lambda x: x["score"], reverse=True)
    return scored_results[:top_k]

