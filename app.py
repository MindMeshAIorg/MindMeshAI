import os
import json
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------

load_dotenv()

# Local development only. Do not enable this in production.
if os.getenv("ENVIRONMENT", "development") == "development":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

SRC_DIR = BASE_DIR / "src"

# ---------------------------------------------------------
# FastAPI imports
# ---------------------------------------------------------

from fastapi import FastAPI, Request, HTTPException, Body, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    RedirectResponse,
    JSONResponse,
    FileResponse,
)
from fastapi.staticfiles import StaticFiles

from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------
# Google OAuth imports
# ---------------------------------------------------------

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# ---------------------------------------------------------
# Telegram imports
# ---------------------------------------------------------

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# ---------------------------------------------------------
# MindMeshAI database imports
# ---------------------------------------------------------

from databases.Normal_database.sync_store import (
    upsert_connected_account,
    list_connected_accounts,
    deactivate_connected_account,
    touch_user_activity,
)
from databases.Normal_database.data_insertion_updation import (
    get_active_items,
    complete_item,
)
from databases.Normal_database.postgres_client import test_postgres_connection
from databases.Vector_Database.qdrant_setup import test_qdrant_connection
import uuid

# ---------------------------------------------------------
# WhatsApp imports
# ---------------------------------------------------------

from MCP_and_connectors.whatsapp_connection import (
    start_whatsapp_login,
    get_whatsapp_qr,
    disconnect_whatsapp,
)

# ---------------------------------------------------------
# Chatbot imports
# ---------------------------------------------------------

from chatbot.llm import generate_answer

from chatbot.memory import (
    get_recent_messages,
    save_message,
    get_long_term_memory,
    remember,
)

try:
    from chatbot.rag_retriever import retrieve_context
except ImportError:
    try:
        from rag_retriever import retrieve_context
    except ImportError:
        async def retrieve_context(message: str, user_id: str):
            return None

from databases.Normal_database.auth_store import (
    create_user,
    authenticate_user,
    get_user_by_identifier,
)

import importlib.util

_rag_runner_module = None

def get_rag_runner():
    global _rag_runner_module
    if _rag_runner_module is None:
        runner_file = BASE_DIR / "rag_runner_2.0.py"
        spec = importlib.util.spec_from_file_location("rag_runner_2_0", runner_file)
        _rag_runner_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_rag_runner_module)
    return _rag_runner_module


async def trigger_user_sync_background(user_id: str, username: str = "User", initial_sync: bool = False):
    """Run RAG ingestion for the logged-in user in the background without blocking the UI."""
    print(f"\n[Auto-Sync] Triggering background RAG ingestion for logged-in user: {username} ({user_id})...")
    try:
        runner = get_rag_runner()
        await runner.run_ingestion_for_user(
            user_id=user_id,
            username=username,
            initial_sync=initial_sync,
        )
        print(f"[Auto-Sync] Background RAG ingestion completed for {username} ({user_id}).")
    except Exception as exc:
        print(f"[Auto-Sync] Error during background ingestion for {username} ({user_id}): {exc}")





# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title="MindMeshAI",
    description="MindMeshAI Chatbot and Multi-User Integrations Hub",
    version="1.0.0",
)


# =========================================================
# CORS CONFIGURATION
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://localhost:5137",
        ).split(",")
        if origin.strip()
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# =========================================================
# SESSION CONFIGURATION
# =========================================================

secret = os.getenv(
    "SESSION_SECRET",
    "mindmesh_default_local_secret_session_key",
)

if (
    os.getenv("ENVIRONMENT", "development") == "production"
    and secret == "mindmesh_default_local_secret_session_key"
):
    raise RuntimeError(
        "Set a strong SESSION_SECRET environment variable in production."
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=secret,
    same_site="lax",
    https_only=os.getenv("ENVIRONMENT") == "production",
)


# =========================================================
# STATIC FILES
# =========================================================

if SRC_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(SRC_DIR)),
        name="static",
    )


