
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
CHAT_MEMORY_FILE = BASE_DIR / "chat_memory.json"

# =====================================================================
# SQLITE DATABASE CODE COMMENTED OUT FOR FILE STORAGE
# =====================================================================
# import sqlite3
# DB_PATH = Path(__file__).parent / "chat_memory.db"
#
# def _original_connect():
#     conn = sqlite3.connect(DB_PATH)
#     conn.execute("CREATE TABLE IF NOT EXISTS messages (...)")
#     conn.execute("CREATE TABLE IF NOT EXISTS memories (...)")
#     return conn
# =====================================================================


class _DummySqliteConn:
    def execute(self, *args, **kwargs):
        return self
    def fetchall(self):
        return []
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def connect():
    """Dummy connection for backward compatibility."""
    return _DummySqliteConn()


def _read_memory() -> Dict[str, List[Any]]:
    if not CHAT_MEMORY_FILE.exists():
        initial = {"messages": [], "memories": []}
        with open(CHAT_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(initial, f, indent=2)
        return initial
    try:
        with open(CHAT_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"messages": [], "memories": []}
            data.setdefault("messages", [])
            data.setdefault("memories", [])
            return data
    except Exception:
        return {"messages": [], "memories": []}


def _write_memory(data: Dict[str, List[Any]]) -> None:
    temp_file = CHAT_MEMORY_FILE.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    temp_file.replace(CHAT_MEMORY_FILE)


def get_recent_messages(user_id, limit=10):
    target_uid = str(user_id)
    data = _read_memory()
    messages = data.get("messages", [])

    # Filter messages for user (or all messages in single-user mode)
    matching = [
        m for m in messages
        if str(m.get("user_id")) == target_uid or target_uid in ("single_user", "user_123", "")
    ]
    if not matching and messages:
        # Single-user fallback
        matching = messages

    # Get last `limit` messages
    slice_start = max(0, len(matching) - limit)
    recent = matching[slice_start:]

    return [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in recent
    ]


def save_message(user_id, role, content):
    data = _read_memory()
    now_iso = datetime.now(timezone.utc).isoformat()
    new_msg = {
        "id": len(data.get("messages", [])) + 1,
        "user_id": str(user_id),
        "role": str(role),
        "content": str(content),
        "timestamp": now_iso,
    }
    data.setdefault("messages", []).append(new_msg)
    _write_memory(data)


def get_long_term_memory(user_id):
    target_uid = str(user_id)
    data = _read_memory()
    memories = data.get("memories", [])

    matching = [
        m.get("fact", "") for m in memories
        if str(m.get("user_id")) == target_uid or target_uid in ("single_user", "user_123", "")
    ]
    if not matching and memories:
        matching = [m.get("fact", "") for m in memories]

    return [f for f in matching if f]


def remember(user_id, fact):
    fact = fact.strip()
    if not fact or len(fact) > 300:
        return False

    target_uid = str(user_id)
    data = _read_memory()
    memories = data.setdefault("memories", [])

    # Check for duplicate fact for this user
    for m in memories:
        if (str(m.get("user_id")) == target_uid or target_uid in ("single_user", "user_123")) and m.get("fact") == fact:
            return True

    now_iso = datetime.now(timezone.utc).isoformat()
    memories.append({
        "id": len(memories) + 1,
        "user_id": target_uid,
        "fact": fact,
        "created_at": now_iso,
    })
    _write_memory(data)
    return True

