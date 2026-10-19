import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

COLLECTION_NAME = os.getenv(
    "QDRANT_COLLECTION",
    "mindmesh_memories",
)
CHUNKS_FILE = ROOT_DIR / "vector_chunks.json"

# =====================================================================
# QDRANT DATABASE CONNECTION CODE COMMENTED OUT FOR FILE STORAGE
# =====================================================================
# from qdrant_client import QdrantClient, models
#
# QDRANT_URL = os.getenv("QDRANT_URL")
# QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
#
# def get_qdrant_client(timeout: int = 45) -> QdrantClient:
#     return QdrantClient(
#         url=QDRANT_URL,
#         api_key=QDRANT_API_KEY,
#         prefer_grpc=False,
#         timeout=timeout,
#         check_compatibility=False,
#     )
#
# client = get_qdrant_client()
# =====================================================================


def _read_chunks() -> list:
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


def _write_chunks(chunks: list) -> None:
    temp_file = CHUNKS_FILE.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    temp_file.replace(CHUNKS_FILE)


class _DummyCollectionInfo:
    def __init__(self, count: int):
        self.points_count = count


class _FileVectorClient:
    """Mock client interface to maintain compatibility with Qdrant calls."""

    def collection_exists(self, collection_name: str) -> bool:
        return True

    def get_collection(self, collection_name: str):
        return _DummyCollectionInfo(len(_read_chunks()))

    def delete(self, collection_name: str, points_selector: list = None, **kwargs):
        """Delete points by chunk ID from vector_chunks.json."""
        if not points_selector:
            return
        chunks = _read_chunks()
        ids_to_del = {str(pid) for pid in points_selector}
        new_chunks = [c for c in chunks if str(c.get("chunk_id")) not in ids_to_del]
        _write_chunks(new_chunks)

    def upsert(self, collection_name: str, points: list, **kwargs):
        pass

    def create_payload_index(self, *args, **kwargs):
        pass


_client_instance = _FileVectorClient()


def get_qdrant_client(timeout: int = 45) -> _FileVectorClient:
    return _client_instance


client = _client_instance


def test_qdrant_connection() -> dict:
    """Diagnostic check confirming JSON file vector storage is active."""
    chunks = _read_chunks()
    return {
        "status": "ok",
        "mode": "json_file_storage",
        "collection": COLLECTION_NAME,
        "exists": True,
        "points_count": len(chunks),
    }


def setup_collection():
    """Verify or initialize vector_chunks.json in the project base directory."""
    _read_chunks()
    print(f"JSON File Vector Storage active for collection '{COLLECTION_NAME}'.")
    print(f"File location: {CHUNKS_FILE}")


if __name__ == "__main__":
    setup_collection()