
import json
import uuid
from pathlib import Path



# Configuration
INPUT_FILE = "abubakkar_messages.json"
OUTPUT_FILE = "whatsapp_chunks_embedded.json"

MODEL_NAME = "BAAI/bge-m3"

CHUNK_SIZE = 50
CHUNK_OVERLAP = 15
BATCH_SIZE = 8

# Replace with the actual application user ID.
USER_ID = "user_123"


def create_chunks(messages, chat_name):
    """Create overlapping chunks of complete WhatsApp messages."""
    formatted_messages = []

    for message in messages:
        text = message.get("text", "").strip()

        # Skip messages without text.
        if not text:
            continue

        sender = message.get("sender", "unknown")

        formatted_messages.append({
            "text": f"{sender}: {text}",
            "time": message.get("time"),
          
        })

    chunks = []
    step = CHUNK_SIZE - CHUNK_OVERLAP

    for start in range(0, len(formatted_messages), step):
        chunk_messages = formatted_messages[
            start:start + CHUNK_SIZE
        ]

        if not chunk_messages:
            break

        # Keep each complete message on its own line.
        chunk_text = "\n".join(
            item["text"] for item in chunk_messages
        )

        first_message = chunk_messages[0]


        chunks.append({
            "chunk_id": str(uuid.uuid4()),
            "user_id": USER_ID,
            "payload": {
                "user_id": USER_ID,
                "chunk_index": len(chunks),
                "source_type": "whatsapp",
                "actual_text_in_chunk": chunk_text,
                "chat_name": chat_name,
                "time": first_message["time"],
                
            },
        })

    return chunks


def generate_embeddings(chunks):
    """Generate BGE-M3 dense and sparse vectors for every chunk."""
    if not chunks:
        return chunks

    model = BGEM3FlagModel(
        MODEL_NAME,
        use_fp16=False,
    )

    texts = [
        chunk["payload"]["actual_text_in_chunk"]
        for chunk in chunks
    ]

    results = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        max_length=8192,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )

    for chunk, dense_vector, sparse_weights in zip(
        chunks,
        results["dense_vecs"],
        results["lexical_weights"],
    ):
        chunk["dense_vector"] = dense_vector.tolist()

        chunk["sparse_vector"] = {
            "indices": [
                int(index) for index in sparse_weights.keys()
            ],
            "values": [
                float(weight) for weight in sparse_weights.values()
            ],
        }

    return chunks


def main():
    input_path = Path(INPUT_FILE)

    if not input_path.exists():
        print(f"Input file not found: {input_path.resolve()}")
        return

    data = json.loads(
        input_path.read_text(encoding="utf-8")
    )

    chat = data["chat"]

    messages = sorted(
        data["messages"],
        key=lambda message: message.get("time") or "",
    )

    print(f"Messages loaded: {len(messages)}")

    chunks = create_chunks(
        messages=messages,
        chat_name=chat["name"],
    )

    print(f"Chunks created: {len(chunks)}")
    print("Generating dense and sparse embeddings...")

    chunks = generate_embeddings(chunks)

    output_path = Path(OUTPUT_FILE)

    output_path.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if chunks:
        print(
            "Dense vector dimensions: "
            f"{len(chunks[0]['dense_vector'])}"
        )
    else:
        print("No chunks to embed.")

    print(f"Chunks saved to: {output_path.resolve()}")


if __name__ == "__main__":
    main()

