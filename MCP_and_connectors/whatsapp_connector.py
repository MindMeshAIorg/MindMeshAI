
import asyncio
import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from MCP_and_connectors.normalizer import normalize_message

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from databases.Normal_database.sync_store import (
    get_sync_checkpoint,
    save_sync_checkpoint,
)


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
CHECKPOINT_FILE = BASE_DIR / "whatsapp_sync_checkpoint.json"

SERVER_PATH = os.getenv(
    "WHATSAPP_BINARY",
    "/mnt/c/Users/Abdul Hannan/OneDrive/Desktop/"
    "MindMeshAI/whatsapp-mcp-server/whatsapp-mcp",
)

# Must match the data root used by whatsapp_connection.py.
WHATSAPP_DATA_ROOT = os.getenv(
    "WHATSAPP_DATA_ROOT",
    "/home/abdul_hannan/whatsapp-mcp-data",
)
WHATSAPP_DATA_DIR = os.getenv(
    "WHATSAPP_DATA_DIR",
    f"{WHATSAPP_DATA_ROOT.rstrip('/')}/local_test_user",
)

BATCH_SIZE = 500
CHAT_PAGE_SIZE = 200
ACCOUNT_ID = "default"

# Re-fetch a small window before the checkpoint to reduce the risk
# of missing messages that share timestamps. Message IDs deduplicate it.
CHECKPOINT_OVERLAP = timedelta(minutes=2)


# ---------------------------------------------------------
# JSON CHECKPOINT HELPERS
# ---------------------------------------------------------

def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temp_path.replace(path)


def message_key(message: dict) -> tuple[str, str, str]:
    return (
        str(message.get("account_id") or ""),
        str(message.get("conversation_id") or ""),
        str(message.get("message_id") or ""),
    )


# ---------------------------------------------------------
# MCP RESPONSE HELPERS
# ---------------------------------------------------------

def extract_tool_data(result: Any) -> Any:
    if getattr(result, "isError", False):
        errors = [
            item.text
            for item in (getattr(result, "content", None) or [])
            if getattr(item, "text", None)
        ]
        raise RuntimeError(
            "\n".join(errors) or "WhatsApp MCP tool failed."
        )

    structured = getattr(result, "structuredContent", None)

    if structured is not None:
        return structured

    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)

        if not text:
            continue

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue

    raise RuntimeError(
        "MCP response did not contain readable structured data."
    )


async def call_tool(
    session: ClientSession,
    name: str,
    arguments: dict | None = None,
) -> Any:
    result = await session.call_tool(
        name,
        arguments=arguments or {},
    )
    return extract_tool_data(result)


def parse_timestamp(value: Any) -> datetime | None:
    """Parse ISO-8601 or Unix timestamps and return UTC datetimes."""

    if value is None or value == "":
        return None

    try:
        if isinstance(value, (int, float)):
            seconds = (
                value / 1000
                if abs(value) > 10_000_000_000
                else value
            )
            return datetime.fromtimestamp(
                seconds,
                tz=timezone.utc,
            )

        text = str(value).strip()

        try:
            numeric = float(text)
            seconds = (
                numeric / 1000
                if abs(numeric) > 10_000_000_000
                else numeric
            )
            return datetime.fromtimestamp(
                seconds,
                tz=timezone.utc,
            )
        except ValueError:
            pass

        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError, OSError):
        return None


def get_list(
    data: Any,
    *possible_keys: str,
) -> list[dict]:
    """Extract a list from either a direct array or an object."""

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in possible_keys:
            value = data.get(key)

            if isinstance(value, list):
                return [
                    item for item in value
                    if isinstance(item, dict)
                ]

    return []


def get_chat_jid(chat: dict) -> str | None:
    value = (
        chat.get("jid")
        or chat.get("JID")
        or chat.get("chat_jid")
    )
    return str(value) if value else None


def get_chat_name(chat: dict) -> str:
    """Use the best display-name field actually supplied by the server."""

    for field in (
        "name",
        "display_name",
        "push_name",
        "subject",
        "chat_name",
        "formatted_name",
    ):
        value = chat.get(field)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return get_chat_jid(chat) or "Unknown"


def get_message_timestamp(message: dict) -> Any:
    return (
        message.get("time")
        or message.get("timestamp")
        or message.get("created_at")
    )


def get_whatsapp_data_dir(user_id: str | None) -> str:
    if user_id is None:
        return WHATSAPP_DATA_DIR

    if not user_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Invalid user ID.")

    return f"{WHATSAPP_DATA_ROOT.rstrip('/')}/{user_id}"


