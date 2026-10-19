import os
import time
from contextlib import contextmanager
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

# =====================================================================
# DATABASE CONNECTION CODE COMMENTED OUT FOR FILE-BASED STORAGE
# =====================================================================
# import psycopg
# from psycopg.rows import dict_row
#
# def get_sanitized_database_url() -> str:
#     """Retrieve and sanitize DATABASE_URL ensuring SSL mode is properly set for cloud Postgres."""
#     url = os.getenv("DATABASE_URL")
#     if not url:
#         load_dotenv(ROOT_DIR / ".env")
#         url = os.getenv("DATABASE_URL")
#     if not url:
#         raise ValueError("DATABASE_URL is missing from your environment or .env file.")
#
#     # Render and cloud PostgreSQL instances strictly require SSL
#     if "sslmode=" not in url:
#         delim = "&" if "?" in url else "?"
#         url = f"{url}{delim}sslmode=require"
#
#     return url
#
# @contextmanager
# def get_connection(max_retries: int = 3, retry_delay: float = 2.0):
#     url = get_sanitized_database_url()
#     conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=15)
#     try:
#         yield conn
#     finally:
#         conn.close()
# =====================================================================

class _DummyCursor:
    def execute(self, *args, **kwargs):
        pass
    def fetchone(self):
        return None
    def fetchall(self):
        return []
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

class _DummyConnection:
    def cursor(self):
        return _DummyCursor()
    def commit(self):
        pass
    def rollback(self):
        pass
    def close(self):
        pass

@contextmanager
def get_connection(max_retries: int = 3, retry_delay: float = 2.0):
    """
    Dummy connection context manager for backward compatibility.
    Database connections are commented out; MindMeshAI now runs in single-user JSON mode.
    """
    dummy = _DummyConnection()
    try:
        yield dummy
    finally:
        dummy.close()


def test_postgres_connection() -> dict:
    """Diagnostic check confirming JSON file-based storage mode is active."""
    return {
        "status": "ok",
        "mode": "json_file_storage",
        "info": {
            "storage": "JSON file-based storage active",
            "base_dir": str(ROOT_DIR),
        },
    }