# =========================================================
# GLOBAL CONFIGURATION
# =========================================================

REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/auth/gmail/callback",
)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]

TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))

TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")

# Temporary storage for Telegram login sessions.
telegram_pending_sessions: dict[str, dict] = {}


# =========================================================
# REQUEST MODELS
# =========================================================

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str | None = Field(default=None, max_length=128)


class AuthRequest(BaseModel):
    username: str | None = None
    user: str | None = None
    password: str = Field(min_length=4)


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "MindMeshAI",
    }


# =========================================================
# CHATBOT ENDPOINT
# =========================================================

@app.post("/api/chat")
async def chat(http_request: Request, request: ChatRequest):
    message = request.message.strip()
    raw_uid = (request.user_id or "").strip()
    canonical_uid = resolve_canonical_user_id(raw_uid, http_request.session)
    user_id = canonical_uid or raw_uid

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="User ID required. Please log in or provide user_id.",
        )

    touch_user_activity(user_id)


    # ---------------------------------------------
    # Save a long-term memory explicitly
    # Example: remember: My exam is on Monday
    # ---------------------------------------------

    if message.lower().startswith("remember:"):
        fact = message[len("remember:"):].strip()

        if not fact or len(fact) > 300:
            raise HTTPException(
                status_code=400,
                detail="Memory must be 1 to 300 characters.",
            )

        remember(user_id, fact)

        return {
            "answer": "I'll remember that for future conversations."
        }

    # ---------------------------------------------
    # Retrieve conversation history and memories
    # ---------------------------------------------

    history = get_recent_messages(user_id)

    memories = get_long_term_memory(user_id)

    try:
        # Retrieve relevant information from the vector database.
        context = await retrieve_context(message, user_id)

        # Generate the response using the LLM.
        answer = generate_answer(
            message,
            context=context,
            history=history,
            memories=memories,
        )

        # Save both messages after generating the answer.
        save_message(user_id, "user", message)

        save_message(user_id, "assistant", answer)

        return {
            "answer": answer
        }

    except Exception as exc:
        traceback.print_exc()

        raise HTTPException(
            status_code=502,
            detail=(
                f"Chatbot failed: "
                f"{type(exc).__name__}: {exc}"
            ),
        )


# =========================================================
# CHAT HISTORY ENDPOINT
# =========================================================

@app.get("/api/chat/history")
def chat_history(request: Request, user_id: str | None = None):
    uid = (
        user_id
        or request.session.get("user_id")
        or request.session.get("user", {}).get("user_id")
        or request.session.get("user", {}).get("username")
    )
    if not uid:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in.",
        )
    touch_user_activity(uid)
    try:
        messages = get_recent_messages(uid)
        return {"user_id": uid, "messages": messages}
    except Exception as exc:
        return {"user_id": uid, "messages": []}


# =========================================================
# AUTHENTICATION ENDPOINTS
# =========================================================

@app.post("/api/auth/signup")
def signup(request: Request, payload: AuthRequest, background_tasks: BackgroundTasks):
    username = (payload.username or payload.user or "").strip()
    if not username:
        raise HTTPException(
            status_code=400,
            detail="Username is required.",
        )

    try:
        user_record = create_user(username, payload.password)
        uid = str(user_record.get("user_id") or user_record.get("id"))
        username_val = user_record.get("username", username)
        request.session["user"] = user_record
        request.session["user_id"] = uid
        touch_user_activity(uid)

        # Trigger RAG ingestion for the newly registered user in the background
        background_tasks.add_task(
            trigger_user_sync_background,
            user_id=uid,
            username=username_val,
            initial_sync=True,
        )

        return {
            "success": True,
            "message": "User registered successfully.",
            "user": user_record,
        }
    except ValueError as val_err:
        raise HTTPException(
            status_code=400,
            detail=str(val_err),
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Failed to create user account.",
        )