# ---------------------------------------------------------
# CHAT LOADING AND NAME MATCHING
# ---------------------------------------------------------

async def load_all_chats(session: ClientSession) -> list[dict]:
    """Load chat pages and deduplicate chats by JID."""

    all_chats: list[dict] = []
    offset = 0

    while True:
        data = await call_tool(
            session,
            "list_chats",
            {
                
                "offset": offset,
                "include_archived": True,
            },
        )

        page = get_list(data, "chats")

        if not page:
            break

        all_chats.extend(page)

        if len(page) < CHAT_PAGE_SIZE:
            break

        offset += len(page)

    unique: dict[str, dict] = {}

    for chat in all_chats:
        jid = get_chat_jid(chat)

        if jid:
            unique[jid] = chat

    return list(unique.values())


def select_chats(
    chats: list[dict],
    chat_name: str | None,
) -> list[dict]:
    """Match a requested chat by display name or JID."""

    if not chat_name:
        return chats

    query = chat_name.strip().casefold()

    exact = [
        chat for chat in chats
        if get_chat_name(chat).casefold() == query
        or (get_chat_jid(chat) or "").casefold() == query
    ]

    if len(exact) == 1:
        return exact

    if len(exact) > 1:
        matches = exact
    else:
        matches = [
            chat for chat in chats
            if query in get_chat_name(chat).casefold()
            or query in (get_chat_jid(chat) or "").casefold()
        ]

    if not matches:
        raise ValueError(
            f"No WhatsApp chat found matching {chat_name!r}."
        )

    if len(matches) > 1:
        candidates = [
            f"{get_chat_name(chat)} ({get_chat_jid(chat)})"
            for chat in matches
        ]
        raise ValueError(
            "Chat name is ambiguous. Choose one: "
            + ", ".join(candidates)
        )

    return matches


# ---------------------------------------------------------
# MESSAGE NORMALIZATION
# ---------------------------------------------------------

def normalize_whatsapp_message(
    message: dict,
    chat: dict,
    account_id: str,
) -> dict:
    message_id = (
        message.get("id")
        or message.get("ID")
        or message.get("message_id")
    )

    timestamp = get_message_timestamp(message)

    sender = (
        message.get("sender_name")
        or message.get("push_name")
        or message.get("sender")
        or message.get("sender_jid")
        or "Unknown"
    )

    text = (
        message.get("text")
        or message.get("body")
        or message.get("content")
        or ""
    )

    conversation_id = (
        message.get("chat_jid")
        or message.get("conversation_id")
        or get_chat_jid(chat)
    )

    return normalize_message(
        source="whatsapp",
        message_id=message_id,
        conversation_id=conversation_id,
        sender=sender,
        subject=get_chat_name(chat),
        text=text,
        timestamp=timestamp,
        account_id=account_id,
    )


# ---------------------------------------------------------
# MESSAGE PAGINATION
# ---------------------------------------------------------

