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

from databases.Normal_database.postgres_client import get_connection
#  cur.execute("""
#                 CREATE TABLE IF NOT EXISTS users (
#                     user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#                     password_hash TEXT NOT NULL,
#                     created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
#                 );
#             """)

def table_creation():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS important_items (
                    -- 1. Unique ID of this important chunk
                    chunk_id UUID PRIMARY KEY,

                    -- 2. Unique user ID created during login
                    user_id TEXT NOT NULL,

                    -- 3. Original data source
                    source TEXT NOT NULL CHECK (
                        source IN ('WHATSAPP', 'EMAIL')
                    ),

                    -- 4. Why this data is important
                    category TEXT NOT NULL CHECK (
                        category IN (
                            'UNSEEN',
                            'WORK',
                            'DEADLINE',
                            'COMMITMENT',
                            'EVENT',
                            'WAITING_FOR'
                        )
                    ),

                    -- 5. Confidence score
                    confidence REAL NOT NULL
                        CHECK (confidence >= 0 AND confidence <= 1),

                    -- 6. Original chunk that caused this item
                    actual_text_in_chunk TEXT NOT NULL,

                    -- 7. Item state
                    status TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (
                            status IN ('PENDING', 'COMPLETED')
                        ),

                    -- 8. Whether notifier should use this item
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,

                    -- 9. WhatsApp chat or group name
                    chat_name TEXT,

                    -- 10. Date and time of the original message
                    chate_date TIMESTAMP,

                    -- 11. When this item was first saved
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    -- 12. When this item was last changed
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    -- 13. When the user completed the task
                    completed_at TIMESTAMP,

                    -- 14. First reminder after one day
                    next_reminder TIMESTAMP
                        DEFAULT (
                            CURRENT_TIMESTAMP + INTERVAL '1 day'
                        ),

                    -- 15. Number of reminders sent
                    reminder_count INTEGER DEFAULT 0
                );
            """)

            # Find all items belonging to a user
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_items_user
                ON important_items(user_id);
            """)

            # Find active items for a user
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_items_active
                ON important_items(user_id, is_active);
            """)

            # Filter items by category
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_items_category
                ON important_items(user_id, category);
            """)

            # Find items that need a reminder
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_items_reminder
                ON important_items(next_reminder)
                WHERE is_active = TRUE;
            """)

        conn.commit()

    print("MindMesh PostgreSQL setup completed successfully.")