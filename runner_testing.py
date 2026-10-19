
import asyncio
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

from MCP_and_connectors.whatsapp_connector import whatsapp_loader
from MCP_and_connectors.privacy_filter import sanitize_records
from MCP_and_connectors.gmail_connector import fetch_gmail
from MCP_and_connectors.telegram_connector import fetch_telegram_messages

from RAG.chunking import create_chunks
from RAG.embedding import generate_embeddings

from databases.Normal_database.data_insertion_updation import (
    insert_important_item,
)
from notification_pipeline.storing_notifications_data import (
    notification_data_structure,
)
from databases.Normal_database.sync_store import (
    get_users_with_connected_accounts,
    get_user_by_id_or_username,
    get_connected_account,
    get_sync_checkpoint,
)
from notification_pipeline.notification_creation import (
    summarize_notification_batches,
)


# ==============================
# Configuration
# ==============================

BASE_DIR = Path(__file__).resolve().parent

MODEL_NAME = "BAAI/bge-m3"

# JSON test file in the base directory
RAG_TEST_FILE = BASE_DIR / "rag_runner_teting.json"

WHATSAPP_CHUNK_SIZE = 10
GMAIL_CHUNK_SIZE = 1
TELEGRAM_CHUNK_SIZE = 10

EMBEDDING_BATCH_SIZE = 8
TELEGRAM_LIMIT_PER_CHAT = 10


# ==============================
# JSON File Storage
# ==============================

def make_json_serializable(value):
    """Convert NumPy arrays, tensors and nested objects to JSON-safe values."""

    if isinstance(value, dict):
        return {
            str(key): make_json_serializable(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [make_json_serializable(item) for item in value]

    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, np.generic):
        return value.item()

    # Handle PyTorch tensors if present.
    try:
        import torch

        if isinstance(value, torch.Tensor):
            return value.detach().cpu().tolist()
    except ImportError:
        pass

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    # Support objects exposing a standard dictionary representation.
    if hasattr(value, "model_dump"):
        return make_json_serializable(value.model_dump())

    if hasattr(value, "to_dict"):
        return make_json_serializable(value.to_dict())

    raise TypeError(
        f"Cannot serialize object of type {type(value).__name__}"
    )


def save_chunks_to_json(chunks, user_id):
    """
    Save embedded chunks to the base-directory JSON file.

    Creates the file if missing and appends chunks without
    deleting existing test data.
    """

    RAG_TEST_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Initialize the file if it does not exist.
    if not RAG_TEST_FILE.exists():
        RAG_TEST_FILE.write_text("[]", encoding="utf-8")

    # Load existing test chunks.
    try:
        with RAG_TEST_FILE.open("r", encoding="utf-8") as file:
            existing_chunks = json.load(file)

        if not isinstance(existing_chunks, list):
            raise ValueError("Expected a JSON array in the test file.")

    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(
            f"{RAG_TEST_FILE.name} contains invalid JSON. "
            "Back it up and repair it before continuing."
        ) from error

    # Normalize chunks and attach ownership metadata.
    new_chunks = []

    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise TypeError(
                f"Expected each chunk to be a dictionary, "
                f"got {type(chunk).__name__}"
            )

        chunk_copy = dict(chunk)
        chunk_copy.setdefault("payload", {})

        if isinstance(chunk_copy["payload"], dict):
            chunk_copy["payload"].setdefault("user_id", user_id)

        chunk_copy["user_id"] = user_id

        new_chunks.append(make_json_serializable(chunk_copy))

    # Append, preserving existing chunks.
    existing_chunks.extend(new_chunks)

    # Write the updated file.
    with RAG_TEST_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            existing_chunks,
            file,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )

    print(f"Saved {len(new_chunks)} chunks to {RAG_TEST_FILE}")
    print(f"Total chunks in test file: {len(existing_chunks)}")


# ==============================
# Connector: WhatsApp
# ==============================

