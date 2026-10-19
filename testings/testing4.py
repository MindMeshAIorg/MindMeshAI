import json
from pathlib import Path

from FlagEmbedding import BGEM3FlagModel

INPUT_FILE = "whatsapp_chunks.json"
OUTPUT_FILE = "whatsapp_chunks_embedded.json"

MODEL_NAME = "BAAI/bge-m3"


def generate_embeddings(chunks):
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

        # Store sparse vectors in a JSON-friendly format.
        chunk["sparse_vector"] = {
            "indices": [
                int(index) for index in sparse_weights.keys()
            ],
            "values": [
                float(weight) for weight in sparse_weights.values()
            ],
        }

        # Ensure the user ID is present in the payload.
        chunk["payload"]["user_id"] = chunk["user_id"]

    return chunks


def main():
    chunks = json.loads(
        Path(INPUT_FILE).read_text(encoding="utf-8")
    )

    if not chunks:
        print("No chunks found. Run chunking.py first.")
        return

    chunks = generate_embeddings(chunks)

    Path(OUTPUT_FILE).write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Chunks embedded: {len(chunks)}")
    print(
        "Dense dimensions:",
        len(chunks[0]["dense_vector"]),
    )
    print(
        "Sparse terms:",
        len(chunks[0]["sparse_vector"]["indices"]),
    )
    print(f"Saved to: {Path(OUTPUT_FILE).resolve()}")


if __name__ == "__main__":
    main()