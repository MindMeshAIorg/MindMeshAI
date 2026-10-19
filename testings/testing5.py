import json
from pathlib import Path

from qdrant_client import models

from databases.Vector_Database.qdrant_setup import client, COLLECTION_NAME

INPUT_FILE = "whatsapp_chunks_embedded.json"


def store_chunks(chunks):
    points = []

    for chunk in chunks:
        sparse_data = chunk["sparse_vector"]
        payload = chunk["payload"]
      

        # Ensure the user ID is included in the payload.
        payload["user_id"] = chunk["user_id"]

        point = models.PointStruct(
            id=chunk["chunk_id"],
            vector={
                "dense_vec": chunk["dense_vector"],
                "sparse_vec": models.SparseVector(
                    indices=sparse_data["indices"],
                    values=sparse_data["values"],
                ),
            },
            payload=payload,
        )

        points.append(point)

    if not points:
        print("No chunks to upload.")
        return

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points,
        wait=True,
    )

    print(f"Successfully stored {len(points)} chunks in Qdrant.")


def main():
    input_path = Path(INPUT_FILE)

    if not input_path.exists():
        print(f"File not found: {input_path.resolve()}")
        return

    chunks = json.loads(
        input_path.read_text(encoding="utf-8")
    )

    store_chunks(chunks)


if __name__ == "__main__":
    main()