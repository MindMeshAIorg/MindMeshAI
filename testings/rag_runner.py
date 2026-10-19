
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
for p in (PROJECT_ROOT, BASE_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

VENV_PACKAGES = PROJECT_ROOT / ".mindmeshenv" / "Lib" / "site-packages"
if VENV_PACKAGES.exists() and str(VENV_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_PACKAGES))

import asyncio

from MCP_and_connectors.whatsapp_connector import whatsapp_loader
from RAG.chunking import create_chunks
from RAG.embedding import generate_embeddings
from databases.Vector_Database.insertion_in_vectorDB import store_chunks


MODEL_NAME = "BAAI/bge-m3"
CONTACT_NAME = "Abubakkar"
USER_ID = "user_123"

CHUNK_SIZE = 1
BATCH_SIZE = 8


async def main():
    # 1. Load WhatsApp messages.
    print(f"\n[1/4] Loading messages from {CONTACT_NAME}...")

    messages = await whatsapp_loader(
          start_date="2026-10-11",
       
        initial_sync=True,
    )

    if not messages:
        print("No WhatsApp messages found.")
        return

    chat_name = messages[0].get("subject") or CONTACT_NAME

    print(f"Loaded {len(messages)} messages from {chat_name}.")

    # 2. Create chunks.
    print("\n[2/4] Creating chunks...")
    for c in messages:
        print(c["text"])

    # chunks = create_chunks(
    #     messages=messages,
    #     chat_name=chat_name,
    #     chunk_size=CHUNK_SIZE,
    #     user_id=USER_ID,
    # )

    # if not chunks:
    #     print("No chunks were created.")
    #     return

    # print(f"Created {len(chunks)} chunks.")

    # # 3. Generate dense and sparse embeddings.
    # print("\n[3/4] Generating BGE-M3 embeddings...")

    # embedded_chunks = generate_embeddings(
    #     chunks,
    #     MODEL_NAME,
    #     BATCH_SIZE,
    # )

    # print(f"Generated embeddings for {len(embedded_chunks)} chunks.")

    # # 4. Store chunks in Qdrant.
    # print("\n[4/4] Storing chunks in Qdrant...")

    # store_chunks(embedded_chunks)

    # print("\nWhatsApp RAG ingestion completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
