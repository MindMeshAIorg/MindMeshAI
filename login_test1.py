
import sys
from pathlib import Path

# Add project root and virtualenv site-packages to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

VENV_PACKAGES = PROJECT_ROOT / ".mindmeshenv" / "Lib" / "site-packages"
if VENV_PACKAGES.exists() and str(VENV_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_PACKAGES))

import asyncio
from MCP_and_connectors.whatsapp_connection import (
    start_whatsapp_login,
    get_whatsapp_qr,
    monitor_login,
)

async def main():
    user_id = "local_test_user"

    result = await start_whatsapp_login(user_id)
    print("Login status:", result)

    # Wait for the QR code to become available.
    for _ in range(30):
        await asyncio.sleep(1)
        qr = await get_whatsapp_qr(user_id)

        if qr["status"] == "scan_qr":
            print("QR code is ready.")
            with open("whatsapp_qr.png", "wb") as f:
                import base64
                encoded = qr["qr_data_url"].split(",", 1)[1]
                f.write(base64.b64decode(encoded))

            print("Open whatsapp_qr.png and scan it.")
            break

        if qr["status"] == "login_process_finished":
            print("Login process ended:", qr)
            return
    else:
        print("QR code did not appear. Check the terminal logs.")
        return

    await monitor_login(user_id)

asyncio.run(main())
