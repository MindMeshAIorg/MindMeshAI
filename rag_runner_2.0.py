import asyncio
import os
import sys
from pathlib import Path

from MCP_and_connectors.whatsapp_connector import whatsapp_loader
from MCP_and_connectors.privacy_filter import sanitize_records
from MCP_and_connectors.gmail_connector import fetch_gmail
from MCP_and_connectors.telegram_connector import fetch_telegram_messages

from RAG.chunking import create_chunks
from RAG.embedding import generate_embeddings

from databases.Vector_Database.insertion_in_vectorDB import store_chunks
from databases.Normal_database.data_insertion_updation import insert_important_item
from notification_pipeline.storing_notifications_data import notification_data_structure
from databases.Normal_database.sync_store import (
    get_users_with_connected_accounts,
    get_user_by_id_or_username,
    get_connected_account,
    get_sync_checkpoint,
)
from notification_pipeline.notification_creation import summarize_notification_batches


# ==============================
# Configuration
# ==============================

BASE_DIR = Path(__file__).resolve().parent

MODEL_NAME = "BAAI/bge-m3"

WHATSAPP_CHUNK_SIZE = 10
GMAIL_CHUNK_SIZE = 1
TELEGRAM_CHUNK_SIZE = 10

EMBEDDING_BATCH_SIZE = 8
TELEGRAM_LIMIT_PER_CHAT = 100


# ==============================
# Connector: WhatsApp
# ==============================

async def load_whatsapp(user_id: str, initial_sync: bool = False):
    print(f"\n[WhatsApp] Fetching messages for user {user_id}...")

    target_chat = os.getenv("WHATSAPP_TARGET_CHAT", None)
    try:
        messages = await whatsapp_loader(
            initial_sync=initial_sync,
            user_id=user_id,
            chat_name=target_chat,
        )

        if isinstance(messages, dict):
            messages = messages.get("messages", [])

        print(f"[WhatsApp] Fetched {len(messages)} messages for user {user_id}.", flush=True)
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
        account_email = acc.get("account_identifier") if acc else os.getenv("GMAIL_DEFAULT_ACCOUNT", "abdulhannanifteqar765@gmail.com")

        db_cp = get_sync_checkpoint(user_id, "GMAIL", account_email)
        checkpoint_file = BASE_DIR / "MCP_and_connectors" / "gmail" / "sync_checkpoint.json"

        if not initial_sync and (db_cp or checkpoint_file.exists()):
            days = 1
        else:
            days = int(os.getenv("GMAIL_SYNC_DAYS", "3"))

        messages = fetch_gmail(days=days, user_id=user_id, account_id=account_email)

        print(f"[Gmail] Fetched {len(messages)} messages for {account_email} (user: {user_id}).")
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

        print(f"[Telegram] Fetched {len(messages)} messages for user {user_id}.")
        return messages

    except Exception as error:
        print(f"[Telegram] Import failed for user {user_id}: {error}")
        return []


# ==============================
# Per-User Ingestion Pipeline
# ==============================

