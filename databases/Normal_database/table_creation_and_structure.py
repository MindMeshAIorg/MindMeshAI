import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# =====================================================================
# SQL DATABASE TABLE CREATION CODE COMMENTED OUT FOR FILE STORAGE
# =====================================================================
# from databases.Normal_database.postgres_client import get_connection
#
# def _original_table_creation():
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             # 0. Registered Users (User and Password)
#             cur.execute("""
#                 CREATE TABLE IF NOT EXISTS users (
#                     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#                     username TEXT UNIQUE NOT NULL,
#                     "user" TEXT,
#                     password TEXT NOT NULL,
#                     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
#                     updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
#                 );
#             """)
#             cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
#             # 1. Connected accounts
#             cur.execute("""
#                 CREATE TABLE IF NOT EXISTS user_connected_accounts (
#                     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#                     user_id TEXT NOT NULL,
#                     source TEXT NOT NULL CHECK (source IN ('GMAIL', 'TELEGRAM', 'WHATSAPP')),
#                     account_identifier TEXT NOT NULL,
#                     auth_credentials JSONB NOT NULL,
#                     is_active BOOLEAN NOT NULL DEFAULT TRUE,
#                     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
#                     updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
#                     CONSTRAINT uq_user_source_account UNIQUE (user_id, source, account_identifier)
#                 );
#             """)
#             # 2. Sync checkpoints
#             cur.execute("""
#                 CREATE TABLE IF NOT EXISTS user_sync_checkpoints (
#                     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#                     user_id TEXT NOT NULL,
#                     source TEXT NOT NULL CHECK (source IN ('GMAIL', 'TELEGRAM', 'WHATSAPP')),
#                     account_identifier TEXT NOT NULL,
#                     checkpoint_data JSONB NOT NULL,
#                     last_synced_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
#                     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
#                     updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
#                     CONSTRAINT uq_user_checkpoint UNIQUE (user_id, source, account_identifier)
#                 );
#             """)
#             # 3. Important items extracted from communications
#             cur.execute("""
#                 CREATE TABLE IF NOT EXISTS important_items (
#                     chunk_id UUID PRIMARY KEY,
#                     user_id TEXT NOT NULL,
#                     source TEXT NOT NULL,
#                     category TEXT NOT NULL,
#                     actual_text_in_chunk TEXT NOT NULL,
#                     status TEXT NOT NULL DEFAULT 'PENDING',
#                     is_active BOOLEAN NOT NULL DEFAULT TRUE,
#                     chat_name TEXT,
#                     timestamp TIMESTAMP,
#                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#                     updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#                     completed_at TIMESTAMP,
#                     next_reminder TIMESTAMP DEFAULT (CURRENT_TIMESTAMP + INTERVAL '1 day'),
#                     reminder_count INTEGER DEFAULT 0
#                 );
#             """)
#         conn.commit()
# =====================================================================


def table_creation():
    """
    Ensure all JSON storage files exist in the project base directory with proper initial state.
    """
    initial_files = {
        "users.json": [],
        "connected_accounts.json": [],
        "sync_checkpoints.json": [],
        "important_items.json": [],
        "chat_memory.json": {"messages": [], "memories": []},
        "vector_chunks.json": [],
    }

    for filename, default_content in initial_files.items():
        file_path = BASE_DIR / filename
        if not file_path.exists():
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(default_content, f, indent=2, ensure_ascii=False)
            print(f"[Storage Init] Created {filename} in {BASE_DIR}")
        else:
            # Validate JSON readability
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    json.load(f)
            except Exception:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(default_content, f, indent=2, ensure_ascii=False)
                print(f"[Storage Init] Reinitialized corrupted {filename} in {BASE_DIR}")

    print("MindMesh JSON file-based storage setup completed successfully.")