@app.post("/api/auth/login")
def login(request: Request, payload: AuthRequest, background_tasks: BackgroundTasks):
    username = (payload.username or payload.user or "").strip()
    if not username:
        raise HTTPException(
            status_code=400,
            detail="Username is required.",
        )

    user_record = authenticate_user(username, payload.password)
    if not user_record:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password.",
        )

    uid = str(user_record.get("user_id") or user_record.get("id"))
    username_val = user_record.get("username", username)
    request.session["user"] = user_record
    request.session["user_id"] = uid
    touch_user_activity(uid)

    # Automatically trigger RAG ingestion for this logged-in user using their exact user_id
    background_tasks.add_task(
        trigger_user_sync_background,
        user_id=uid,
        username=username_val,
        initial_sync=False,
    )

    return {
        "success": True,
        "message": "Logged in successfully.",
        "user": user_record,
    }


@app.post("/api/sync")
async def sync_data(request: Request, background_tasks: BackgroundTasks, payload: dict = Body(default={})):
    """Allow logged-in users to trigger an on-demand sync of their connected accounts."""
    uid = (
        payload.get("user_id")
        or request.session.get("user_id")
        or request.session.get("user", {}).get("user_id")
        or request.session.get("user", {}).get("username")
    )
    if not uid:
        raise HTTPException(
            status_code=401,
            detail="User ID required. Please log in.",
        )

    uid_str = str(uid)
    username = request.session.get("user", {}).get("username") or uid_str
    initial = bool(payload.get("initial", False))

    background_tasks.add_task(
        trigger_user_sync_background,
        user_id=uid_str,
        username=username,
        initial_sync=initial,
    )

    return {
        "success": True,
        "message": f"Data sync initiated for {username}.",
        "user_id": uid_str,
    }



@app.get("/api/auth/me")
def get_current_user(request: Request):
    user_record = request.session.get("user")
    if user_record:
        return {"authenticated": True, "user": user_record}
    return {"authenticated": False, "user": None}


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"success": True, "message": "Logged out successfully."}


@app.get("/api/database/status")
def database_status():
    """Verify health and connectivity of both PostgreSQL and Qdrant Cloud."""
    pg_status = test_postgres_connection()
    qdrant_status = test_qdrant_connection()
    all_ok = pg_status.get("status") == "ok" and qdrant_status.get("status") in ("ok", "warning")
    return {
        "status": "healthy" if all_ok else "unhealthy",
        "postgres": pg_status,
        "qdrant": qdrant_status,
    }


@app.get("/api/notifications")
def get_user_notifications(request: Request, user_id: str | None = None):
    """Retrieve important items and reminders stored in PostgreSQL for the active user."""
    canonical_uid = resolve_canonical_user_id(user_id, request.session)
    if not canonical_uid:
        raise HTTPException(
            status_code=401,
            detail="User ID required. Please log in.",
        )

    # Fetch notifications for canonical_uid
    items = get_active_items(canonical_uid)

    # Also check if items exist under the raw user_id/username and merge
    raw_uid = (user_id or "").strip()
    if raw_uid and raw_uid != canonical_uid:
        extra_items = get_active_items(raw_uid)
        seen_ids = {str(it.get("chunk_id")) for it in items}
        for extra in extra_items:
            if str(extra.get("chunk_id")) not in seen_ids:
                items.append(extra)

    # Format timestamps for JSON serialization
    serialized_items = []
    for it in items:
        item_dict = dict(it)
        for k, v in item_dict.items():
            if hasattr(v, "isoformat"):
                item_dict[k] = v.isoformat()
            elif isinstance(v, uuid.UUID):
                item_dict[k] = str(v)
        serialized_items.append(item_dict)

    return {
        "user_id": canonical_uid,
        "notifications": serialized_items,
        "count": len(serialized_items),
    }


