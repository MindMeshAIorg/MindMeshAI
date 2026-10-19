
import sys
from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
for p in (PROJECT_ROOT, BASE_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

VENV_PACKAGES = PROJECT_ROOT / ".mindmeshenv" / "Lib" / "site-packages"
if VENV_PACKAGES.exists() and str(VENV_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_PACKAGES))

from FlagEmbedding import BGEM3FlagModel
try:
    from testings.chunking_testing import create_chunks
except ImportError:
    from chunking_testing import create_chunks

INPUT_FILE = "abubakkar_messages.json"
OUTPUT_FILE = "whatsapp_chunks_embedded.json"

MODEL_NAME = "BAAI/bge-m3"

CHUNK_SIZE = 50
CHUNK_OVERLAP = 15
BATCH_SIZE = 8

# Replace with the actual application user ID.
USER_ID = "user_123"
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

