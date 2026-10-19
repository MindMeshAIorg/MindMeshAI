
import asyncio
import base64
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Set WHATSAPP_RUNTIME to "wsl" for local Windows + WSL,
# or "native" when running the executable directly in Linux/Render.


WHATSAPP_RUNTIME = os.getenv("WHATSAPP_RUNTIME", "wsl").lower()

WHATSAPP_BINARY = os.getenv(
    "WHATSAPP_BINARY",
    "/mnt/c/Users/Abdul Hannan/OneDrive/Desktop/"
    "MindMeshAI/whatsapp-mcp-server/whatsapp-mcp",
)


WHATSAPP_DATA_ROOT = os.getenv(
    "WHATSAPP_DATA_ROOT",
    "/home/abdul_hannan/whatsapp-mcp-data",
)


@dataclass
class WhatsAppSession:
    login_process: Optional[asyncio.subprocess.Process] = None
    serve_process: Optional[asyncio.subprocess.Process] = None
    lock: Optional[asyncio.Lock] = None
    qr_data_url: Optional[str] = None


_sessions: dict[str, WhatsAppSession] = {}


def get_session(user_id: str) -> WhatsAppSession:
    if user_id not in _sessions:
        _sessions[user_id] = WhatsAppSession(
            lock=asyncio.Lock()
        )

    return _sessions[user_id]


def validate_user_id(user_id: str) -> None:
    if (
        not user_id
        or not user_id.replace("-", "").replace("_", "").isalnum()
    ):
        raise ValueError("Invalid user ID.")


def get_user_data_dir(user_id: str) -> str:
    validate_user_id(user_id)
    return f"{WHATSAPP_DATA_ROOT.rstrip('/')}/{user_id}"


def build_command(*args: str) -> list[str]:
    if WHATSAPP_RUNTIME == "wsl":
        if shutil.which("wsl") is None:
            raise RuntimeError(
                "WSL was not found. Install or enable WSL first."
            )

        # Bash safely resolves the executable path and its arguments.
        import shlex

        command = " ".join(
            shlex.quote(part)
            for part in (WHATSAPP_BINARY, *args)
        )

        return ["wsl", "-e", "bash", "-lc", command]

    if WHATSAPP_RUNTIME == "native":
        return [WHATSAPP_BINARY, *args]

    raise ValueError(
        "WHATSAPP_RUNTIME must be 'wsl' or 'native'."
    )


async def start_whatsapp_login(user_id: str) -> dict:
    session = get_session(user_id)

    async with session.lock:
        if (
            session.login_process
            and session.login_process.returncode is None
        ):
            return {"status": "login_in_progress"}

        if (
            session.serve_process
            and session.serve_process.returncode is None
        ):
            return {"status": "already_connected"}

        data_dir = get_user_data_dir(user_id)

        # Create the per-user directory in the Linux/WSL filesystem.
        command = build_command(
            "login",
            "--data-dir",
            data_dir,
            "--sync-idle",
            "90s",
        )

        session.qr_data_url = None

        session.login_process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Start reading output so the process pipes cannot fill up.
        asyncio.create_task(
            _capture_login_output(user_id)
        )

        return {"status": "login_started"}


async def _capture_login_output(user_id: str) -> None:
    """
    Read login output and capture login-qr.png while it exists.

    The Go server deletes its QR image when the login command exits,
    so the image must be copied while login is still running.
    """
    session = get_session(user_id)
    process = session.login_process

    if process is None:
        return

    async def read_stream(stream) -> None:
        while True:
            line = await stream.readline()

            if not line:
                break

            # Keep logs minimal; do not expose QR contents or credentials.
            print(f"[WhatsApp login] {line.decode(errors='replace').rstrip()}")

    stdout_task = asyncio.create_task(
        read_stream(process.stdout)
    )
    stderr_task = asyncio.create_task(
        read_stream(process.stderr)
    )

    # Poll the QR file in WSL until it appears or login exits.
    data_dir = get_user_data_dir(user_id)
    qr_path = f"{data_dir}/login-qr.png"

    while process.returncode is None:
        try:
            result = await asyncio.create_subprocess_exec(
                "wsl",
                "-e",
                "bash",
                "-lc",
                f"if [ -f {__import__('shlex').quote(qr_path)} ]; "
                f"then base64 -w 0 "
                f"{__import__('shlex').quote(qr_path)}; fi",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )

            output, _ = await result.communicate()

            if output:
                encoded = output.decode("ascii").strip()

                if encoded:
                    session.qr_data_url = (
                        f"data:image/png;base64,{encoded}"
                    )
                    break

        except Exception as exc:
            print(f"[WhatsApp QR polling] {exc}")

        await asyncio.sleep(1)

    await asyncio.gather(
        stdout_task,
        stderr_task,
        return_exceptions=True,
    )


async def get_whatsapp_qr(user_id: str) -> dict:
    session = get_session(user_id)
    process = session.login_process

    if process is None:
        return {"status": "not_started"}

    if session.qr_data_url:
        return {
            "status": "scan_qr",
            "qr_data_url": session.qr_data_url,
        }

    if process.returncode is not None:
        return {
            "status": "login_process_finished",
            "return_code": process.returncode,
        }

    return {"status": "waiting_for_qr"}


async def monitor_login(user_id: str) -> None:
    session = get_session(user_id)
    process = session.login_process

    if process is None:
        return

    return_code = await process.wait()

    if return_code != 0:
        print(
            f"WhatsApp login failed for user {user_id}; "
            f"exit code: {return_code}"
        )
        return

    # Start an HTTP MCP server so a separate MCP client can connect.
    # Bind locally during development. Configure a protected endpoint
    # and unique token before exposing this service remotely.
    data_dir = get_user_data_dir(user_id)

    session.serve_process = await asyncio.create_subprocess_exec(
        *build_command(
            "serve",
            "--transport",
            "http",
            "--addr",
            "127.0.0.1:0",
            "--data-dir",
            data_dir,
        ),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    print(
        f"WhatsApp login completed for user {user_id}. "
        "MCP server process started; configure an MCP client "
        "to use its endpoint before importing messages."
    )


async def disconnect_whatsapp(user_id: str) -> None:
    session = get_session(user_id)

    for process in (
        session.login_process,
        session.serve_process,
    ):
        if process and process.returncode is None:
            process.terminate()

            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=10,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    session.login_process = None
    session.serve_process = None
    session.qr_data_url = None