@app.post("/api/notifications/complete")
def complete_notification_item(
    request: Request,
    payload: dict = Body(...),
):
    """Mark an important item as completed in PostgreSQL."""
    chunk_id = payload.get("chunk_id")
    raw_uid = payload.get("user_id")
    canonical_uid = resolve_canonical_user_id(raw_uid, request.session)

    if not chunk_id or not canonical_uid:
        raise HTTPException(
            status_code=400,
            detail="chunk_id and user_id are required.",
        )

    success = complete_item(chunk_id, canonical_uid)
    if not success and raw_uid and raw_uid != canonical_uid:
        success = complete_item(chunk_id, raw_uid)

    return {
        "success": success,
        "chunk_id": str(chunk_id),
    }


# =========================================================
# GOOGLE OAUTH HELPER
# =========================================================

def create_flow(state=None):
    client_id = os.getenv("GOOGLE_CLIENT_ID")

    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    redirect_uri = os.getenv(
        "GOOGLE_REDIRECT_URI",
        REDIRECT_URI,
    )

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail=(
                "GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET "
                "is missing from your .env file."
            ),
        )

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": (
                "https://accounts.google.com/o/oauth2/auth"
            ),
            "token_uri": (
                "https://oauth2.googleapis.com/token"
            ),
            "redirect_uris": [redirect_uri],
        }
    }

    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        state=state,
        redirect_uri=redirect_uri,
    )


# =========================================================
# FRONTEND ENDPOINTS
# =========================================================

@app.get("/", response_class=FileResponse)
def home():
    dashboard_file = SRC_DIR / "dashboard.html"
    if dashboard_file.exists():
        return FileResponse(str(dashboard_file), media_type="text/html")
    raise HTTPException(status_code=404, detail="dashboard.html not found in src folder.")


@app.get("/dashboard", response_class=FileResponse)
def dashboard_page():
    dashboard_file = SRC_DIR / "dashboard.html"
    if dashboard_file.exists():
        return FileResponse(str(dashboard_file), media_type="text/html")
    raise HTTPException(status_code=404, detail="dashboard.html not found in src folder.")


@app.get("/login", response_class=FileResponse)
def login_page():
    login_file = SRC_DIR / "login.html"
    if login_file.exists():
        return FileResponse(str(login_file), media_type="text/html")
    raise HTTPException(status_code=404, detail="login.html not found in src folder.")


@app.get("/signup", response_class=FileResponse)
def signup_page():
    login_file = SRC_DIR / "login.html"
    if login_file.exists():
        return FileResponse(str(login_file), media_type="text/html")
    raise HTTPException(status_code=404, detail="login.html not found in src folder.")


@app.get("/conectors", response_class=FileResponse)
@app.get("/connectors", response_class=FileResponse)
@app.get("/conectors.html", response_class=FileResponse)
def connectors_page():
    conectors_file = SRC_DIR / "conectors.html"
    if conectors_file.exists():
        return FileResponse(str(conectors_file), media_type="text/html")
    raise HTTPException(status_code=404, detail="conectors.html not found in src folder.")


@app.get("/conectors.css", response_class=FileResponse)
@app.get("/style.css", response_class=FileResponse)
def get_conectors_css():
    css_file = SRC_DIR / "conectors.css"
    if css_file.exists():
        return FileResponse(str(css_file), media_type="text/css")
    raise HTTPException(status_code=404, detail="conectors.css not found in src folder.")


@app.get("/conectors.js", response_class=FileResponse)
@app.get("/script.js", response_class=FileResponse)
def get_conectors_js():
    js_file = SRC_DIR / "conectors.js"
    if js_file.exists():
        return FileResponse(str(js_file), media_type="application/javascript")
    raise HTTPException(status_code=404, detail="conectors.js not found in src folder.")


@app.get("/dashboard.css", response_class=FileResponse)
def get_dashboard_css():
    css_file = SRC_DIR / "dashboard.css"
    if css_file.exists():
        return FileResponse(str(css_file), media_type="text/css")
    raise HTTPException(status_code=404, detail="dashboard.css not found in src folder.")