async def run_ingestion_for_user(user_id: str, username: str = "User", initial_sync: bool = False):
    """
    Runs the complete ingestion and vectorization pipeline strictly for one user.
    All chunks and database records are isolated with payload['user_id'] = user_id.
    """
    print("\n" + "=" * 60)
    print(f" Processing Ingestion for: {username} (ID: {user_id})")
    print(f" Mode: {'Initial / Window Sync' if initial_sync else 'Incremental Sync'}")
    print("=" * 60)

    # 1. Fetch from all sources
    whatsapp_messages = []
    gmail_messages = []
    telegram_messages = []

    try:
        whatsapp_messages = await load_whatsapp(user_id=user_id, initial_sync=initial_sync)
    except Exception as error:
        print(f"WhatsApp loading error: {error}")

    try:
        gmail_messages = load_gmail(user_id=user_id, initial_sync=initial_sync)
    except Exception as error:
        print(f"Gmail loading error: {error}")

    try:
        telegram_messages = await load_telegram(user_id=user_id, initial_sync=initial_sync)
    except Exception as error:
        print(f"Telegram loading error: {error}")

    messages = whatsapp_messages + gmail_messages + telegram_messages

    print(f"\n--- Ingestion Summary for {username} ---")
    print(f"WhatsApp: {len(whatsapp_messages)} messages")
    print(f"Gmail:    {len(gmail_messages)} messages")
    print(f"Telegram: {len(telegram_messages)} messages")
    print(f"Total:    {len(messages)} messages")

    if not messages:
        print(f"No new messages to process for user {username} ({user_id}).")
        return

    # 2. Create chunks isolated for this user
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

    # 3. Store notifications in database isolated by user_id
    notification_chunks = notification_data_structure(chunks)
    notification_chunks=summarize_notification_batches(notification_chunks)
    inserted_count = 0
    for item in notification_chunks:
        item["user_id"] = user_id
        if insert_important_item(item):
            inserted_count += 1

    print(f"Important notifications stored: {inserted_count}")

    if not chunks:
        return

    # 4. Generate embeddings
    print(f"\n[2/3] Generating BGE-M3 embeddings for {username}...")
    try:
        embedded_chunks = generate_embeddings(
            chunks,
            MODEL_NAME,
            EMBEDDING_BATCH_SIZE,
        )
        if not embedded_chunks:
            print("Embedding returned no results. Skipping Qdrant insertion.")
            return
        print(f"Generated embeddings for {len(embedded_chunks)} chunks.")
    except Exception as error:
        print(f"Embedding generation failed: {error}")
        return

    # 5. Store chunks in Qdrant (filtered strictly by payload['user_id'] = user_id)
    print(f"\n[3/3] Storing chunks in Qdrant for {username}...")
    try:
        store_chunks(embedded_chunks)
        print(f"Ingestion completed successfully for {username} ({user_id}).")
    except Exception as error:
        print(f"Qdrant storage failed for {username}: {error}")


# ==============================
# Main Multi-User Runner
# ==============================

def get_target_users() -> list[dict[str, str]]:
    """
    Determine which user(s) to ingest for:
    - If a specific user is given via CLI (python rag_runner_2.0.py <id_or_username>), sync only that user.
    - If ACTIVE_USER_ID environment variable is set, sync only that user.
    - Otherwise, query PostgreSQL for ALL registered users with active connected accounts so NO user is starved.
    """
    # 1. CLI positional argument (e.g. `python rag_runner_2.0.py fahad`)
    args = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    if args:
        identifier = args[0].strip()
        user_match = get_user_by_id_or_username(identifier)
        if user_match:
            print(f"[User Resolver] Targeting specific user: {user_match['username']} ({user_match['user_id']})")
            return [user_match]
        print(f"[User Resolver] Targeting specified ID directly: {identifier}")
        return [{"user_id": identifier, "username": identifier}]

    # 2. Environment variable
    env_uid = os.getenv("ACTIVE_USER_ID")
    if env_uid:
        user_match = get_user_by_id_or_username(env_uid)
        if user_match:
            print(f"[User Resolver] Targeting user from ACTIVE_USER_ID env: {user_match['username']}")
            return [user_match]
        return [{"user_id": env_uid, "username": env_uid}]

    # 3. All registered users with connected accounts in PostgreSQL
    connected_users = get_users_with_connected_accounts()
    if connected_users:
        print(f"[User Resolver] Found {len(connected_users)} registered user(s) with connected accounts:")
        for u in connected_users:
            print(f"  - {u['username']} (ID: {u['user_id']})")
        return connected_users

    # No users found with connected accounts
    print("[User Resolver] No registered users with active connected accounts found in PostgreSQL.")
    return []


async def main():
    initial_sync = "--initial" in sys.argv or "--fresh" in sys.argv

    users_to_process = get_target_users()
    if not users_to_process:
        print("[Ingestion Runner] No users to process. Ingestion terminated.")
        return

    print("\n" + "#" * 60)
    print(" MindMeshAI Multi-User Ingestion Runner")
    print(f" Total Users to Ingest: {len(users_to_process)}")
    print(f" Mode: {'Initial / Window Sync' if initial_sync else 'Incremental Sync'}")
    print("#" * 60)

    for user_info in users_to_process:
        uid = user_info["user_id"]
        uname = user_info.get("username", "User")
        await run_ingestion_for_user(user_id=uid, username=uname, initial_sync=initial_sync)

    print("\nAll user ingestions completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
