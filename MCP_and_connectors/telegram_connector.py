from re import A
import sys
from pathlib import Path

# Add project root and virtualenv site-packages to sys.path


import os
import json
import asyncio

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from MCP_and_connectors.normalizer import normalize_message

load_dotenv()

from databases.Normal_database.sync_store import (
    get_sync_checkpoint,
    save_sync_checkpoint,
    get_connected_account,
)

BASE_DIR = Path(__file__).resolve().parent
TELEGRAM_DIR = BASE_DIR / "telegram"
SESSION_FILE = TELEGRAM_DIR / "mindmesh_telegram"
CHECKPOINT_FILE = TELEGRAM_DIR / "sync_checkpoints.json"

TELEGRAM_DIR.mkdir(parents=True, exist_ok=True)

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")


def load_checkpoints(user_id=None, account_id=None):
    if user_id:
        cp = get_sync_checkpoint(user_id, "TELEGRAM", account_id or "default")
        if cp and "checkpoint_data" in cp:
            return cp["checkpoint_data"]

    # Local file checkpoint fallback (commented out in favor of database)
    # if not CHECKPOINT_FILE.exists():
    #     return {"telegram": {}}
    # with CHECKPOINT_FILE.open("r", encoding="utf-8") as f:
    #     return json.load(f)

    return {"telegram": {}}


def save_checkpoints(checkpoints, user_id=None, account_id=None):
    if user_id:
        try:
            save_sync_checkpoint(
                user_id,
                "TELEGRAM",
                account_id or "default",
                checkpoints,
            )
        except Exception as err:
            print(f"Warning: Failed to save Telegram checkpoint to database: {err}")

    # Local file checkpoint saving (commented out in favor of database)
    # temp_file = CHECKPOINT_FILE.with_suffix(".tmp")
    # temp_file.write_text(
    #     json.dumps(checkpoints, indent=2),
    #     encoding="utf-8",
    # )
    # temp_file.replace(CHECKPOINT_FILE)


async def fetch_telegram_messages(limit_per_chat=1, initial_sync=False, user_id=None):
    records = []
    if not user_id:
        print("[Telegram] Error: user_id is required to fetch Telegram messages.")
        return []
    checkpoints = load_checkpoints(user_id=user_id)
    telegram_checkpoints = checkpoints.setdefault("telegram", {})

    
    
    account_id = "default"

    acc = get_connected_account(
        user_id=user_id,
        source="TELEGRAM",
    )

    if not acc:
        print(
            f"[Telegram] No connected account for user {user_id}."
        )
        return []

    if str(acc.get("user_id")) != str(user_id):
        raise RuntimeError(
            "Telegram account ownership mismatch. "
            "Refusing to fetch messages."
        )

    creds = acc.get("auth_credentials")

    if isinstance(creds, str):
        creds = json.loads(creds)

    if not isinstance(creds, dict):
        raise RuntimeError("Invalid Telegram authentication credentials.")

    sess_str = creds.get("session_string")

    if not isinstance(sess_str, str) or not sess_str.strip():
        raise RuntimeError(
            "Telegram session is missing. Reconnect Telegram "
            "through the website."
        )

    client = TelegramClient(
        StringSession(sess_str),
        API_ID,
        API_HASH,
    )



    async with client:
        me = await client.get_me()
        if not me:
            raise RuntimeError("Telegram client could not get user profile. Check credentials.")
        account_id = str(me.id)

        # Each chat has its own message ID checkpoint.
        async for dialog in client.iter_dialogs():
            chat = dialog.entity
            chat_id = str(dialog.id)
            last_id = int(telegram_checkpoints.get(chat_id, 0))

            # First run imports a bounded number per chat.
            # Later runs request messages newer than the saved ID.
            if initial_sync or last_id == 0:
                iterator = client.iter_messages(
                    chat, limit=limit_per_chat
                )
            else:
                iterator = client.iter_messages(
                    chat, min_id=last_id, reverse=True
                )

            newest_id = last_id

            async for message in iterator:
                if not message.message:
                    continue

                sender = "Unknown"
                if message.sender:
                    sender = (
                        getattr(message.sender, "username", None)
                        or getattr(message.sender, "first_name", None)
                        or str(message.sender_id)
                    )

                records.append(
                    normalize_message(
                        source="telegram",
                        message_id=message.id,
                        conversation_id=chat_id,
                        sender=sender,
                        subject=(
                            dialog.name or chat_id
                        ),
                        text=message.message,
                        timestamp=message.date.isoformat(),
                        account_id=account_id,
                    )
                )

                newest_id = max(newest_id, message.id)

            if newest_id > last_id:
                telegram_checkpoints[chat_id] = newest_id

        # Save only after all dialogs have been processed.
        # Save only after all dialogs have been processed.
        save_checkpoints(
            checkpoints, user_id=user_id, account_id=account_id
        )

    return records


def get_telegram_messages(limit_per_chat=100, initial_sync=False, user_id=None):
    return asyncio.run(
        fetch_telegram_messages(
            limit_per_chat=limit_per_chat,
            initial_sync=initial_sync,
            user_id=user_id,
        )
    )



# if __name__ == "__main__":
#     messages = get_telegram_messages(
#         limit_per_chat=100,
#         initial_sync=False,
#     )

#     output_dir = BASE_DIR / "output"
#     output_dir.mkdir(exist_ok=True)

#     output_file = output_dir / "telegram_messages.json"

#     # Load existing records
#     existing = []
#     if output_file.exists():
#         with output_file.open("r", encoding="utf-8") as f:
#             existing = json.load(f)

#     # Merge without duplicating messages
#     merged = {
#         (m["account_id"], m["conversation_id"], m["message_id"]): m
#         for m in existing
#     }

#     for message in messages:
#         key = (
#             message["account_id"],
#             message["conversation_id"],
#             message["message_id"],
#         )
#         merged[key] = message

#     output_file.write_text(
#         json.dumps(list(merged.values()), indent=2, ensure_ascii=False),
#         encoding="utf-8",
#     )

#     print(f"Fetched {len(messages)} new messages.")
#     print(f"Total stored messages: {len(merged)}")
#     print(f"JSON saved to: {output_file}")