@app.get("/dashboard.js", response_class=FileResponse)
def get_dashboard_js():
    js_file = SRC_DIR / "dashboard.js"
    if js_file.exists():
        return FileResponse(str(js_file), media_type="application/javascript")
    raise HTTPException(status_code=404, detail="dashboard.js not found in src folder.")


@app.get("/login.css", response_class=FileResponse)
def get_login_css():
    css_file = SRC_DIR / "login.css"
    if css_file.exists():
        return FileResponse(str(css_file), media_type="text/css")
    raise HTTPException(status_code=404, detail="login.css not found in src folder.")


@app.get("/login.js", response_class=FileResponse)
def get_login_js():
    js_file = SRC_DIR / "login.js"
    if js_file.exists():
        return FileResponse(str(js_file), media_type="application/javascript")
    raise HTTPException(status_code=404, detail="login.js not found in src folder.")



# =========================================================
# CANONICAL USER RESOLUTION HELPER
# =========================================================

def resolve_canonical_user_id(identifier: str | None = None, session: dict | None = None) -> str | None:
    """
    Resolves any username or user UUID to the canonical user ID (UUID).
    Falls back to session user_id or the active registered user in single-user mode.
    """
    raw = (
        (identifier or "").strip()
        or (session.get("user_id") if session else None)
        or (session.get("user", {}).get("user_id") if session else None)
        or (session.get("user", {}).get("username") if session else None)
    )
    if not raw:
        # In single-user mode, fallback to the registered user
        try:
            from databases.Normal_database.sync_store import get_users_with_connected_accounts
            users = get_users_with_connected_accounts()
            if users and users[0].get("user_id"):
                return str(users[0]["user_id"])
        except Exception:
            pass
        return "single_user"

    try:
        user = get_user_by_identifier(str(raw))
        if user and user.get("id"):
            return str(user["id"])
    except Exception:
        pass
    return str(raw).strip()


# =========================================================
# CONNECTED ACCOUNT ENDPOINTS
# =========================================================

@app.get("/accounts")
def get_accounts(request: Request, user_id: str | None = None):
    canonical_uid = resolve_canonical_user_id(user_id, request.session)
    if not canonical_uid:
        raise HTTPException(
            status_code=401,
            detail="User ID required. Please log in.",
        )

    # Fetch accounts for canonical_uid
    accounts = list_connected_accounts(user_id=canonical_uid)

    # If raw user_id differs, also fetch any legacy accounts and merge
    raw_uid = (user_id or "").strip()
    if raw_uid and raw_uid != canonical_uid:
        alt_accounts = list_connected_accounts(user_id=raw_uid)
        seen = {(a["source"], a["account_identifier"]) for a in accounts}
        for alt in alt_accounts:
            if (alt["source"], alt["account_identifier"]) not in seen:
                accounts.append(alt)

    return {
        "user_id": canonical_uid,
        "accounts": accounts,
    }


@app.post("/accounts/disconnect")
async def disconnect_account_endpoint(
    request: Request,
    payload: dict = Body(...),
):
    raw_user_id = payload.get("user_id")
    canonical_uid = resolve_canonical_user_id(raw_user_id, request.session)
    source = payload.get("source")
    identifier = payload.get("account_identifier")

    if not canonical_uid or not source:
        raise HTTPException(
            status_code=400,
            detail="user_id and source required.",
        )

    source = source.upper()

    if source == "WHATSAPP":
        await disconnect_whatsapp(canonical_uid)
        if raw_user_id and raw_user_id != canonical_uid:
            await disconnect_whatsapp(raw_user_id)

    # Deactivate for canonical_uid and raw_user_id
    uids_to_deactivate = {canonical_uid}
    if raw_user_id:
        uids_to_deactivate.add(raw_user_id)

    for uid in uids_to_deactivate:
        if not identifier:
            accounts = list_connected_accounts(user_id=uid, source=source)
            for account in accounts:
                deactivate_connected_account(uid, source, account["account_identifier"])
        else:
            deactivate_connected_account(uid, source, identifier)

    return {
        "success": True,
        "message": f"{source} account disconnected.",
    }