async def load_whatsapp(user_id: str, initial_sync: bool = False):
    print(f"\n[WhatsApp] Fetching messages for user {user_id}...")

    try:
        messages = await whatsapp_loader(
            initial_sync=initial_sync,
            user_id=user_id,
            chat_name="abubakkar",
        )

        if isinstance(messages, dict):
            messages = messages.get("messages", [])

        print(
            f"[WhatsApp] Fetched {len(messages)} messages "
            f"for user {user_id}."
        )
        return messages

    except Exception as error:
        print(f"[WhatsApp] Import failed for user {user_id}: {error}")
        return []


# ==============================
# Connector: Gmail
# ==============================

def load_gmail(user_id: str, initial_sync: bool = False):
    print(f"\n[Gmail] Fetching messages for user {user_id}...")

    try:
        acc = get_connected_account(user_id, "GMAIL")

        account_email = (
            acc.get("account_identifier")
            if acc
            else os.getenv(
                "GMAIL_DEFAULT_ACCOUNT",
                "abdulhannanifteqar765@gmail.com",
            )
        )

        db_cp = get_sync_checkpoint(
            user_id, "GMAIL", account_email
        )

        checkpoint_file = (
            BASE_DIR
            / "MCP_and_connectors"
            / "gmail"
            / "sync_checkpoint.json"
        )

        if not initial_sync and (
            db_cp or checkpoint_file.exists()
        ):
            days = 1
        else:
            days = int(os.getenv("GMAIL_SYNC_DAYS", "3"))

        messages = fetch_gmail(
            days=days,
            user_id=user_id,
            account_id=account_email,
        )

        print(
            f"[Gmail] Fetched {len(messages)} messages "
            f"for {account_email} (user: {user_id})."
        )
        return messages

    except Exception as error:
        print(f"[Gmail] Import failed for user {user_id}: {error}")
        return []


# ==============================
# Connector: Telegram
# ==============================

async def load_telegram(user_id: str, initial_sync: bool = False):
    print(f"\n[Telegram] Fetching messages for user {user_id}...")

    try:
        messages = await fetch_telegram_messages(
            limit_per_chat=TELEGRAM_LIMIT_PER_CHAT,
            initial_sync=initial_sync,
            user_id=user_id,
        )

        print(
            f"[Telegram] Fetched {len(messages)} messages "
            f"for user {user_id}."
        )
        return messages

    except Exception as error:
        print(f"[Telegram] Import failed for user {user_id}: {error}")
        return []


# ==============================
# Per-User Ingestion Pipeline
# ==============================

async def run_ingestion_for_user(
    user_id: str,
    username: str = "User",
    initial_sync: bool = False,
):
    print("\n" + "=" * 60)
    print(f"Processing Ingestion for: {username} (ID: {user_id})")
    print(
        f"Mode: "
        f"{'Initial / Window Sync' if initial_sync else 'Incremental Sync'}"
    )
    print("=" * 60)

    # 1. Fetch messages from all sources.
    whatsapp_messages = []
    gmail_messages = []
    telegram_messages = []

    try:
        whatsapp_messages = await load_whatsapp(
            user_id=user_id,
            initial_sync=initial_sync,
        )
    except Exception as error:
        print(f"WhatsApp loading error: {error}")

    try:
        gmail_messages = load_gmail(
            user_id=user_id,
            initial_sync=initial_sync,
        )
    except Exception as error:
        print(f"Gmail loading error: {error}")

    try:
        telegram_messages = await load_telegram(
            user_id=user_id,
            initial_sync=initial_sync,
        )
    except Exception as error:
        print(f"Telegram loading error: {error}")

    messages = (
        whatsapp_messages
        + gmail_messages
        + telegram_messages
    )

    print(f"\n--- Ingestion Summary for {username} ---")
    print(f"WhatsApp: {len(whatsapp_messages)} messages")
    print(f"Gmail:    {len(gmail_messages)} messages")
    print(f"Telegram: {len(telegram_messages)} messages")
    print(f"Total:    {len(messages)} messages")

    if not messages:
        print(
            f"No new messages to process for {username} ({user_id})."
        )
        return

    # 2. Create chunks.
    print(f"\n[1/3] Creating chunks for {username}...")

    try:
        chunks = create_chunks(
            messages=messages,
            whatsapp_chunk_size=WHATSAPP_CHUNK_SIZE,
            gmail_chunk_size=GMAIL_CHUNK_SIZE,
            telegram_chunk_size=TELEGRAM_CHUNK_SIZE,
            user_id=user_id,
        )

        print(f"Created {len(chunks)} chunks.")

    except Exception as error:
        print(f"Chunk creation failed for {username}: {error}")
        return

    # 3. Store notifications in PostgreSQL as before.
    notification_chunks = notification_data_structure(chunks)
    notification_chunks = summarize_notification_batches(
        notification_chunks
    )

    inserted_count = 0

    for item in notification_chunks:
        item["user_id"] = user_id

        if insert_important_item(item):
            inserted_count += 1

    print(f"Important notifications stored: {inserted_count}")

    if not chunks:
        print("No chunks created.")
        return

    # 4. Generate embeddings.
    print(f"\n[2/3] Generating BGE-M3 embeddings for {username}...")

    try:
        embedded_chunks = generate_embeddings(
            chunks,
            MODEL_NAME,
            EMBEDDING_BATCH_SIZE,
        )

        if not embedded_chunks:
            print("Embedding returned no results. Skipping JSON storage.")
            return

        print(
            f"Generated embeddings for {len(embedded_chunks)} chunks."
        )

    except Exception as error:
        print(f"Embedding generation failed: {error}")
        return

    # 5. Save embedded chunks to JSON instead of Qdrant.
    print(f"\n[3/3] Saving chunks to JSON for {username}...")

    try:
        save_chunks_to_json(
            chunks=embedded_chunks,
            user_id=user_id,
        )

        print(
            f"Ingestion completed successfully for "
            f"{username} ({user_id})."
        )

    except Exception as error:
        print(f"JSON storage failed for {username}: {error}")


