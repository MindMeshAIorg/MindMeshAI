
import sys
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

for path in (PROJECT_ROOT, BASE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

VENV_PACKAGES = (
    PROJECT_ROOT / ".mindmeshenv" / "Lib" / "site-packages"
)

if VENV_PACKAGES.exists() and str(VENV_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_PACKAGES))

from notification_pipeline.slection import categorize


VALID_SOURCES = {"WHATSAPP", "EMAIL", "GMAIL", "TELEGRAM"}

VALID_CATEGORIES = {
    "UNSEEN",
    "WORK",
    "DEADLINE",
    "COMMITMENT",
    "EVENT",
    "WAITING_FOR",
}


def notification_data_structure(chunks):
    if isinstance(chunks, dict):
        chunks = [chunks]

    if not isinstance(chunks, list):
        raise TypeError("chunks must be a dictionary or list")

    notification_items = []

    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise TypeError("Each chunk must be a dictionary")

        payload = chunk.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        source = str(
            chunk.get("source")
            or payload.get("source_type")
            or ""
        ).strip().upper()

        if source not in VALID_SOURCES:
            print(f"Skipping unsupported source: {source!r}")
            continue

        actual_text = (
            chunk.get("text")
            or chunk.get("actual_text_in_chunk")
            or payload.get("actual_text_in_chunk")
        )

        if not isinstance(actual_text, str) or not actual_text.strip():
            print("Skipping chunk with empty text.")
            continue

        category = str(categorize(actual_text)).strip().upper()

        # Ordinary messages should not become reminder records.
        if category in {"NORMAL", "NONE", ""}:
            continue

        if category not in VALID_CATEGORIES:
            print(f"Skipping unsupported category: {category!r}")
            continue

        raw_timestamp = (
            chunk.get("timestamp")
            or payload.get("end_timestamp")
            or payload.get("start_timestamp")
        )

        if isinstance(raw_timestamp, datetime):
            parsed_timestamp = raw_timestamp
        elif isinstance(raw_timestamp, str) and raw_timestamp.strip():
            parsed_timestamp = datetime.fromisoformat(
                raw_timestamp.strip().replace("Z", "+00:00")
            )
        else:
            parsed_timestamp = None

        if parsed_timestamp and parsed_timestamp.tzinfo is not None:
            parsed_timestamp = parsed_timestamp.astimezone(
                timezone.utc
            ).replace(tzinfo=None)

        item = {
            "chunk_id": str(uuid.uuid4()),
            "user_id": chunk.get("user_id") or payload.get("user_id"),
            "source": source,
            "category": category,
            "actual_text_in_chunk": actual_text,
            "status": "PENDING",
            "is_active": True,
            "chat_name": (
                chunk.get("subject")
                or chunk.get("chat_name")
                or payload.get("subject")
                or chunk.get("conversation_id")
                or payload.get("conversation_id")
            ),
            "timestamp": parsed_timestamp,
            "completed_at": None,
            "next_reminder": (
                datetime.now(timezone.utc).replace(tzinfo=None)
                + timedelta(days=1)
            ),
            "reminder_count": 0,
        }

        notification_items.append(item)

    return notification_items