# =========================================================
# GMAIL OAUTH ENDPOINTS
# =========================================================

@app.get("/auth/gmail")
def start_gmail_oauth(
    request: Request,
    user_id: str | None = None,
):
    uid = (
        user_id
        or request.session.get("user_id")
        or request.session.get("user", {}).get("user_id")
        or request.session.get("user", {}).get("username")
    )
    if not uid:
        return RedirectResponse("/login")

    flow = create_flow()

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    request.session["oauth_state"] = state

    request.session["code_verifier"] = flow.code_verifier

    request.session["user_id"] = uid

    return RedirectResponse(authorization_url)



@app.get("/auth/gmail/callback")
def gmail_oauth_callback(request: Request):
    state = request.session.get("oauth_state")

    if not state:
        return JSONResponse(
            {
                "error": (
                    "OAuth state missing. "
                    "Start again at /auth/gmail."
                )
            },
            status_code=400,
        )

    if request.query_params.get("error"):
        error = request.query_params.get("error")

        return JSONResponse(
            {"error": error},
            status_code=400,
        )

    # Normalize localhost and 127.0.0.1.
    request_url = str(request.url)

    redirect_uri = os.getenv(
        "GOOGLE_REDIRECT_URI",
        REDIRECT_URI,
    )

    if (
        "127.0.0.1" in request_url
        and "localhost" in redirect_uri
    ):
        request_url = request_url.replace(
            "127.0.0.1",
            "localhost",
            1,
        )

    elif (
        "localhost" in request_url
        and "127.0.0.1" in redirect_uri
    ):
        request_url = request_url.replace(
            "localhost",
            "127.0.0.1",
            1,
        )

    flow = create_flow(state=state)

    flow.code_verifier = request.session.get(
        "code_verifier"
    )

    try:
        flow.fetch_token(
            authorization_response=request_url
        )

    except Exception as exc:
        traceback.print_exc()

        return JSONResponse(
            {
                "error": "Google OAuth failed",
                "details": str(exc),
                "hint": (
                    "Check the registered redirect URI "
                    "and try again."
                ),
            },
            status_code=400,
        )

    credentials = flow.credentials

    user_id = (
        request.session.get("user_id")
        or request.session.get("user", {}).get("user_id")
        or request.session.get("user", {}).get("username")
    )
    if not user_id:
        return RedirectResponse("/login")

    # Fetch the authenticated Gmail address.
    try:
        service = build(
            "gmail",
            "v1",
            credentials=credentials,
        )

        profile = (
            service.users()
            .getProfile(userId="me")
            .execute()
        )

        email_address = profile.get(
            "emailAddress",
            "unknown@gmail.com",
        )

    except Exception:
        traceback.print_exc()

        raise HTTPException(
            status_code=502,
            detail="Could not retrieve the Gmail profile.",
        )

    # Store account details and credentials.
    upsert_connected_account(
        user_id=user_id,
        source="GMAIL",
        account_identifier=email_address,
        auth_credentials=json.loads(
            credentials.to_json()
        ),
        is_active=True,
    )

    request.session.pop("oauth_state", None)

    request.session.pop("code_verifier", None)

    return RedirectResponse(
        f"/conectors.html?user_id={user_id}&connected=gmail"
    )



# =========================================================
# TELEGRAM AUTHENTICATION ENDPOINTS
# =========================================================