async def fetch_chat_messages(
    session: ClientSession,
    chat: dict,
    account_id: str,
    start_datetime: datetime | None,
    after_checkpoint: str | None,
    initial_sync: bool,
) -> list[dict]:
    """
    Fetch messages using the server's list_messages pagination.

    An explicit start date takes priority over the checkpoint.
    Incremental sync re-fetches a small overlap before the checkpoint.
    The overlap is deduplicated using message IDs.
    """

    chat_jid = get_chat_jid(chat)

    if not chat_jid:
        raise ValueError(
            f"WhatsApp chat has no JID: {chat!r}"
        )

    if start_datetime is not None:
        after = start_datetime
    elif not initial_sync and after_checkpoint:
        checkpoint_time = parse_timestamp(after_checkpoint)
        after = (
            checkpoint_time - CHECKPOINT_OVERLAP
            if checkpoint_time
            else None
        )
    else:
        after = None

    after_cursor = after.isoformat() if after else None
    before_cursor: str | None = None

    fetched: dict[tuple[str, str, str], dict] = {}
    seen_page_signatures: set[tuple[str, ...]] = set()
    previous_oldest: datetime | None = None

    while True:
        arguments: dict[str, Any] = {
            "chat": chat_jid,
            "limit": BATCH_SIZE,
            "oldest_first": False,
        }

        if after_cursor:
            arguments["after"] = after_cursor

        if before_cursor:
            arguments["before"] = before_cursor

        page_data = await call_tool(
            session,
            "list_messages",
            arguments,
        )

        messages = get_list(page_data, "messages")

        if not messages:
            break

        timestamped: list[tuple[datetime, dict]] = []

        for message in messages:
            message_time = parse_timestamp(
                get_message_timestamp(message)
            )

            if message_time is not None:
                timestamped.append((message_time, message))

        # If timestamps are absent, a safe older-page cursor cannot
        # be derived from this response.
        if not timestamped:
            for message in messages:
                record = normalize_whatsapp_message(
                    message,
                    chat,
                    account_id,
                )
                key = message_key(record)

                if key[2]:
                    fetched[key] = record

            break

        timestamped.sort(key=lambda item: item[0])

        # Filter locally too, so the start-date boundary is enforced
        # even if the server's "after" filter is inclusive or imprecise.
        for message_time, message in timestamped:
            if start_datetime and message_time < start_datetime:
                continue

            record = normalize_whatsapp_message(
                message,
                chat,
                account_id,
            )

            key = message_key(record)

            if key[2]:
                fetched[key] = record

        oldest_time = timestamped[0][0]

        signature = tuple(
            str(
                message.get("id")
                or message.get("ID")
                or message.get("message_id")
                or get_message_timestamp(message)
            )
            for _, message in timestamped
        )

        if signature in seen_page_signatures:
            print(
                f"Warning: server repeated a page for {chat_jid}; "
                "stopping pagination to avoid an infinite loop."
            )
            break

        seen_page_signatures.add(signature)

        has_more = (
            page_data.get("has_more")
            if isinstance(page_data, dict)
            else None
        )

        # Stop after reaching the requested date boundary.
        if start_datetime and oldest_time <= start_datetime:
            break

        if (
            previous_oldest is not None
            and oldest_time >= previous_oldest
        ):
            print(
                f"Warning: pagination cursor did not move backward "
                f"for {chat_jid}; stopping."
            )
            break

        previous_oldest = oldest_time

        # If the server explicitly says there are no older messages,
        # honor that. If has_more is absent, a full page is the fallback.
        if has_more is False:
            break

        if has_more is None and len(messages) < BATCH_SIZE:
            break

        if len(messages) < BATCH_SIZE and has_more is not True:
            break

        # The server's "before" cursor is assumed to accept timestamps.
        # If the server uses another cursor format, this must be adapted
        # to its actual tool schema.
        before_cursor = oldest_time.isoformat()

    return sorted(
        fetched.values(),
        key=lambda record: (
            parse_timestamp(record.get("timestamp"))
            or datetime.min.replace(tzinfo=timezone.utc),
            record.get("conversation_id") or "",
            record.get("message_id") or "",
        ),
    )


# ---------------------------------------------------------
# MAIN LOADER
# ---------------------------------------------------------

