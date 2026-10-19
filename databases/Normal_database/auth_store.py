import hashlib
import os
import uuid
from typing import Optional, Dict, Any
import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
USERS_FILE = BASE_DIR / "users.json"

# Attempt to use pwdlib Argon2 if available, otherwise PBKDF2 HMAC SHA-256
try:
    from pwdlib import PasswordHash
    _password_hash = PasswordHash.recommended()
    _USE_PWDLIB = True
except Exception:
    _USE_PWDLIB = False


def hash_password(password: str) -> str:
    """Hash a plaintext password securely."""
    if _USE_PWDLIB:
        try:
            return _password_hash.hash(password)
        except Exception:
            pass

    salt = os.urandom(16).hex()
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,
    ).hex()
    return f"pbkdf2:{salt}:{hashed}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a hash."""
    if not hashed_password:
        return False
    if hashed_password.startswith("pbkdf2:"):
        try:
            _, salt, hash_val = hashed_password.split(":")
            recomputed = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt.encode("utf-8"),
                100000,
            ).hex()
            return recomputed == hash_val
        except Exception:
            return False

    if _USE_PWDLIB:
        try:
            return _password_hash.verify(plain_password, hashed_password)
        except Exception:
            pass

    return False



def _read_users() -> list:
    if not USERS_FILE.exists():
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        return []
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_users(users: list) -> None:
    temp_file = USERS_FILE.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)
    temp_file.replace(USERS_FILE)


# =====================================================================
# SQL DATABASE AUTH CODE COMMENTED OUT FOR FILE STORAGE
# =====================================================================
# from databases.Normal_database.postgres_client import get_connection
#
# def _original_create_user(username: str, password: str):
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             cur.execute('SELECT id FROM users WHERE username = %s OR "user" = %s LIMIT 1;', (username, username))
#             if cur.fetchone():
#                 raise ValueError("User already exists.")
#             cur.execute(
#                 'INSERT INTO users (username, "user", password) VALUES (%s, %s, %s) RETURNING id, username, "user", created_at;',
#                 (username, username, hash_password(password))
#             )
#             user_row = cur.fetchone()
#             conn.commit()
#             return user_row
# =====================================================================


def create_user(username: str, password: str) -> Dict[str, Any]:
    """
    Inserts a new user into users.json file in the base directory.
    Configured for single-user mode.
    Raises ValueError if user with that username already exists.
    """
    username = username.strip()
    if not username:
        raise ValueError("Username cannot be empty.")
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters.")

    users = _read_users()
    for u in users:
        if u.get("username", "").lower() == username.lower() or u.get("user", "").lower() == username.lower():
            raise ValueError("User already exists.")

    hashed = hash_password(password)
    uid = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    new_user = {
        "id": uid,
        "user_id": uid,
        "username": username,
        "user": username,
        "password": hashed,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    users.append(new_user)
    _write_users(users)

    return {
        "id": uid,
        "user_id": uid,
        "username": username,
        "user": username,
        "created_at": now_iso,
    }


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Validates a username and password against users.json.
    Returns user details on success, None on failure.
    """
    username = username.strip()
    if not username or not password:
        return None

    users = _read_users()
    # Find matching user
    target_user = None
    for u in users:
        if u.get("username", "").lower() == username.lower() or u.get("user", "").lower() == username.lower():
            target_user = u
            break

    # If no users exist yet in single-user mode, auto-register this single user
    if not target_user and not users:
        return create_user(username, password)

    if not target_user:
        return None

    if not verify_password(password, target_user.get("password", "")):
        return None

    uid = str(target_user.get("id", "single_user"))
    return {
        "id": uid,
        "user_id": uid,
        "username": target_user.get("username", username),
        "user": target_user.get("user", username),
        "created_at": target_user.get("created_at"),
    }


def get_user_by_identifier(username_or_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch user by id or username from users.json.
    In single-user mode, falls back to the active single user if available.
    """
    identifier = str(username_or_id).strip()
    users = _read_users()

    # Exact match first
    for u in users:
        if (
            str(u.get("id")) == identifier
            or str(u.get("user_id")) == identifier
            or u.get("username", "").lower() == identifier.lower()
            or u.get("user", "").lower() == identifier.lower()
        ):
            uid = str(u.get("id"))
            return {
                "id": uid,
                "user_id": uid,
                "username": u.get("username"),
                "user": u.get("user"),
                "created_at": u.get("created_at"),
            }

    # In single-user mode, if exactly one user exists, return that user
    if len(users) == 1:
        u = users[0]
        uid = str(u.get("id"))
        return {
            "id": uid,
            "user_id": uid,
            "username": u.get("username"),
            "user": u.get("user"),
            "created_at": u.get("created_at"),
        }

    # If no registered users yet, return standard single-user stub
    if not users:
        return {
            "id": "single_user",
            "user_id": "single_user",
            "username": identifier or "single_user",
            "user": identifier or "single_user",
            "created_at": None,
        }

    return None


