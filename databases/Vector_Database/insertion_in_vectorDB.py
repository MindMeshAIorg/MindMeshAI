import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CHUNKS_FILE = ROOT_DIR / "vector_chunks.json"

# =====================================================================
# QDRANT DATABASE INSERTION CODE COMMENTED OUT FOR FILE STORAGE
# =====================================================================
# from qdrant_client import models
# from databases.Vector_Database.qdrant_setup import client, get_qdrant_client, COLLECTION_NAME
#
# def _original_store_chunks(chunks, max_retries=3, retry_delay=2.0):
#     points = []
#     for chunk in chunks:
#         point = models.PointStruct(...)
#         points.append(point)
#     client.upsert(collection_name=COLLECTION_NAME, points=points)
# =====================================================================


def _read_chunks() -> List[Dict[str, Any]]:
    if not CHUNKS_FILE.exists():
        with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        return []
    try:
        with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_chunks(chunks: List[Dict[str, Any]]) -> None:
    temp_file = CHUNKS_FILE.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    temp_file.replace(CHUNKS_FILE)


def store_chunks(chunks, max_retries: int = 3, retry_delay: float = 2.0) -> int:
    """
    Store embedded chunks directly into vector_chunks.json in the base directory.
    Supports single-user and multi-source chunks.
    """
    if not chunks:
        print("No chunks to store.")
        return 0

    existing_chunks = _read_chunks()
    existing_map = {str(c.get("chunk_id")): i for i, c in enumerate(existing_chunks)}
    now_iso = datetime.now(timezone.utc).isoformat()

    added_count = 0
    for chunk in chunks:
        cid = str(chunk.get("chunk_id"))
        payload = chunk.get("payload", {}).copy()
        payload["user_id"] = str(chunk.get("user_id", "single_user"))

        # Format sparse data safely for JSON
        sparse_data = chunk.get("sparse_vector", {})
        if hasattr(sparse_data, "indices") and hasattr(sparse_data, "values"):
            sparse_dict = {"indices": list(sparse_data.indices), "values": list(sparse_data.values)}
        elif isinstance(sparse_data, dict):
            sparse_dict = sparse_data
        else:
            sparse_dict = {}

        # Format dense vector safely for JSON
        dense_vec = chunk.get("dense_vector", [])
        if hasattr(dense_vec, "tolist"):
            dense_vec = dense_vec.tolist()
        elif isinstance(dense_vec, (list, tuple)):
            dense_vec = list(dense_vec)

        stored_record = {
            "chunk_id": cid,
            "user_id": str(chunk.get("user_id", "single_user")),
            "dense_vector": dense_vec,
            "sparse_vector": sparse_dict,
            "payload": payload,
            "stored_at": now_iso,
        }

        if cid in existing_map:
            existing_chunks[existing_map[cid]] = stored_record
        else:
            existing_chunks.append(stored_record)
            existing_map[cid] = len(existing_chunks) - 1
        added_count += 1

    _write_chunks(existing_chunks)
    print(f"Successfully stored {added_count} chunk(s) in vector_chunks.json.")
    return added_count

