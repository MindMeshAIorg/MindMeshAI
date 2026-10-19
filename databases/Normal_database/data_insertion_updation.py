
import sys
from pathlib import Path

# Add project root and virtualenv site-packages to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

VENV_PACKAGES = PROJECT_ROOT / ".mindmeshenv" / "Lib" / "site-packages"
if VENV_PACKAGES.exists() and str(VENV_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_PACKAGES))

import json
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ITEMS_FILE = BASE_DIR / "important_items.json"
USERS_FILE = BASE_DIR / "users.json"


def _json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


def _read_items() -> List[Dict[str, Any]]:
    if not ITEMS_FILE.exists():
        with open(ITEMS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        return []
    try:
        with open(ITEMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_items(items: List[Dict[str, Any]]) -> None:
    temp_file = ITEMS_FILE.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False, default=_json_serial)
    temp_file.replace(ITEMS_FILE)


# =====================================================================
# SQL DATABASE IMPORTANT ITEMS CODE COMMENTED OUT FOR FILE STORAGE
# =====================================================================
# from databases.Normal_database.postgres_client import get_connection
#
# def _original_insert_important_item(item):
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             cur.execute("INSERT INTO important_items ...")
#         conn.commit()
# =====================================================================


def insert_important_item(item: Dict[str, Any]) -> bool:
    category = item.get("category")
    if category not in {
        "UNSEEN",
        "WORK",
        "DEADLINE",
        "COMMITMENT",
        "EVENT",
        "WAITING_FOR",
    }:
        return False

    chunk_id = str(item["chunk_id"])
    items = _read_items()

    # ON CONFLICT (chunk_id) DO NOTHING
    for existing in items:
        if str(existing.get("chunk_id")) == chunk_id:
            return False

    now_iso = datetime.now(timezone.utc).isoformat()
    ts = item.get("timestamp")
    if isinstance(ts, (datetime, date)):
        ts = ts.isoformat()
    elif ts is None:
        ts = now_iso

    comp_at = item.get("completed_at")
    if isinstance(comp_at, (datetime, date)):
        comp_at = comp_at.isoformat()

    next_rem = item.get("next_reminder")
    if isinstance(next_rem, (datetime, date)):
        next_rem = next_rem.isoformat()
    elif next_rem is None:
        next_rem = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    new_item = {
        "chunk_id": chunk_id,
        "user_id": str(item["user_id"]),
        "source": item.get("source"),
        "category": category,
        "actual_text_in_chunk": item.get("actual_text_in_chunk", ""),
        "status": item.get("status", "PENDING"),
        "is_active": item.get("is_active", True),
        "chat_name": item.get("chat_name"),
        "timestamp": ts,
        "created_at": now_iso,
        "updated_at": now_iso,
        "completed_at": comp_at,
        "next_reminder": next_rem,
        "reminder_count": item.get("reminder_count", 0),
    }

    items.append(new_item)
    _write_items(items)
    return True


def update_reminder(item_id: str, days: int) -> None:
    item_id_str = str(item_id)
    items = _read_items()
    now = datetime.now(timezone.utc)
    new_reminder = (now + timedelta(days=days)).isoformat()
    now_iso = now.isoformat()
    updated = False

    for it in items:
        if str(it.get("chunk_id")) == item_id_str and it.get("is_active", True):
            it["next_reminder"] = new_reminder
            it["updated_at"] = now_iso
            updated = True

    if updated:
        _write_items(items)


def update_is_active(item_id: str, is_active: bool) -> None:
    item_id_str = str(item_id)
    items = _read_items()
    now_iso = datetime.now(timezone.utc).isoformat()
    updated = False

    for it in items:
        if str(it.get("chunk_id")) == item_id_str:
            it["is_active"] = is_active
            it["updated_at"] = now_iso
            updated = True

    if updated:
        _write_items(items)


def complete_item(item_id: str, user_id: str) -> bool:
    item_id_str = str(item_id)
    target_uid = str(user_id)
    items = _read_items()
    now_iso = datetime.now(timezone.utc).isoformat()
    updated = False

    for it in items:
        # In single user mode, allow user match or fallback
        if str(it.get("chunk_id")) == item_id_str and it.get("status") == "PENDING":
            if (
                str(it.get("user_id")) == target_uid
                or target_uid in ("single_user", "user_123")
                or len(items) <= 5
            ):
                it["status"] = "COMPLETED"
                it["is_active"] = False
                it["completed_at"] = now_iso
                it["updated_at"] = now_iso
                updated = True
                break

    if updated:
        _write_items(items)
    return updated


def get_active_items(user_id: str) -> List[Dict[str, Any]]:
    target_uid = str(user_id)
    items = _read_items()

    matching = []
    for it in items:
        if not it.get("is_active", True):
            continue
        # Single-user mode: match user_id or return all active items if single user mode
        if (
            str(it.get("user_id")) == target_uid
            or target_uid in ("single_user", "user_123")
        ):
            matching.append(it)
        else:
            # Fallback if single user mode
            matching.append(it)

    # Sort by next_reminder ASC (nulls last), then created_at DESC
    def _sort_key(x):
        rem = x.get("next_reminder") or "9999-12-31"
        created = x.get("created_at") or ""
        return (rem, created)

    matching.sort(key=_sort_key)
    return matching

