import json
import re
import uuid
from pathlib import Path

CHUNK_SIZE = 50
CHUNK_OVERLAP = 5

INPUT_FILE = "abubakkar_messages.json"
OUTPUT_FILE = "whatsapp_chunks.json"

# Replace this with the actual user ID from your database.
USER_ID = "user_123"


def create_chunks(messages, chat_name, user_id):
    chunks = []
    prepared_messages = []

    # Prepare each message with its sender prefix.
    for message in messages:
        text = message.get("text", "").strip()

        # Skip messages without text for this first RAG test.
        if not text:
            continue

        sender = message.get("sender", "unknown")
        message_text = f"{sender}: {text}"

        prepared_messages.append({
            "text": message_text,
            "time": message.get("time"),
            "sender": sender,
        })

    # Split messages into words while keeping their source metadata.
    words = []

    for message in prepared_messages:
        message_words = re.findall(r"\S+", message["text"])

        for word in message_words:
            words.append({
                "word": word,
                "time": message["time"],
                "sender": message["sender"],
            })

    start = 0
    chunk_index = 0
    step = CHUNK_SIZE - CHUNK_OVERLAP

    while start < len(words):
        chunk_words = words[start:start + CHUNK_SIZE]

        if not chunk_words:
            break

        # Metadata comes from the message containing the first word.
        first_message = chunk_words[0]

        chunk_text = " ".join(
            item["word"] for item in chunk_words
        )

        chunks.append({
            "chunk_id": str(uuid.uuid4()),
            "user_id": user_id,
            "vector": None,  # Added later by the embedding module.
            "payload": {
                "user_id": user_id,
                "chunk_index": chunk_index,
                "source_type": "whatsapp",
                "actual_text_in_chunk": chunk_text,
                "chat_name": chat_name,
                "time": first_message["time"],
            },
        })

        chunk_index += 1
        start += step

    return chunks


# def main():
#     data = json.loads(
#         Path(INPUT_FILE).read_text(encoding="utf-8")
#     )

#     chat = data["chat"]

#     messages = sorted(
#         data["messages"],
#         key=lambda message: message.get("time", ""),
#     )

#     chunks = create_chunks(
#         messages=messages,
#         chat_name=chat["name"],
#         user_id=USER_ID,
#     )

#     Path(OUTPUT_FILE).write_text(
#         json.dumps(chunks, ensure_ascii=False, indent=2),
#         encoding="utf-8",
#     )

#     print(f"Messages in JSON: {len(messages)}")
#     print(f"Chunks created: {len(chunks)}")
#     print(f"Saved to: {Path(OUTPUT_FILE).resolve()}")

#     # Display the first three chunks for testing.
#     for chunk in chunks[:3]:
#         payload = chunk["payload"]

#         print(f"\nChunk {payload['chunk_index']}")
#         print(f"First message time: {payload['time']}")
#         print(
#             "Word count:",
#             len(payload["actual_text_in_chunk"].split()),
#         )
#         print(payload["actual_text_in_chunk"])


# if __name__ == "__main__":
#     main()