@app.post("/auth/telegram/send-code")
async def telegram_send_code(
    request: Request,
    payload: dict = Body(...),
):
    raw_user_id = payload.get("user_id")
    user_id = resolve_canonical_user_id(raw_user_id, request.session)
    phone = (payload.get("phone") or "").strip()

    if not user_id or not phone:
        raise HTTPException(
            status_code=400,
            detail="user_id and phone are required.",
        )

    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        raise HTTPException(
            status_code=500,
            detail=(
                "TELEGRAM_API_ID or TELEGRAM_API_HASH "
                "is missing from .env"
            ),
        )

    client = None

    try:
        client = TelegramClient(
            StringSession(),
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
        )

        await client.connect()

        result = await client.send_code_request(phone)

        session_entry = {
            "client": client,
            "phone": phone,
            "phone_code_hash": result.phone_code_hash,
        }
        telegram_pending_sessions[user_id] = session_entry
        if raw_user_id and raw_user_id != user_id:
            telegram_pending_sessions[raw_user_id] = session_entry

        return {
            "success": True,
            "message": (
                "Verification code sent to your Telegram app."
            ),
            "phone": phone,
        }

    except Exception as exc:
        traceback.print_exc()
        if client is not None:
            await client.disconnect()

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


@app.post("/auth/telegram/verify-code")
async def telegram_verify_code(
    request: Request,
    payload: dict = Body(...),
):
    raw_user_id = payload.get("user_id")
    user_id = resolve_canonical_user_id(raw_user_id, request.session)
    code = str(payload.get("code") or "").strip().replace(" ", "")
    password = payload.get("password")

    if not user_id or not code:
        raise HTTPException(
            status_code=400,
            detail="user_id and code are required.",
        )

    pending = telegram_pending_sessions.get(user_id) or (
        telegram_pending_sessions.get(raw_user_id) if raw_user_id else None
    )

    if not pending:
        raise HTTPException(
            status_code=400,
            detail=(
                "No Telegram login in progress for this user. "
                "Please send code first."
            ),
        )

    client: TelegramClient = pending["client"]
    phone = pending["phone"]
    phone_code_hash = pending["phone_code_hash"]

    try:
        if not client.is_connected():
            await client.connect()

        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash,
            )

        except SessionPasswordNeededError:
            if not password:
                return {
                    "success": False,
                    "needs_password": True,
                    "message": "2FA password is required.",
                }

            await client.sign_in(password=password)

        # Extract the reusable Telegram session.
        session_string = client.session.save()
        me = await client.get_me()
        telegram_id = str(me.id) if me else "unknown"
        tg_username = getattr(me, "username", "") or ""

        print("[Telegram Auth] Canonical MindMesh user ID:", user_id)
        print("[Telegram Auth] Telegram account ID:", telegram_id)

        # Save the account and session to database under canonical user_id
        upsert_connected_account(
            user_id=user_id,
            source="TELEGRAM",
            account_identifier=telegram_id,
            auth_credentials={
                "phone": phone,
                "session_string": session_string,
                "user_id": telegram_id,
                "username": tg_username,
            },
            is_active=True,
        )

        telegram_pending_sessions.pop(user_id, None)
        if raw_user_id:
            telegram_pending_sessions.pop(raw_user_id, None)

        await client.disconnect()

        return {
            "success": True,
            "message": (
                "Telegram successfully connected "
                "and saved to database!"
            ),
            "telegram_id": telegram_id,
        }

    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# =========================================================
# WHATSAPP AUTHENTICATION ENDPOINTS
# =========================================================

@app.post("/auth/whatsapp/start")
async def whatsapp_start(
    request: Request,
    payload: dict = Body(...),
):
    raw_user_id = payload.get("user_id")
    user_id = resolve_canonical_user_id(raw_user_id, request.session)
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="user_id is required. Please log in.",
        )

    try:
        result = await start_whatsapp_login(user_id)
        return result

    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=(
                f"WhatsApp start error: "
                f"{type(exc).__name__}: {exc}"
            ),
        )


@app.get("/auth/whatsapp/qr")
async def whatsapp_qr(
    request: Request,
    user_id: str | None = None,
):
    canonical_uid = resolve_canonical_user_id(user_id, request.session)
    if not canonical_uid:
        raise HTTPException(
            status_code=400,
            detail="user_id is required. Please log in.",
        )

    try:
        result = await get_whatsapp_qr(canonical_uid)
        return result

    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=(
                f"WhatsApp QR error: "
                f"{type(exc).__name__}: {exc}"
            ),
        )


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )