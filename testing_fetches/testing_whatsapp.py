
import asyncio
import json
import sys
import traceback
from pathlib import Path

# Add project root to sys.path so imports work regardless of current working directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure virtualenv packages are loaded even if python is invoked directly without venv activation
VENV_PACKAGES = PROJECT_ROOT / ".mindmeshenv" / "Lib" / "site-packages"
if VENV_PACKAGES.exists():
    for p in (VENV_PACKAGES, VENV_PACKAGES / "win32", VENV_PACKAGES / "win32" / "lib"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

from MCP_and_connectors.whatsapp_connector import whatsapp_loader


# ==============================
# Configuration
# ==============================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "whatsapp_output.json"

WHATSAPP_CHAT_NAME = "abubakkar"


# ==============================
# WhatsApp Testing
# ==============================

async def main():
    user_id = sys.argv[1] if len(sys.argv) > 1 else "user_123"
    archive_label = user_id or "configured default archive"
    print(f"\nFetching WhatsApp messages for user: {archive_label}...")

    try:
        messages = await whatsapp_loader(
            chat_name=WHATSAPP_CHAT_NAME,
            initial_sync=False,
            user_id=user_id,
        )

        # Support both list and dictionary return formats.
        if isinstance(messages, dict):
            messages = messages.get("messages", [])

        OUTPUT_FILE.write_text(
            json.dumps(messages, indent=4, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        print(f"Fetched WhatsApp messages: {len(messages)}")
        print(f"Output saved to: {OUTPUT_FILE}")

    except Exception as error:
        print(f"WhatsApp testing failed: {error}")
        traceback.print_exception(error)


if __name__ == "__main__":
    asyncio.run(main())
