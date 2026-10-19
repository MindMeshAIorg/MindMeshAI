import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONNECTED_ACCOUNTS_FILE = BASE_DIR / "connected_accounts.json"
CHECKPOINTS_FILE = BASE_DIR / "sync_checkpoints.json"
USERS_FILE = BASE_DIR / "users.json"

# =====================================================================
# SQL DATABASE SYNC STORE CODE COMMENTED OUT FOR FILE STORAGE
# =====================================================================
# from psycopg.types.json import Jsonb
# from databases.Normal_database.postgres_client import get_connection
#
# def _original_upsert_connected_account(user_id, source, account_identifier, auth_credentials, is_active=True):
#     with get_connection() as conn:
#         with conn.cursor() as cur:
#             cur.execute("INSERT INTO user_connected_accounts ...")
#         conn.commit()
# =====================================================================


def _read_json_file(file_path: Path, default_val: Any) -> Any:
    if not file_path.exists():
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(default_val, f, indent=2)
        return default_val
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_val


def _write_json_file(file_path: Path, data: Any) -> None:
    temp_file = file_path.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    temp_file.replace(file_path)


# =====================================================================
# Connected Accounts Operations (File-based, Single-User)
# =====================================================================


def upsert_connected_account(
    user_id: str,
    source: str,
    account_identifier: str,
    auth_credentials: Dict[str, Any],
    is_active: bool = True,
) -> None:
    """Save an account connection to connected_accounts.json in base directory."""
    source_clean = source.upper().strip()
    if not user_id or not account_identifier:
        raise ValueError("user_id and account_identifier are required.")

    accounts = _read_json_file(CONNECTED_ACCOUNTS_FILE, [])
    now_iso = datetime.now(timezone.utc).isoformat()

    # In single-user mode, or when managing Telegram OTP, handle existing accounts
    matched = False
    for acc in accounts:
        # Same source and identifier
        if (
            acc.get("source", "").upper() == source_clean
            and str(acc.get("account_identifier")) == str(account_identifier)
        ):
            # Update matching record
            acc["user_id"] = str(user_id)
            acc["auth_credentials"] = auth_credentials
            acc["is_active"] = is_active
            acc["updated_at"] = now_iso
            matched = True
            break

    if not matched:
        accounts.append({
            "id": str(uuid.uuid4()),
            "user_id": str(user_id),
            "source": source_clean,
            "account_identifier": str(account_identifier),
            "auth_credentials": auth_credentials,
            "is_active": is_active,
            "created_at": now_iso,
            "updated_at": now_iso,
        })

    _write_json_file(CONNECTED_ACCOUNTS_FILE, accounts)


