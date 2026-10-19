import asyncio
import base64
import os
import shlex
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Set WHATSAPP_RUNTIME to "wsl" for local Windows + WSL,
# or "native" when running the executable directly in Linux/Render.
WHATSAPP_RUNTIME = os.getenv("WHATSAPP_RUNTIME", "wsl").lower()

WHATSAPP_BINARY = os.getenv(
    "WHATSAPP_BINARY",
    "/mnt/c/Users/Abdul Hannan/OneDrive/Desktop/MindMeshAI/whatsapp-mcp-server/whatsapp-mcp",
)

WHATSAPP_DATA_ROOT = os.getenv(
    "WHATSAPP_DATA_ROOT",
    "/home/abdul_hannan/whatsapp-mcp-data",
)


@dataclass
class WhatsAppSession:
    login_process: Optional[subprocess.Popen] = None
    serve_process: Optional[subprocess.Popen] = None
    lock: Optional[asyncio.Lock] = None
    qr_data_url: Optional[str] = None
    is_linked: bool = False
    account_identifier: Optional[str] = None
    error: Optional[str] = None


_sessions: dict[str, WhatsAppSession] = {}


def get_session(user_id: str) -> WhatsAppSession:
    if user_id not in _sessions:
        _sessions[user_id] = WhatsAppSession(
            lock=asyncio.Lock()
        )
    return _sessions[user_id]


def validate_user_id(user_id: str) -> None:
    if not user_id or not user_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Invalid user ID.")


def get_user_data_dir(user_id: str) -> str:
    validate_user_id(user_id)
    return f"{WHATSAPP_DATA_ROOT.rstrip('/')}/{user_id}"


