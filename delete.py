
import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models

load_dotenv()


def delete_all_qdrant_data():
    client = QdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY"),
    )

    collection_name = "mindmesh_memories"

    try:
        # Verify that the collection exists.
        if not client.collection_exists(collection_name):
            print(f"Collection '{collection_name}' does not exist.")
            return

        # Get the current number of points.
        before = client.count(
            collection_name=collection_name,
            exact=True,
        ).count

        print(f"Points before deletion: {before}")

        if before == 0:
            print("Collection is already empty.")
            return

        # Delete all points and their payloads.
        client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter()
            ),
            wait=True,
        )

        # Verify the deletion.
        after = client.count(
            collection_name=collection_name,
            exact=True,
        ).count

        if after == 0:
            print("All points deleted successfully.")
            print("The collection and vector configuration are preserved.")
        else:
            print(f"Deletion incomplete. Remaining points: {after}")

    except Exception as e:
        print(f"Failed to delete Qdrant data: {e}")

    finally:
        client.close()


if __name__ == "__main__":
    delete_all_qdrant_data()