# ==============================
# Main Multi-User Runner
# ==============================

def get_target_users() -> list[dict[str, str]]:
    """
    Determine which users to ingest:
    1. CLI argument
    2. ACTIVE_USER_ID environment variable
    3. All users with connected accounts
    """

    args = [
        arg for arg in sys.argv[1:]
        if not arg.startswith("-")
    ]

    if args:
        identifier = args[0].strip()
        user_match = get_user_by_id_or_username(identifier)

        if user_match:
            print(
                f"[User Resolver] Targeting specific user: "
                f"{user_match['username']} ({user_match['user_id']})"
            )
            return [user_match]

        print(
            f"[User Resolver] Targeting specified ID directly: "
            f"{identifier}"
        )
        return [{"user_id": identifier, "username": identifier}]

    env_uid = os.getenv("ACTIVE_USER_ID")

    if env_uid:
        user_match = get_user_by_id_or_username(env_uid)

        if user_match:
            print(
                f"[User Resolver] Targeting user from "
                f"ACTIVE_USER_ID env: {user_match['username']}"
            )
            return [user_match]

        return [{"user_id": env_uid, "username": env_uid}]

    connected_users = get_users_with_connected_accounts()

    if connected_users:
        print(
            f"[User Resolver] Found {len(connected_users)} "
            f"registered user(s) with connected accounts:"
        )

        for user in connected_users:
            print(
                f"  - {user['username']} (ID: {user['user_id']})"
            )

        return connected_users

    print(
        "[User Resolver] No registered users with active "
        "connected accounts found in PostgreSQL."
    )
    return []


async def main():
    initial_sync = (
        "--initial" in sys.argv
        or "--fresh" in sys.argv
    )

    users_to_process = get_target_users()

    if not users_to_process:
        print(
            "[Ingestion Runner] No users to process. "
            "Ingestion terminated."
        )
        return

    print("\n" + "#" * 60)
    print("MindMeshAI Multi-User Ingestion Runner")
    print(f"Total Users to Ingest: {len(users_to_process)}")
    print(
        f"Mode: "
        f"{'Initial / Window Sync' if initial_sync else 'Incremental Sync'}"
    )
    print(f"JSON test file: {RAG_TEST_FILE}")
    print("#" * 60)

    for user_info in users_to_process:
        uid = user_info["user_id"]
        username = user_info.get("username", "User")

        await run_ingestion_for_user(
            user_id=uid,
            username=username,
            initial_sync=initial_sync,
        )

    print("\nAll user ingestions completed.")


if __name__ == "__main__":
    asyncio.run(main())