def ensure_whatsapp_serve(user_id: str) -> None:
    session = get_session(user_id)

    if session.login_process and session.login_process.poll() is None:
        return

    if session.serve_process and session.serve_process.poll() is None:
        return

    session.serve_process = subprocess.Popen(
        build_command(
            "serve",
            "--data-dir",
            get_user_data_dir(user_id),
        ),
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def stop_whatsapp_process(process: Optional[subprocess.Popen]) -> None:
    if process is None or process.poll() is not None:
        return

    graceful_stop = process.stdin is not None
    if graceful_stop and not process.stdin.closed:
        try:
            process.stdin.close()
        except OSError:
            graceful_stop = False

    if not graceful_stop:
        process.terminate()

    try:
        await asyncio.to_thread(process.wait, timeout=5)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            await asyncio.to_thread(process.wait, timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            await asyncio.to_thread(process.wait)


def build_command(*args: str) -> list[str]:
    if WHATSAPP_RUNTIME == "wsl":
        if shutil.which("wsl") is None:
            raise RuntimeError("WSL was not found. Install or enable WSL first.")

        command = " ".join(
            shlex.quote(part)
            for part in (WHATSAPP_BINARY, *args)
        )
        return ["wsl", "-e", "bash", "-lc", command]

    if WHATSAPP_RUNTIME == "native":
        return [WHATSAPP_BINARY, *args]

    raise ValueError("WHATSAPP_RUNTIME must be 'wsl' or 'native'.")


def _get_wsl_distro() -> Optional[str]:
    try:
        res = subprocess.run(["wsl", "-l", "-q"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            lines = [l.strip().replace("\x00", "") for l in res.stdout.splitlines() if l.strip().replace("\x00", "")]
            if lines:
                return lines[0]
    except Exception:
        pass
    return None


def _fetch_qr_base64(qr_path: str) -> Optional[str]:
    # 1. Native Windows UNC path read across possible WSL distributions
    if WHATSAPP_RUNTIME == "wsl":
        distros = ["Ubuntu", "Ubuntu-22.04", "Ubuntu-24.04", "Ubuntu-20.04"]
        detected = _get_wsl_distro()
        if detected and detected not in distros:
            distros.insert(0, detected)

        qr_win = qr_path.replace("/", "\\")
        for d in distros:
            for prefix in [rf"\\wsl.localhost\{d}", rf"\\wsl$\{d}"]:
                try:
                    unc_path = Path(f"{prefix}{qr_win}")
                    if unc_path.exists():
                        data = unc_path.read_bytes()
                        if data and len(data) > 100:
                            return base64.b64encode(data).decode("ascii")
                except Exception:
                    pass

    # 2. Native Linux read if running natively
    p = Path(qr_path)
    if p.exists():
        try:
            data = p.read_bytes()
            if data and len(data) > 100:
                return base64.b64encode(data).decode("ascii")
        except Exception:
            pass

    # 3. Fallback to WSL command
    if WHATSAPP_RUNTIME == "wsl":
        cmd = [
            "wsl",
            "-e",
            "bash",
            "-lc",
            f"if [ -s {shlex.quote(qr_path)} ]; then base64 -w 0 {shlex.quote(qr_path)}; fi",
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=5)
            out = res.stdout.strip()
            if out and len(out) > 100:
                return out
        except Exception:
            pass

    return None


async def start_whatsapp_login(user_id: str) -> dict:
    session = get_session(user_id)

    async with session.lock:
        # Terminate any previous login or serve process
        for proc in (session.login_process, session.serve_process):
            await stop_whatsapp_process(proc)
        session.login_process = None
        session.serve_process = None
        session.qr_data_url = None
        session.is_linked = False
        session.error = None

        data_dir = get_user_data_dir(user_id)

        # In WSL, ensure data directory exists and clean stale locks/processes
        if WHATSAPP_RUNTIME == "wsl":
            try:
                cleanup_cmd = (
                    f"mkdir -p {shlex.quote(data_dir)} && "
                    f"pkill -f 'whatsapp-mcp.*{shlex.quote(data_dir)}' || true; "
                    f"rm -f {shlex.quote(data_dir)}/connection.lock {shlex.quote(data_dir)}/login-qr.png"
                )
                await asyncio.to_thread(
                    subprocess.run,
                    ["wsl", "-e", "bash", "-lc", cleanup_cmd],
                    capture_output=True,
                    timeout=5,
                )
            except Exception as e:
                print(f"[WhatsApp prep warning] {e}")

        # 15s allows the initial history sync to download messages from the phone,
        # while our real-time stdout listener marks the user 'connected' in <1s!
        command = build_command(
            "login",
            "--data-dir",
            data_dir,
            "--sync-idle",
            "15s",
        )

        session.login_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )

        # Start drainer thread for real-time link detection and error capture
        def _drain_stream(stream, name):
            try:
                for line in iter(stream.readline, b""):
                    msg = line.decode("utf-8", errors="replace").rstrip()
                    print(f"[WhatsApp {name}] {msg}")

                    lower = msg.lower()
                    if any(x in lower for x in ["already linked as", "linked as", "logged in as", "successfully authenticated", "paired with"]):
                        import re
                        identifier = user_id
                        m = re.search(r'([0-9]+)@s\.whatsapp\.net', msg)
                        if m:
                            identifier = "+" + m.group(1)
                        print(f"[WhatsApp] Device linked detected: {msg} (identifier: {identifier})")
                        session.is_linked = True
                        session.qr_data_url = None
                        session.account_identifier = identifier
                        try:
                            from databases.Normal_database.sync_store import upsert_connected_account
                            upsert_connected_account(
                                user_id=user_id,
                                source="WHATSAPP",
                                account_identifier=identifier,
                                auth_credentials={"data_dir": data_dir, "status": "connected"},
                                is_active=True,
                            )
                            print(f"[WhatsApp] Saved connected account to DB for user {user_id}")
                        except Exception as e:
                            print(f"Failed to upsert connected account: {e}")

                    # Capture error messages if process reports fatal error
                    if any(err_kw in lower for err_kw in ["another whatsapp-mcp process is connected", "panic:", "cannot connect", "pairing failed"]):
                        session.error = msg
            except Exception:
                pass
            finally:
                stream.close()

        threading.Thread(target=_drain_stream, args=(session.login_process.stdout, "stdout"), daemon=True).start()
        threading.Thread(target=_drain_stream, args=(session.login_process.stderr, "stderr"), daemon=True).start()

        # Start background polling for QR code
        asyncio.create_task(_capture_login_output(user_id))

        # Start background task to monitor completion
        asyncio.create_task(monitor_login(user_id))

        return {"status": "login_started"}


async def _capture_login_output(user_id: str) -> None:
    session = get_session(user_id)
    process = session.login_process

    if process is None:
        return

    data_dir = get_user_data_dir(user_id)
    qr_path = f"{data_dir}/login-qr.png"

    # Fast poll every 0.5s for instant QR appearance
    for _ in range(120):
        if session.is_linked:
            break

        # If process exited and not linked, perform one last check
        if process.poll() is not None:
            encoded = await asyncio.to_thread(_fetch_qr_base64, qr_path)
            if encoded:
                session.qr_data_url = f"data:image/png;base64,{encoded}"
            break

        try:
            encoded = await asyncio.to_thread(_fetch_qr_base64, qr_path)
            if encoded:
                session.qr_data_url = f"data:image/png;base64,{encoded}"
                break
        except Exception as exc:
            print(f"[WhatsApp QR polling] {exc}")

        await asyncio.sleep(0.5)


async def get_whatsapp_qr(user_id: str) -> dict:
    session = get_session(user_id)
    process = session.login_process

    # 1. If detected as linked in memory
    if session.is_linked:
        ensure_whatsapp_serve(user_id)
        return {
            "status": "connected",
            "account_identifier": getattr(session, "account_identifier", user_id),
        }

    # 2. Check PostgreSQL in case of server reload
    try:
        from databases.Normal_database.sync_store import get_connected_account
        acc = get_connected_account(user_id, "WHATSAPP")
        if acc and acc.get("is_active"):
            session.is_linked = True
            session.qr_data_url = None
            session.account_identifier = acc.get("account_identifier") or user_id
            ensure_whatsapp_serve(user_id)
            return {
                "status": "connected",
                "account_identifier": session.account_identifier,
            }
    except Exception:
        pass

    if process is None:
        return {"status": "not_started"}

    return_code = process.poll()
    if return_code is not None:
        if session.is_linked:
            ensure_whatsapp_serve(user_id)
            return {
                "status": "connected",
                "account_identifier": getattr(session, "account_identifier", user_id),
            }
        if return_code != 0:
            error_msg = session.error or f"WhatsApp login process exited with code {return_code}."
            return {
                "status": "error",
                "message": error_msg,
                "return_code": return_code,
            }
        return {
            "status": "login_process_finished",
            "return_code": return_code,
        }

    if session.qr_data_url and not session.is_linked:
        return {
            "status": "scan_qr",
            "qr_data_url": session.qr_data_url,
        }

    return {"status": "waiting_for_qr"}


async def monitor_login(user_id: str) -> None:
    session = get_session(user_id)
    process = session.login_process

    if process is None:
        return

    return_code = await asyncio.to_thread(process.wait)

    if return_code != 0 and not session.is_linked:
        print(f"WhatsApp login failed for user {user_id}; exit code: {return_code}")
        return

    session.is_linked = True
    session.qr_data_url = None
    data_dir = get_user_data_dir(user_id)
    identifier = getattr(session, "account_identifier", user_id)

    # Save to PostgreSQL user_connected_accounts
    try:
        from databases.Normal_database.sync_store import upsert_connected_account
        upsert_connected_account(
            user_id=user_id,
            source="WHATSAPP",
            account_identifier=identifier,
            auth_credentials={
                "data_dir": data_dir,
                "status": "connected",
            },
            is_active=True,
        )
        print(f"WhatsApp account saved to DB for user {user_id}")
    except Exception as exc:
        print(f"Warning: Failed to save WhatsApp account to DB: {exc}")

    try:
        ensure_whatsapp_serve(user_id)
        print(f"WhatsApp live service started for user {user_id}")
    except Exception as exc:
        print(f"Failed to start WhatsApp live service for user {user_id}: {exc}")


async def disconnect_whatsapp(user_id: str) -> None:
    session = get_session(user_id)

    # Stop the long-running connection before asking the MCP server to log out.
    for process in (session.login_process, session.serve_process):
        await stop_whatsapp_process(process)

    session.login_process = None
    session.serve_process = None
    session.qr_data_url = None
    session.is_linked = False
    session.account_identifier = None
    session.error = None

    data_dir = get_user_data_dir(user_id)
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            build_command("logout", "--data-dir", data_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"WhatsApp logout failed for user {user_id}: {result.stderr.strip()}")
    except Exception as exc:
        print(f"[WhatsApp logout warning] {exc}")

    # Remove stale files in WSL
    if WHATSAPP_RUNTIME == "wsl":
        try:
            cleanup_cmd = f"rm -f {shlex.quote(data_dir)}/connection.lock {shlex.quote(data_dir)}/login-qr.png"
            await asyncio.to_thread(
                subprocess.run,
                ["wsl", "-e", "bash", "-lc", cleanup_cmd],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass
