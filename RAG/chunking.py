
import uuid
from collections import defaultdict


def create_chunks(
    messages,
    whatsapp_chunk_size=20,
    gmail_chunk_size=1,
    telegram_chunk_size=20,
    user_id: str = None,
):
    if not user_id:
        raise ValueError("user_id is strictly required for chunking to ensure multi-user isolation.")
    chunk_sizes = {
        "whatsapp": whatsapp_chunk_size,
        "gmail": gmail_chunk_size,
        "telegram": telegram_chunk_size,
    }

    print("\n========== CHUNKING DIAGNOSTICS ==========")
    print(f"Total input messages: {len(messages)}")
    print(f"Supported sources: {list(chunk_sizes.keys())}")

    # Group messages by source and conversation.
    grouped_messages = defaultdict(list)

    # Diagnostic counters.
    skipped_empty_text = 0
    skipped_unknown_source = 0
    accepted_messages = 0

    for index, message in enumerate(messages):
        text = (message.get("text") or "").strip()
        source = (message.get("source") or "").lower()

        # Print details for each incoming message.
        print(f"\nMessage {index + 1}:")
        print(f"  Source: {source!r}")
        print(f"  Text length: {len(text)}")
        print(f"  Conversation ID: {message.get('conversation_id')!r}")
        print(f"  Account ID: {message.get('account_id')!r}")

        # Skip messages without text.
        if not text:
            skipped_empty_text += 1
            print("  SKIPPED: message text is empty.")
            continue

        # Skip unsupported sources.
        if source not in chunk_sizes:
            skipped_unknown_source += 1
            print(f"  SKIPPED: unsupported source {source!r}.")
            continue

        conversation_id = message.get("conversation_id") or "unknown"
        account_id = message.get("account_id") or "default"

        grouped_messages[
            (source, conversation_id, account_id)
        ].append(message)

        accepted_messages += 1
        print("  ACCEPTED: message added to a group.")

    print("\n========== GROUPING SUMMARY ==========")
    print(f"Accepted messages: {accepted_messages}")
    print(f"Skipped empty text: {skipped_empty_text}")
    print(f"Skipped unsupported source: {skipped_unknown_source}")
    print(f"Number of groups: {len(grouped_messages)}")

    for group_key, group_messages in grouped_messages.items():
        print(f"  Group {group_key}: {len(group_messages)} messages")

    chunks = []

    for (source, conversation_id, account_id), source_messages in (
        grouped_messages.items()
    ):
        chunk_size = chunk_sizes[source]

        if chunk_size <= 0:
            raise ValueError(
                f"Chunk size for {source!r} must be greater than zero."
            )

        # Keep messages in chronological order.
        source_messages.sort(
            key=lambda message: message.get("timestamp") or ""
        )

        for start in range(0, len(source_messages), chunk_size):
            chunk_messages = source_messages[
                start:start + chunk_size
            ]

            chunk_text = "\n".join(
                f"{message.get('sender') or 'unknown'}: "
                f"{(message.get('text') or '').strip()}"
                for message in chunk_messages
            )

            first_message = chunk_messages[0]
            last_message = chunk_messages[-1]

            chunk = {
                "chunk_id": str(uuid.uuid4()),
                "user_id": user_id,
                "payload": {
                    "user_id": user_id,
                    "account_id": account_id,
                    "chunk_index": len(chunks),
                    "source_type": source,
                    "conversation_id": conversation_id,
                    "subject": first_message.get("subject"),
                    "message_ids": [
                        message.get("message_id")
                        for message in chunk_messages
                    ],
                    "start_timestamp": first_message.get("timestamp"),
                    "end_timestamp": last_message.get("timestamp"),
                    "actual_text_in_chunk": chunk_text,
                },
            }

            chunks.append(chunk)

            print(
                f"\nCREATED CHUNK {len(chunks)}: "
                f"source={source!r}, "
                f"messages={len(chunk_messages)}, "
                f"text_length={len(chunk_text)}"
            )

    print("\n========== FINAL CHUNKING SUMMARY ==========")
    print(f"Input messages: {len(messages)}")
    print(f"Accepted messages: {accepted_messages}")
    print(f"Total chunks created: {len(chunks)}")

    if not chunks:
        print(
            "WARNING: No chunks created. "
            "Check the skipped-message diagnostics above."
        )

    return chunks
