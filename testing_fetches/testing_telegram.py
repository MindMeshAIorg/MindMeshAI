
import asyncio
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

from MCP_and_connectors.telegram_connector import fetch_telegram_messages


# ==============================
# Configuration
# ==============================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "telegram_output.json"

TELEGRAM_LIMIT_PER_CHAT = 8


# ==============================
# Telegram Testing
# ==============================

async def main():
    user_id = sys.argv[1] if len(sys.argv) > 1 else "user_123"
    print(f"\nFetching Telegram messages for user: {user_id}...")

    try:
        messages = await fetch_telegram_messages(
            limit_per_chat=TELEGRAM_LIMIT_PER_CHAT,
            initial_sync=False,
            user_id=user_id,
        )

        OUTPUT_FILE.write_text(
            json.dumps(messages, indent=4, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        print(f"Fetched Telegram messages: {len(messages)}")
        print(f"Output saved to: {OUTPUT_FILE}")

    except Exception as error:
        print(f"Telegram testing failed: {error}")


if __name__ == "__main__":
    asyncio.run(main())
