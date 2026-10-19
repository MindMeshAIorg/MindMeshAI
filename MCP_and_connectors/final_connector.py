
import sys
from pathlib import Path



import json

from MCP_and_connectors.privacy_filter import sanitize_records
from MCP_and_connectors.gmail_connector import fetch_gmail
from MCP_and_connectors.telegram_connector import get_telegram_messages

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"


def save_json(filename, messages):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / filename

    # Preserve existing records
    existing = []
    if output_file.exists():
        try:
            existing = json.loads(
                output_file.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            # Do not overwrite a damaged file automatically.
            raise RuntimeError(
                f"Cannot safely read {output_file}. "
                "Restore or inspect it before continuing."
            )

    # Merge and deduplicate old and new records
    merged = {}

    for message in existing + messages:
        key = (
            message.get("user_id"),
            message.get("account_id"),
            message.get("source"),
            message.get("conversation_id"),
            message.get("message_id"),
        )
        merged[key] = message

    output_file.write_text(
        json.dumps(list(merged.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Fetched this run: {len(messages)} records.")
    print(f"Total stored: {len(merged)} records.")
    print(f"JSON saved to: {output_file}")


def main():
    checkpoint = BASE_DIR / "gmail" / "sync_checkpoint.json"

    # Ask for a date range only for the first Gmail import.
    if checkpoint.exists():
        days = 2  # Ignored by Gmail when an incremental checkpoint exists.
    else:
        days = int(input("Initial Gmail import: last how many days? "))
        if days < 1:
            raise ValueError("Enter a number of days greater than zero.")

    print("\nFetching Gmail messages...")
    try:
        gmail_messages = fetch_gmail(days=days)
        gmail_messages = sanitize_records(gmail_messages)
        save_json("gmail_messages.json", gmail_messages)
    except Exception as error:
        print(f"Gmail import failed: {error}")

    print("\nFetching Telegram messages...")
    try:
        telegram_messages = get_telegram_messages(
            limit_per_chat=100,
            initial_sync=False,
        )
        telegram_messages = sanitize_records(telegram_messages)
        save_json("telegram_messages.json", telegram_messages)
    except Exception as error:
        print(f"Telegram import failed: {error}")

    print("\nImport process finished.")