def get_connected_account(
    user_id: str,
    source: str,
    account_identifier: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve an active connected account and its credentials from connected_accounts.json."""
    source_clean = source.upper().strip()
    accounts = _read_json_file(CONNECTED_ACCOUNTS_FILE, [])

    # Filter by source and is_active
    matching = [
        acc for acc in accounts
        if acc.get("source", "").upper() == source_clean
        and acc.get("is_active", True)
    ]

    # In single-user mode, if account_identifier is specified, filter by it
    if account_identifier:
        matching = [
            acc for acc in matching
            if str(acc.get("account_identifier")) == str(account_identifier)
        ]

    # Prioritize user_id match if multiple exist
    user_matching = [
        acc for acc in matching
        if str(acc.get("user_id")) == str(user_id)
    ]
    if user_matching:
        # Return most recently updated
        user_matching.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return user_matching[0]

    if matching:
        # Single-user fallback: return the active connection
        matching.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return matching[0]

    return None


def list_connected_accounts(
    user_id: str,
    source: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List all active connected accounts from connected_accounts.json."""
    accounts = _read_json_file(CONNECTED_ACCOUNTS_FILE, [])
    source_clean = source.upper().strip() if source else None

    results = []
    for acc in accounts:
        if not acc.get("is_active", True):
            continue
        if source_clean and acc.get("source", "").upper() != source_clean:
            continue
        # In single user mode, allow user match or fallback to all active accounts
        if str(acc.get("user_id")) == str(user_id) or user_id in ("single_user", "user_123", ""):
            results.append(acc)
        elif len(_read_json_file(USERS_FILE, [])) <= 1:
            # Only single user in system
            results.append(acc)

    # Remove sensitive tokens in listing if desired, but keep structure intact
    return [
        {
            "id": acc.get("id"),
            "user_id": acc.get("user_id"),
            "source": acc.get("source"),
            "account_identifier": acc.get("account_identifier"),
            "is_active": acc.get("is_active", True),
            "created_at": acc.get("created_at"),
            "updated_at": acc.get("updated_at"),
        }
        for acc in results
    ]


def deactivate_connected_account(
    user_id: str,
    source: str,
    account_identifier: str,
) -> bool:
    """Soft-deactivate an account connection in connected_accounts.json."""
    source_clean = source.upper().strip()
    accounts = _read_json_file(CONNECTED_ACCOUNTS_FILE, [])
    now_iso = datetime.now(timezone.utc).isoformat()
    updated = False

    for acc in accounts:
        if (
            acc.get("source", "").upper() == source_clean
            and str(acc.get("account_identifier")) == str(account_identifier)
        ):
            acc["is_active"] = False
            acc["updated_at"] = now_iso
            updated = True

    if updated:
        _write_json_file(CONNECTED_ACCOUNTS_FILE, accounts)
    return updated


# =====================================================================
# Sync Checkpoints Operations (File-based)
# =====================================================================


def get_sync_checkpoint(
    user_id: str,
    source: str,
    account_identifier: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get the current progress checkpoint data from sync_checkpoints.json."""
    source_clean = source.upper().strip()
    checkpoints = _read_json_file(CHECKPOINTS_FILE, [])

    matching = [
        cp for cp in checkpoints
        if cp.get("source", "").upper() == source_clean
    ]

    if account_identifier:
        matching = [
            cp for cp in matching
            if str(cp.get("account_identifier")) == str(account_identifier)
        ]

    # In single-user mode, match user_id or fallback
    user_matching = [
        cp for cp in matching
        if str(cp.get("user_id")) == str(user_id)
    ]
    target = user_matching[0] if user_matching else (matching[0] if matching else None)

    if not target:
        return None

    checkpoint_data = target.get("checkpoint_data", {})
    if isinstance(checkpoint_data, str):
        try:
            checkpoint_data = json.loads(checkpoint_data)
        except Exception:
            checkpoint_data = {}

    return {
        "checkpoint_data": checkpoint_data,
        "last_synced_at": target.get("last_synced_at"),
    }


def save_sync_checkpoint(
    user_id: str,
    source: str,
    account_identifier: str,
    checkpoint_data: Dict[str, Any],
) -> None:
    """Save or advance a sync checkpoint in sync_checkpoints.json."""
    source_clean = source.upper().strip()
    checkpoints = _read_json_file(CHECKPOINTS_FILE, [])
    now_iso = datetime.now(timezone.utc).isoformat()

    matched = False
    for cp in checkpoints:
        if (
            cp.get("source", "").upper() == source_clean
            and str(cp.get("account_identifier")) == str(account_identifier)
            and (str(cp.get("user_id")) == str(user_id) or user_id in ("single_user", "user_123"))
        ):
            cp["user_id"] = str(user_id)
            cp["checkpoint_data"] = checkpoint_data
            cp["last_synced_at"] = now_iso
            cp["updated_at"] = now_iso
            matched = True
            break

    if not matched:
        checkpoints.append({
            "id": str(uuid.uuid4()),
            "user_id": str(user_id),
            "source": source_clean,
            "account_identifier": str(account_identifier),
            "checkpoint_data": checkpoint_data,
            "last_synced_at": now_iso,
            "created_at": now_iso,
            "updated_at": now_iso,
        })

    _write_json_file(CHECKPOINTS_FILE, checkpoints)


def reset_sync_checkpoint(
    user_id: str,
    source: str,
    account_identifier: str,
) -> bool:
    """Delete a sync checkpoint from sync_checkpoints.json."""
    source_clean = source.upper().strip()
    checkpoints = _read_json_file(CHECKPOINTS_FILE, [])
    initial_len = len(checkpoints)

    checkpoints = [
        cp for cp in checkpoints
        if not (
            cp.get("source", "").upper() == source_clean
            and str(cp.get("account_identifier")) == str(account_identifier)
        )
    ]

    deleted = len(checkpoints) < initial_len
    if deleted:
        _write_json_file(CHECKPOINTS_FILE, checkpoints)
    return deleted


# =====================================================================
# User Discovery and Activity Tracking (Single-User Mode)
# =====================================================================


def touch_user_activity(user_id: str) -> None:
    """Update user updated_at timestamp in users.json."""
    if not user_id:
        return
    users = _read_json_file(USERS_FILE, [])
    now_iso = datetime.now(timezone.utc).isoformat()
    updated = False

    for u in users:
        if (
            str(u.get("id")) == str(user_id)
            or str(u.get("user_id")) == str(user_id)
            or u.get("username") == str(user_id)
        ):
            u["updated_at"] = now_iso
            updated = True
            break

    if updated:
        _write_json_file(USERS_FILE, users)


def get_users_with_connected_accounts() -> List[Dict[str, Any]]:
    """
    Retrieve registered users for ingestion.
    Configured for single-user mode: returns the active user profile.
    """
    users = _read_json_file(USERS_FILE, [])
    accounts = _read_json_file(CONNECTED_ACCOUNTS_FILE, [])
    active_accounts = [a for a in accounts if a.get("is_active", True)]

    # If users exist in users.json
    if users:
        # If there's an active connected account linked to a user, match them
        user_ids_with_accounts = {str(a.get("user_id")) for a in active_accounts}
        matched_users = [
            u for u in users
            if str(u.get("id")) in user_ids_with_accounts or u.get("username") in user_ids_with_accounts
        ]
        if matched_users:
            return [
                {
                    "user_id": str(u.get("id")),
                    "username": u.get("username", "user"),
                    "display_name": u.get("user") or u.get("username", "user"),
                }
                for u in matched_users
            ]

        # Return all registered users (or single user)
        return [
            {
                "user_id": str(u.get("id")),
                "username": u.get("username", "user"),
                "display_name": u.get("user") or u.get("username", "user"),
            }
            for u in users
        ]

    # If connected accounts exist but no users in users.json yet
    if active_accounts:
        first_uid = str(active_accounts[0].get("user_id", "single_user"))
        return [{
            "user_id": first_uid,
            "username": first_uid,
            "display_name": "Single User",
        }]

    # Default single-user fallback
    return [{
        "user_id": "single_user",
        "username": "single_user",
        "display_name": "Single User",
    }]


def get_user_by_id_or_username(identifier: str) -> Optional[Dict[str, Any]]:
    """Look up a registered user by UUID string or username from users.json."""
    if not identifier:
        return None
    from databases.Normal_database.auth_store import get_user_by_identifier
    return get_user_by_identifier(identifier)

