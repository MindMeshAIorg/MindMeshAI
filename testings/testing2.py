
import asyncio
import json
from datetime import date, datetime, time, timezone
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ============================================================
# CONFIGURATION
# ============================================================

SERVER_PATH = (
    "/mnt/c/Users/Abdul Hannan/OneDrive/Desktop/"
    "MindMeshAI/whatsapp-mcp-server/whatsapp-mcp"
)

BATCH_SIZE = 500

CHAT_NAME = "Abrar M"
START_DATE = "2026-10-07"  # YYYY-MM-DD


# ============================================================
# MCP RESPONSE HELPERS
# ============================================================

def extract_tool_data(result) -> dict:
    """Extract a dictionary from an MCP tool response."""

    if result.isError:
        raise RuntimeError(
            f"MCP tool failed: {result.content}"
        )

    if result.structuredContent is not None:
        return result.structuredContent

    for item in result.content:
        if getattr(item, "type", None) != "text":
            continue

        try:
            parsed = json.loads(item.text)
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, dict):
            return parsed

    raise RuntimeError(
        "MCP response did not contain a JSON object."
    )


async def call_tool(
    session: ClientSession,
    name: str,
    arguments: dict,
) -> dict:
    """Call an MCP tool and return its dictionary response."""

    result = await session.call_tool(
        name,
        arguments=arguments,
    )

    return extract_tool_data(result)


# ============================================================
# TIMESTAMP PARSER
# ============================================================

def parse_timestamp(value: Any) -> datetime | None:
    """Parse ISO-8601 or Unix timestamps into UTC."""

    if value is None or value == "":
        return None

    try:
        if isinstance(value, (int, float)):
            seconds = (
                value / 1000
                if value > 10_000_000_000
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
                if numeric > 10_000_000_000
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

    except (
        ValueError,
        TypeError,
        OverflowError,
        OSError,
    ):
        return None


# ============================================================
# MESSAGE PRINTING
# ============================================================

def print_messages(
    messages: list,
    page_name: str,
) -> list[datetime]:
    """Print every field of every returned message."""

    print("\n" + "=" * 80)
    print(f"{page_name}: {len(messages)} messages returned")
    print("=" * 80)

    timestamps = []

    for index, message in enumerate(messages, start=1):
        timestamp = parse_timestamp(
            message.get("time")
            or message.get("timestamp")
        )

        if timestamp is not None:
            timestamps.append(timestamp)

        print(f"\n--- Message {index} ---")
        print("ID:", message.get("id", "missing"))
        print("Timestamp:", (
            timestamp.isoformat()
            if timestamp
            else "INVALID OR MISSING"
        ))
        print("Sender:", message.get("sender", "unknown"))
        print("Chat:", message.get("chat", "unknown"))
        print("Kind:", message.get("kind", "unknown"))
        print("Text:", repr(message.get("text", "")))

        # Print every field supplied by the MCP server.
        print("Full message object:")
        print(
            json.dumps(
                message,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )

    return timestamps


# ============================================================
# DIAGNOSTIC TEST
# ============================================================

async def test_whatsapp_date_filter() -> None:
    """Inspect date filtering, message contents and pagination."""

    selected_date = date.fromisoformat(START_DATE)

    start_datetime = datetime.combine(
        selected_date,
        time.min,
        tzinfo=timezone.utc,
    )

    after_value = start_datetime.isoformat()

    print("=" * 80)
    print("WHATSAPP DATE FILTER DIAGNOSTIC")
    print("=" * 80)
    print("Chat:", CHAT_NAME)
    print("Requested date:", START_DATE)
    print("Cutoff UTC:", after_value)
    print("Batch size:", BATCH_SIZE)

    server = StdioServerParameters(
        command="wsl",
        args=["-e", SERVER_PATH, "serve"],
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ------------------------------------------------
            # 1. Find the chat
            # ------------------------------------------------

            print("\n[1] Searching for chat...")

            chat_result = await call_tool(
                session,
                "list_chats",
                {
                    "query": CHAT_NAME,
                    "limit": 200,
                },
            )

            chats = chat_result.get("chats", [])

            if not chats:
                print("No matching chat found.")
                return

            print("Matching chats:", len(chats))

            for index, chat in enumerate(chats, start=1):
                print(
                    f"{index}. "
                    f"Name={chat.get('name')!r}, "
                    f"JID={chat.get('jid')!r}"
                )

            if len(chats) != 1:
                print(
                    "\nMore than one chat matched. "
                    "Use a more specific CHAT_NAME and retry."
                )
                return

            chat = chats[0]
            chat_jid = chat.get("jid")

            if not chat_jid:
                print("The selected chat has no JID.")
                return

            print("Selected chat:", chat.get("name"))
            print("Selected JID:", chat_jid)

            # ------------------------------------------------
            # 2. First request: messages after the cutoff
            # ------------------------------------------------

            print("\n[2] Requesting messages after cutoff...")

            first_page = await call_tool(
                session,
                "list_messages",
                {
                    "chat": chat_jid,
                    "limit": BATCH_SIZE,
                    "after": after_value,
                },
            )

            messages = first_page.get("messages", [])

            print("Request after:", after_value)
            print("Messages returned:", len(messages))
            print("has_more:", first_page.get("has_more"))

            first_timestamps = print_messages(
                messages,
                "FIRST PAGE",
            )

            if first_timestamps:
                print(
                    "\nOldest first-page message:",
                    min(first_timestamps).isoformat(),
                )
                print(
                    "Newest first-page message:",
                    max(first_timestamps).isoformat(),
                )

                print(
                    "Messages before cutoff:",
                    sum(
                        ts < start_datetime
                        for ts in first_timestamps
                    ),
                )
                print(
                    "Messages on/after cutoff:",
                    sum(
                        ts >= start_datetime
                        for ts in first_timestamps
                    ),
                )

            # ------------------------------------------------
            # 3. Second request: test before-based pagination
            # ------------------------------------------------

            print("\n[3] Testing before-based pagination...")

            if not first_timestamps:
                print(
                    "Cannot test the second page because "
                    "the first page has no valid timestamps."
                )
                return

            oldest = min(first_timestamps)

            second_page = await call_tool(
                session,
                "list_messages",
                {
                    "chat": chat_jid,
                    "limit": BATCH_SIZE,
                    "after": after_value,
                    "before": oldest.isoformat(),
                },
            )

            second_messages = second_page.get("messages", [])

            print("Request after:", after_value)
            print("Request before:", oldest.isoformat())
            print("Second-page messages:", len(second_messages))
            print(
                "Second-page has_more:",
                second_page.get("has_more"),
            )

            second_timestamps = print_messages(
                second_messages,
                "SECOND PAGE",
            )

            if second_timestamps:
                print(
                    "\nSecond-page oldest:",
                    min(second_timestamps).isoformat(),
                )
                print(
                    "Second-page newest:",
                    max(second_timestamps).isoformat(),
                )

            # ------------------------------------------------
            # 4. Summary
            # ------------------------------------------------

            print("\n" + "=" * 80)
            print("DIAGNOSTIC SUMMARY")
            print("=" * 80)
            print("First-page count:", len(messages))
            print("Second-page count:", len(second_messages))
            print(
                "First-page has_more:",
                first_page.get("has_more"),
            )
            print(
                "Second-page has_more:",
                second_page.get("has_more"),
            )
            print(
                "\nThis diagnostic prints all messages returned "
                "by these two requests."
            )
            print(
                "It does not automatically retrieve all history. "
                "Pagination support depends on the MCP server."
            )


if __name__ == "__main__":
    asyncio.run(test_whatsapp_date_filter())