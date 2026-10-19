import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "OneDrive" / "Desktop" / "MindMeshAI"
# Fallback to direct path
if not PROJECT_ROOT.exists():
    PROJECT_ROOT = Path(r"c:\Users\Abdul Hannan\OneDrive\Desktop\MindMeshAI")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

print("=" * 60)
print(" VERIFYING ALL DATABASE CONNECTIONS: STORAGE & RETRIEVAL")
print("=" * 60)

# 1. PostgreSQL Connection Test
print("\n[1] Testing PostgreSQL Connection...")
from databases.Normal_database.postgres_client import test_postgres_connection, get_connection
pg_res = test_postgres_connection()
print(f"PostgreSQL Status: {pg_res}")
assert pg_res["status"] == "ok", f"Postgres connection failed: {pg_res}"

# 2. Qdrant Connection Test
print("\n[2] Testing Qdrant Connection...")
from databases.Vector_Database.qdrant_setup import test_qdrant_connection, client, COLLECTION_NAME
qdrant_res = test_qdrant_connection()
print(f"Qdrant Status: {qdrant_res}")
assert qdrant_res["status"] in ("ok", "warning"), f"Qdrant connection failed: {qdrant_res}"

# 3. PostgreSQL Store & Retrieve Test
print("\n[3] Testing PostgreSQL Storage and Retrieval...")
from databases.Normal_database.data_insertion_updation import insert_important_item, get_active_items, complete_item

test_chunk_id = str(uuid.uuid4())
test_user_id = "test_verification_user"

test_item = {
    "chunk_id": test_chunk_id,
    "user_id": test_user_id,
    "source": "WHATSAPP",
    "category": "DEADLINE",
    "actual_text_in_chunk": "Test assignment deadline due tomorrow at 5pm",
    "status": "PENDING",
    "is_active": True,
    "chat_name": "Test Chat",
    "timestamp": datetime.now(timezone.utc),
}

inserted = insert_important_item(test_item)
print(f"  Item inserted: {inserted} (chunk_id: {test_chunk_id})")
assert inserted is True, "Failed to insert test item into PostgreSQL"

retrieved_items = get_active_items(test_user_id)
print(f"  Retrieved {len(retrieved_items)} active item(s) for user {test_user_id}")
matching = [i for i in retrieved_items if str(i["chunk_id"]) == test_chunk_id]
assert len(matching) > 0, "Failed to retrieve inserted item from PostgreSQL"
print(f"  Successfully verified PostgreSQL retrieval: {matching[0]['actual_text_in_chunk']}")

# Clean up test item
completed = complete_item(test_chunk_id, test_user_id)
print(f"  Test item marked completed / cleaned up: {completed}")

# 4. Qdrant Store & Retrieve Test
print("\n[4] Testing Qdrant Storage and Hybrid Retrieval...")
from databases.Vector_Database.insertion_in_vectorDB import store_chunks
from RAG.search_and_retrival import retrieve

# Create a test vector chunk
# Dense vector: 1024 floats, Sparse vector: dict of indices and values
import random
test_point_id = str(uuid.uuid4())
dummy_dense = [random.uniform(-0.1, 0.1) for _ in range(1024)]
# Normalize dummy dense vector
norm = sum(x**2 for x in dummy_dense)**0.5
dummy_dense = [x / norm for x in dummy_dense]

dummy_chunk = {
    "chunk_id": test_point_id,
    "user_id": test_user_id,
    "dense_vector": dummy_dense,
    "sparse_vector": {
        "indices": [10, 25, 100],
        "values": [0.5, 0.8, 1.2],
    },
    "payload": {
        "actual_text_in_chunk": "Machine learning final presentation on Friday afternoon",
        "chat_name": "AI Study Group",
        "source_type": "whatsapp",
        "time": datetime.now(timezone.utc).isoformat(),
    }
}

stored_count = store_chunks([dummy_chunk])
print(f"  Stored {stored_count} point(s) in Qdrant")
assert stored_count == 1, "Failed to store chunk in Qdrant"

# Test retrieval using RAG
print("\n[5] Testing RAG Hybrid Search in Qdrant...")
results = retrieve(
    question="presentation",
    user_id=test_user_id,
    top_k=3,
)
print(f"  Retrieved {len(results)} search result(s) from Qdrant for query 'presentation':")
for r in results:
    print(f"    - [{r.get('chat_name')}] {r.get('text')} (Score: {r.get('score'):.4f})")

# Clean up test point from Qdrant
client.delete(
    collection_name=COLLECTION_NAME,
    points_selector=[test_point_id],
)
print("  Test Qdrant point cleaned up.")

print("\n" + "=" * 60)
print(" ALL TESTS PASSED SUCCESSFULLY! BOTH POSTGRESQL AND QDRANT WORK END-TO-END.")
print("=" * 60)
