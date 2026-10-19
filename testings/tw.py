import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
for p in (PROJECT_ROOT, BASE_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

VENV_PACKAGES = PROJECT_ROOT / ".mindmeshenv" / "Lib" / "site-packages"
if VENV_PACKAGES.exists() and str(VENV_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_PACKAGES))

import asyncio
import json
from datetime import date, datetime, time, timezone, timedelta
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from MCP_and_connectors.normalizer import normalize_message


BASE_DIR = Path(__file__).resolve().parent
CHECKPOINT_FILE = BASE_DIR / "whatsapp_sync_checkpoint.json"

# WSL path to the WhatsApp MCP executable.
SERVER_PATH = (
    "/mnt/c/Users/Abdul Hannan/OneDrive/Desktop/"
    "MindMeshAI/whatsapp-mcp-server/whatsapp-mcp"
)

BATCH_SIZE = 500
CHAT_LIST_LIMIT = 1000
ACCOUNT_ID = "default"

# India Standard Time is UTC+05:30.
IST = timezone(timedelta(hours=5, minutes=30))


def read_json(path: Path, default: Any) -> Any:
    """Read JSON from disk, returning default if the file does not exist."""
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def atomic_write_json(path: Path, data: Any) -> None:
    """Safely write JSON by replacing the destination atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temp_path.replace(path)


def message_key(message: dict) -> tuple[str, str, str]:
    """Build a stable deduplication key for a normalized message."""
    return (
        str(message.get("account_id") or ""),
        str(message.get("conversation_id") or ""),
        str(message.get("message_id") or ""),
    )


def extract_tool_data(result) -> dict:
    """Extract a dictionary from an MCP tool result."""
    if result.isError:
        raise RuntimeError(f"MCP tool failed: {result.content}")

    if result.structuredContent is not None:
        if isinstance(result.structuredContent, dict):
            return result.structuredContent
        raise RuntimeError("MCP structuredContent was not a JSON object.")

    for item in result.content:
        if getattr(item, "type", None) != "text":
            continue

        try:
            parsed = json.loads(item.text)
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(parsed, dict):
            return parsed

    raise RuntimeError("MCP response did not contain a structured JSON object.")


def parse_timestamp(value: Any) -> datetime | None:
    """Parse ISO-8601 or Unix timestamps and return an aware UTC datetime."""
    if value is None or value == "":
        return None

    try:
        if isinstance(value, (int, float)):
            seconds = value / 1000 if abs(value) > 10_000_000_000 else value
            return datetime.fromtimestamp(seconds, tz=timezone.utc)

        text_value = str(value).strip()

        try:
            numeric = float(text_value)
            seconds = (
                numeric / 1000
                if abs(numeric) > 10_000_000_000
                else numeric
            )
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except ValueError:
            pass

        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))

        # If the source has no timezone, assume UTC. Change this only if
        # the WhatsApp MCP server documents naive timestamps as local time.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError, OSError):
        return None


def normalize_whatsapp_message(
    message: dict,
    chat: dict,
    account_id: str,
) -> dict:
    """Convert a raw WhatsApp MCP message into the common record schema."""
    message_id = message.get("id") or message.get("message_id")
    timestamp = message.get("time") or message.get("timestamp")

    sender = (
        message.get("sender")
        or message.get("sender_name")
        or message.get("sender_jid")
        or "Unknown"
    )

    text_value = message.get("text")
    if text_value is None:
        text_value = message.get("content", "")

    conversation_id = message.get("chat_jid") or chat.get("jid")

    return normalize_message(
        source="whatsapp",
        message_id=message_id,
        conversation_id=conversation_id,
        sender=sender,
        subject=chat.get("name") or conversation_id,
        text=text_value or "",
        timestamp=timestamp,
        account_id=account_id,
    )


async def call_tool(
    session: ClientSession,
    name: str,
    arguments: dict,
) -> dict:
    """Call an MCP tool and return its parsed object response."""
    result = await session.call_tool(name, arguments=arguments)
    return extract_tool_data(result)


def _sort_records(records: list[dict]) -> list[dict]:
    return sorted(
        records,
        key=lambda record: (
            parse_timestamp(record.get("timestamp"))
            or datetime.min.replace(tzinfo=timezone.utc),
            record.get("conversation_id") or "",
            record.get("message_id") or "",
        ),
    )


async def fetch_chat_messages(
    session: ClientSession,
    chat: dict,
    account_id: str,
    start_datetime: datetime | None,
    after_checkpoint: str | None,
    initial_sync: bool,
) -> list[dict]:
    """
    Fetch and deduplicate messages from one chat.

    If start_datetime is provided, it is the inclusive lower boundary.
    Otherwise incremental sync uses after_checkpoint. Pagination moves
    backward using the oldest timestamp returned by each page.
    """
    chat_jid = chat.get("jid")
    if not chat_jid:
        raise ValueError("The WhatsApp chat does not contain a JID.")

    fetched_by_key: dict[tuple[str, str, str], dict] = {}

    if start_datetime is not None:
        after = start_datetime.isoformat()
    elif not initial_sync:
        after = after_checkpoint
    else:
        after = None

    before = None
    seen_page_signatures: set[tuple[str, ...]] = set()
    previous_oldest: datetime | None = None

    while True:
        arguments: dict[str, Any] = {
            "chat": chat_jid,
            "limit": BATCH_SIZE,
        }

        if before is not None:
            arguments["before"] = before
        if after is not None:
            arguments["after"] = after

        page = await call_tool(session, "list_messages", arguments)
        messages = page.get("messages", [])

        if not isinstance(messages, list) or not messages:
            break

        page_ids: list[str] = []
        page_timestamps: list[datetime] = []

        for message in messages:
            raw_timestamp = message.get("time") or message.get("timestamp")
            message_datetime = parse_timestamp(raw_timestamp)

            # Enforce the lower boundary locally too.
            if start_datetime is not None:
                if message_datetime is None or message_datetime < start_datetime:
                    continue

            record = normalize_whatsapp_message(
                message=message,
                chat=chat,
                account_id=account_id,
            )
            key = message_key(record)

            if key[2]:
                fetched_by_key[key] = record
                page_ids.append(key[2])
            else:
                # Keep messages without IDs, but do not pretend they have
                # real WhatsApp IDs.
                temporary_key = (
                    key[0],
                    key[1],
                    f"missing_id_{len(fetched_by_key)}",
                )
                fetched_by_key[temporary_key] = record

            if message_datetime is not None:
                page_timestamps.append(message_datetime)

        # Detect an identical page to prevent an infinite pagination loop.
        page_signature = tuple(sorted(page_ids))
        if page_signature and page_signature in seen_page_signatures:
            break
        if page_signature:
            seen_page_signatures.add(page_signature)

        # We need timestamps to calculate the next `before` cursor.
        raw_page_timestamps = [
            parse_timestamp(message.get("time") or message.get("timestamp"))
            for message in messages
        ]
        raw_page_timestamps = [
            stamp for stamp in raw_page_timestamps if stamp is not None
        ]
        if not raw_page_timestamps:
            break

        # If the server explicitly says there are no more pages, stop.
        if not page.get("has_more", False):
            break

        oldest = min(raw_page_timestamps)

        # If the cursor does not move backward, stop instead of looping.
        if previous_oldest is not None and oldest >= previous_oldest:
            break

        previous_oldest = oldest
        before = oldest.isoformat()

    return _sort_records(list(fetched_by_key.values()))


async def whatsapp_loader(
    chat_name: str | None = None,
    start_date: str | None = None,
    initial_sync: bool = False,
    existing_records: list[dict] | None = None,
    account_id: str = ACCOUNT_ID,
) -> list[dict]:
    """
    Load WhatsApp messages from one chat or all chats returned by list_chats.

    Args:
        chat_name: Chat name/search query. None requests all available chats.
        start_date: Inclusive YYYY-MM-DD date in India Standard Time.
        initial_sync: If True, do not use saved checkpoints as lower bounds.
        existing_records: Optional existing normalized records to merge.
        account_id: Identifier for this linked WhatsApp account.

    Returns:
        Deduplicated, timestamp-sorted normalized records.

    Note:
        Only checkpoint metadata is persisted. Message records are not saved
        to this JSON file. They must be stored separately by the caller.
    """
    start_datetime = None

    if start_date is not None:
        try:
            selected_date = date.fromisoformat(start_date)
        except ValueError as exc:
            raise ValueError(
                "start_date must use YYYY-MM-DD format, "
                "for example '2026-10-07'."
            ) from exc

        # Interpret the requested calendar date in India, then convert to UTC.
        start_datetime = datetime.combine(
            selected_date,
            time.min,
            tzinfo=IST,
        ).astimezone(timezone.utc)

    if existing_records is None:
        existing_records = []
    if not isinstance(existing_records, list):
        raise ValueError("existing_records must be a list.")

    checkpoint_data = read_json(CHECKPOINT_FILE, {"chats": {}})
    if not isinstance(checkpoint_data, dict):
        raise ValueError("Checkpoint file must contain a JSON object.")

    chat_checkpoints = checkpoint_data.setdefault("chats", {})
    if not isinstance(chat_checkpoints, dict):
        raise ValueError("The checkpoint file's 'chats' value must be an object.")

    server = StdioServerParameters(
        command="wsl",
        args=["-e", SERVER_PATH, "serve"],
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            chat_arguments: dict[str, Any] = {"limit": CHAT_LIST_LIMIT}
            if chat_name is not None:
                chat_arguments["query"] = chat_name

            chat_result = await call_tool(session, "list_chats", chat_arguments)
            chats = chat_result.get("chats", [])

            if not isinstance(chats, list) or not chats:
                if chat_name is None:
                    raise ValueError(
                        "No WhatsApp chats were returned by list_chats."
                    )
                raise ValueError(f"No chat found for '{chat_name}'.")

            if chat_name is not None and len(chats) > 1:
                matches = [
                    {"name": chat.get("name"), "jid": chat.get("jid")}
                    for chat in chats
                ]
                raise ValueError(
                    f"Multiple chats matched '{chat_name}': {matches}. "
                    "Use a more specific name."
                )

            all_fetched: dict[tuple[str, str, str], dict] = {}

            for index, chat in enumerate(chats, start=1):
                chat_jid = chat.get("jid")
                if not chat_jid:
                    continue

                chat_key = f"{account_id}:{chat_jid}"
                checkpoint = chat_checkpoints.get(chat_key, {})
                if not isinstance(checkpoint, dict):
                    checkpoint = {}

                print(
                    f"[{index}/{len(chats)}] Fetching chat: "
                    f"{chat.get('name') or chat_jid}"
                )

                fetched = await fetch_chat_messages(
                    session=session,
                    chat=chat,
                    account_id=account_id,
                    start_datetime=start_datetime,
                    after_checkpoint=checkpoint.get("last_timestamp"),
                    initial_sync=initial_sync,
                )

                for record in fetched:
                    key = message_key(record)
                    if key[2]:
                        all_fetched[key] = record
                    else:
                        temporary_key = (
                            key[0],
                            key[1],
                            f"missing_id_{len(all_fetched)}",
                        )
                        all_fetched[temporary_key] = record

                timestamps = [
                    parse_timestamp(record.get("timestamp"))
                    for record in fetched
                ]
                timestamps = [stamp for stamp in timestamps if stamp is not None]

                # Only update a checkpoint if we fetched timestamped records.
                if timestamps:
                    newest = max(timestamps)
                    previous = parse_timestamp(checkpoint.get("last_timestamp"))
                    if previous is not None:
                        newest = max(newest, previous)

                    chat_checkpoints[chat_key] = {
                        "chat_jid": chat_jid,
                        "chat_name": chat.get("name") or "",
                        "last_timestamp": newest.isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }

            # Merge existing records and newly fetched messages. New fetched
            # records replace existing copies with the same stable key.
            merged: dict[tuple[str, str, str], dict] = {}

            for record in existing_records:
                key = message_key(record)
                if key[2]:
                    merged[key] = record
                else:
                    temporary_key = (
                        key[0],
                        key[1],
                        f"existing_missing_id_{len(merged)}",
                    )
                    merged[temporary_key] = record

            merged.update(all_fetched)

            # When a date was requested, apply it to existing records too.
            if start_datetime is not None:
                filtered = {}
                for key, record in merged.items():
                    stamp = parse_timestamp(record.get("timestamp"))
                    if stamp is not None and stamp >= start_datetime:
                        filtered[key] = record
                merged = filtered

            final_records = _sort_records(list(merged.values()))

            # Persist checkpoint metadata only.
            atomic_write_json(CHECKPOINT_FILE, checkpoint_data)

            print(f"Chats processed: {len(chats)}")
            print(f"New messages fetched: {len(all_fetched)}")
            print(f"Total records returned: {len(final_records)}")

            return final_records


if __name__ == "__main__":
    result = asyncio.run(
        whatsapp_loader(
                     # None = all chats returned by list_chats
            start_date="2026-10-11", # inclusive date in India time
            initial_sync=True,
        )
    )

    print(f"\nTotal messages returned: {len(result)}")
    for message in result[:10]:
        print(json.dumps(message, indent=2, ensure_ascii=False))
