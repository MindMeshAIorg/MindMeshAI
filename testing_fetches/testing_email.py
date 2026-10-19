import json
import sys
from pathlib import Path

# Add project root to sys.path so imports work regardless of current working directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure virtualenv packages are loaded even if python is invoked directly without venv activation
VENV_PACKAGES = PROJECT_ROOT / ".mindmeshenv" / "Lib" / "site-packages"
if VENV_PACKAGES.exists() and str(VENV_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_PACKAGES))

from MCP_and_connectors.gmail_connector import fetch_gmail
from databases.Normal_database.sync_store import get_sync_checkpoint, list_connected_accounts

# ==============================
# Configuration
# ==============================
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "gmail_output.json"


def main():
    # User ID can be passed via command line argument: python testing_email.py user_123
    user_id = sys.argv[1] if len(sys.argv) > 1 else "user_123"
    print(f"\n==========================================")
    print(f"Testing Gmail Fetch for user: {user_id}")
    print(f"==========================================")

    # Verify connected account in PostgreSQL
    accounts = list_connected_accounts(user_id=user_id, source="GMAIL")
    if not accounts or not any(acc.get("is_active") for acc in accounts):
        print(f"Warning: No active GMAIL account found in database for '{user_id}'.")
        print("Please connect your Gmail account first at http://localhost:8000\n")

    try:
        # Check database for existing checkpoint
        db_checkpoint = get_sync_checkpoint(user_id=user_id, source="GMAIL")

        if db_checkpoint and db_checkpoint.get("checkpoint_data", {}).get("history_id"):
            print("Found existing checkpoint in PostgreSQL database. Running incremental sync...")
            days = 1
        else:
            print("No previous checkpoint found in database.")
            try:
                days_input = input("Initial Gmail import: last how many days? (default: 2): ").strip()
                days = int(days_input) if days_input else 2
            except (EOFError, KeyboardInterrupt):
                days = 2
            if days < 1:
                days = 2

        messages = fetch_gmail(days=days, user_id=user_id)

        OUTPUT_FILE.write_text(
            json.dumps(messages, indent=4, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        print(f"\nSuccessfully fetched {len(messages)} Gmail messages.")
        print(f"Output saved to: {OUTPUT_FILE}")

    except Exception as error:
        print(f"Gmail testing failed: {error}")


if __name__ == "__main__":
    main()