async def whatsapp_loader(
    chat_name: str | None = None,
    start_date: str | None = None,
    initial_sync: bool = True,
    existing_records: list[dict] | None = None,
    account_id: str = ACCOUNT_ID,
    user_id: str | None = None,
) -> list[dict]:
    """
    Load and normalize WhatsApp messages.

    start_date:
        Inclusive UTC date in YYYY-MM-DD format.

    initial_sync:
        True ignores the incremental checkpoint unless start_date
        explicitly sets a lower boundary.

    existing_records:
        Previously loaded normalized records to merge with this fetch.
    """

    start_datetime = None

    if start_date is not None:
        try:
            selected_date = date.fromisoformat(start_date)
        except ValueError as exc:
            raise ValueError(
                "start_date must use YYYY-MM-DD format, "
                "for example '2026-10-11'."
            ) from exc

        start_datetime = datetime.combine(
            selected_date,
            time.min,
            tzinfo=timezone.utc,
        )

    if existing_records is None:
        existing_records = []

    if not isinstance(existing_records, list):
        raise ValueError("existing_records must be a list.")

    checkpoint_data = None
    if user_id:
        db_cp = get_sync_checkpoint(user_id, "WHATSAPP", account_id)
        if db_cp and "checkpoint_data" in db_cp:
            checkpoint_data = db_cp["checkpoint_data"]

    if checkpoint_data is None:
        # Local file checkpoint fallback (commented out in favor of database)
        # checkpoint_data = read_json(
        #     CHECKPOINT_FILE,
        #     {"chats": {}},
        # )
        checkpoint_data = {"chats": {}}

    if not isinstance(checkpoint_data, dict):
        raise ValueError(
            "Checkpoint file must contain a JSON object."
        )

    chat_checkpoints = checkpoint_data.setdefault("chats", {})

    if not isinstance(chat_checkpoints, dict):
        raise ValueError(
            "The checkpoint file's 'chats' value must be an object."
        )

    data_dir = get_whatsapp_data_dir(user_id)

    server = StdioServerParameters(
        command="wsl",
        args=[
            "-e",
            SERVER_PATH,
            "serve",
            "--data-dir",
            data_dir,
        ],
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Verify which archive this server is using, if the tool
            # is available in this version of the WhatsApp MCP server.
            try:
                status = await call_tool(
                    session,
                    "whatsapp_status",
                )
                print("WhatsApp archive status:", status)
            except Exception as exc:
                print(
                    "Warning: could not read WhatsApp status:",
                    str(exc),
                )

            chats = await load_all_chats(session)
            selected_chats = select_chats(chats, chat_name)

            print(f"Chats selected: {len(selected_chats)}")

            all_fetched: dict[
                tuple[str, str, str],
                dict,
            ] = {}

            for index, chat in enumerate(
                selected_chats,
                start=1,
            ):
                chat_jid = get_chat_jid(chat)
                display_name = get_chat_name(chat)

                print(
                    f"[{index}/{len(selected_chats)}] "
                    f"{display_name} ({chat_jid})"
                )

                chat_key = f"{account_id}:{chat_jid}"
                checkpoint = chat_checkpoints.get(chat_key, {})

                if not isinstance(checkpoint, dict):
                    checkpoint = {}

                fetched = await fetch_chat_messages(
                    session=session,
                    chat=chat,
                    account_id=account_id,
                    start_datetime=start_datetime,
                    after_checkpoint=checkpoint.get(
                        "last_timestamp"
                    ),
                    initial_sync=initial_sync,
                )

                print(f"    Retrieved {len(fetched)} messages")

                for record in fetched:
                    key = message_key(record)

                    if key[2]:
                        all_fetched[key] = record
                    else:
                        # Avoid claiming that a missing ID is a genuine ID.
                        temp_key = (
                            key[0],
                            key[1],
                            f"missing_id_{len(all_fetched)}",
                        )
                        all_fetched[temp_key] = record

                timestamps = [
                    parse_timestamp(record.get("timestamp"))
                    for record in fetched
                ]
                valid_timestamps = [
                    value for value in timestamps
                    if value is not None
                ]

                # Update checkpoint only if messages with valid
                # timestamps were actually fetched.
                if valid_timestamps:
                    newest = max(valid_timestamps)
                    previous = parse_timestamp(
                        checkpoint.get("last_timestamp")
                    )

                    if previous:
                        newest = max(newest, previous)

                    chat_checkpoints[chat_key] = {
                        "chat_jid": chat_jid,
                        "chat_name": display_name,
                        "last_timestamp": newest.isoformat(),
                        "updated_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                    }

            # Merge previously supplied records with newly fetched ones.
            merged: dict[
                tuple[str, str, str],
                dict,
            ] = {}

            for index, record in enumerate(existing_records):
                key = message_key(record)

                if key[2]:
                    merged[key] = record
                else:
                    temp_key = (
                        key[0],
                        key[1],
                        f"existing_missing_id_{index}",
                    )
                    merged[temp_key] = record

            # Newly fetched records take precedence for duplicate IDs.
            merged.update(all_fetched)

            final_records = sorted(
                merged.values(),
                key=lambda record: (
                    parse_timestamp(record.get("timestamp"))
                    or datetime.min.replace(tzinfo=timezone.utc),
                    record.get("conversation_id") or "",
                    record.get("message_id") or "",
                ),
            )

            if user_id:
                try:
                    save_sync_checkpoint(
                        user_id,
                        "WHATSAPP",
                        account_id,
                        checkpoint_data,
                    )
                except Exception as err:
                    print(f"Warning: Failed to save WhatsApp checkpoint to database: {err}")

            # Local file checkpoint saving (commented out in favor of database)
            # atomic_write_json(
            #     CHECKPOINT_FILE,
            #     checkpoint_data,
            # )

            return final_records
def save_whatsapp_json(
    messages: list[dict[str, Any]],
    filename: str = "new_whatsapp.json",
) -> None:
    """Save extracted WhatsApp messages in BASE_DIR, creating it if needed."""

    BASE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = BASE_DIR / filename

    output_path.write_text(
        json.dumps(
            messages,
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    print(f"Saved {len(messages)} messages to: {output_path}")


# ---------------------------------------------------------
# EXAMPLE RUN
# # ---------------------------------------------------------

# async def main() -> None:
#     result = await whatsapp_loader(
#         start_date="2026-10-11",

#         chat_name="abubakkar",
#         initial_sync=True,
#     )

#     print(f"\nTotal messages returned: {len(result)}")
#     save_whatsapp_json(result)

#     for message in result[:10]:
#         print(
#             json.dumps(
#                 message,
#                 indent=2,
#                 ensure_ascii=False,
#             )
#         )


# if __name__ == "__main__":
#     asyncio.run(main())
