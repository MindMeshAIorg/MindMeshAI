"""
Multi-user, read-only WhatsApp MCP server (Python).

- Each `user_id` gets its own linked WhatsApp session + its own SQLite archive
  under  <DATA_DIR>/<user_id>/
- Read-only: there is NO send capability.
- get_messages(user_id, chat_name=None, days=None)
    * chat_name given  -> only that chat
    * chat_name empty  -> all chats
    * days given       -> only the last N days
    * days empty       -> everything archived

Install:
    pip install "mcp[cli]" neonize segno

Run (stdio, e.g. for Claude Desktop / Claude Code):
    python whatsapp_mcp_server.py
Run (HTTP):
    python whatsapp_mcp_server.py --transport http --port 8765

NOTE: neonize is a Python wrapper around whatsmeow (unofficial protocol).
Event/field names can differ slightly between neonize versions, so the
ingest code below reads fields defensively.
"""

import argparse
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

DATA_DIR = Path(os.environ.get("WHATSAPP_MCP_DATA_DIR", "~/.local/share/whatsapp-mcp-py")).expanduser()
DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)

mcp = FastMCP("whatsapp-mcp-py")

_USER_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


# --------------------------------------------------------------------------- #
# Archive (per-user SQLite)
# --------------------------------------------------------------------------- #
SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    jid TEXT PRIMARY KEY,
    name TEXT,
    is_group INTEGER DEFAULT 0,
    last_ts INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT,
    chat_jid TEXT,
    sender TEXT,
    sender_name TEXT,
    from_me INTEGER DEFAULT 0,
    ts INTEGER,
    text TEXT,
    kind TEXT DEFAULT 'text',
    PRIMARY KEY (id, chat_jid)
);
CREATE INDEX IF NOT EXISTS idx_msg_chat_ts ON messages(chat_jid, ts);
CREATE INDEX IF NOT EXISTS idx_msg_ts ON messages(ts);
"""


def _user_dir(user_id: str) -> Path:
    if not _USER_RE.match(user_id or ""):
        raise ValueError("user_id must be 1-64 chars: letters, digits, '_', '-', '.'")
    d = DATA_DIR / user_id
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def _db(user_id: str) -> sqlite3.Connection:
    con = sqlite3.connect(_user_dir(user_id) / "archive.db", timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def _fmt_ts(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


# --------------------------------------------------------------------------- #
# WhatsApp session manager (one neonize client per user_id)
# --------------------------------------------------------------------------- #
class Session:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.client = None
        self.thread: Optional[threading.Thread] = None
        self.connected = False
        self.last_qr_path: Optional[str] = None
        self.pair_code: Optional[str] = None
        self.error: Optional[str] = None

    # ---- ingest helpers ---- #
    @staticmethod
    def _jid_str(jid) -> str:
        user = getattr(jid, "User", "") or ""
        server = getattr(jid, "Server", "") or ""
        return f"{user}@{server}" if user else ""

    @staticmethod
    def _extract(m) -> tuple[str, str]:
        """Return (text, kind) from a WhatsApp protobuf message."""
        if m is None:
            return "", "other"
        try:
            if m.conversation:
                return m.conversation, "text"
            if m.HasField("extendedTextMessage"):
                return m.extendedTextMessage.text, "text"
            for field, kind in (
                ("imageMessage", "image"),
                ("videoMessage", "video"),
                ("documentMessage", "document"),
                ("audioMessage", "audio"),
                ("stickerMessage", "sticker"),
            ):
                if m.HasField(field):
                    sub = getattr(m, field)
                    caption = getattr(sub, "caption", "") or getattr(sub, "fileName", "") or ""
                    return caption, kind
        except Exception:
            pass
        return "", "other"

    def _store(self, info, message_proto):
        try:
            src = info.MessageSource
            chat = self._jid_str(src.Chat)
            if not chat or chat.endswith("@broadcast"):  # skip status/stories
                return
            text, kind = self._extract(message_proto)
            if not text and kind == "other":
                return
            ts_raw = int(getattr(info, "Timestamp", 0) or 0)
            ts = ts_raw // 1000 if ts_raw > 10**11 else ts_raw  # ms -> s
            sender = self._jid_str(src.Sender)
            from_me = 1 if getattr(src, "IsFromMe", False) else 0
            push = getattr(info, "Pushname", "") or ""
            is_group = 1 if chat.endswith("@g.us") else 0

            con = _db(self.user_id)
            with con:
                name = None
                if is_group:
                    try:
                        name = self.client.get_group_info(src.Chat).GroupName.Name
                    except Exception:
                        name = None
                elif not from_me and push:
                    name = push
                row = con.execute("SELECT name FROM chats WHERE jid=?", (chat,)).fetchone()
                if row is None:
                    con.execute(
                        "INSERT INTO chats(jid,name,is_group,last_ts) VALUES(?,?,?,?)",
                        (chat, name or chat.split("@")[0], is_group, ts),
                    )
                else:
                    con.execute(
                        "UPDATE chats SET last_ts=MAX(last_ts,?), name=COALESCE(?,name) WHERE jid=?",
                        (ts, name, chat),
                    )
                con.execute(
                    "INSERT OR REPLACE INTO messages(id,chat_jid,sender,sender_name,from_me,ts,text,kind) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (getattr(info, "ID", f"{chat}-{ts}"), chat, sender, push, from_me, ts, text, kind),
                )
            con.close()
        except Exception as e:  # never kill the event loop
            self.error = f"ingest error: {e}"

    # ---- lifecycle ---- #
    def start(self, phone: Optional[str] = None):
        if self.thread and self.thread.is_alive():
            return
        from neonize.client import NewClient
        from neonize.events import ConnectedEv, DisconnectedEv, HistorySyncEv, MessageEv

        session_db = str(_user_dir(self.user_id) / "session.sqlite3")
        self.client = NewClient(session_db)
        client = self.client

        @client.event(ConnectedEv)
        def _on_connected(_c, _ev):
            self.connected = True
            self.pair_code = None

        @client.event(DisconnectedEv)
        def _on_disconnected(_c, _ev):
            self.connected = False

        @client.event(MessageEv)
        def _on_message(_c, ev):
            self._store(ev.Info, ev.Message)

        @client.event(HistorySyncEv)
        def _on_history(_c, ev):
            # Initial history push after linking: ingest every conversation we are given.
            try:
                for conv in ev.Data.conversations:
                    cid = getattr(conv, "ID", "") or getattr(conv, "id", "")
                    cname = getattr(conv, "name", "") or getattr(conv, "displayName", "")
                    if cid:
                        con = _db(self.user_id)
                        with con:
                            con.execute(
                                "INSERT INTO chats(jid,name,is_group,last_ts) VALUES(?,?,?,0) "
                                "ON CONFLICT(jid) DO UPDATE SET name=COALESCE(NULLIF(?,''),name)",
                                (cid, cname or cid.split("@")[0], 1 if cid.endswith("@g.us") else 0, cname),
                            )
                            for hm in getattr(conv, "messages", []):
                                wmi = hm.message
                                key = wmi.key
                                text, kind = self._extract(wmi.message)
                                if not text and kind == "other":
                                    continue
                                ts = int(getattr(wmi, "messageTimestamp", 0) or 0)
                                sender = getattr(key, "participant", "") or cid
                                con.execute(
                                    "INSERT OR IGNORE INTO messages(id,chat_jid,sender,sender_name,from_me,ts,text,kind) "
                                    "VALUES(?,?,?,?,?,?,?,?)",
                                    (key.ID, cid, sender, getattr(wmi, "pushName", "") or "",
                                     1 if key.fromMe else 0, ts, text, kind),
                                )
                                con.execute("UPDATE chats SET last_ts=MAX(last_ts,?) WHERE jid=?", (ts, cid))
                        con.close()
            except Exception as e:
                self.error = f"history sync error: {e}"

        @client.event.qr
        def _on_qr(_c, data_qr: bytes):
            try:
                import segno

                path = _user_dir(self.user_id) / "login-qr.png"
                segno.make_qr(data_qr.decode()).save(str(path), scale=8)
                self.last_qr_path = str(path)
            except Exception as e:
                self.error = f"qr error: {e}"

        def _run():
            try:
                if phone:
                    self.pair_code = client.PairPhone(phone, show_push_notification=True)
                client.connect()  # blocks
            except Exception as e:
                self.error = str(e)
                self.connected = False

        self.thread = threading.Thread(target=_run, daemon=True, name=f"wa-{self.user_id}")
        self.thread.start()

    def logout(self):
        try:
            if self.client:
                self.client.logout()
        finally:
            self.connected = False


_sessions: dict[str, Session] = {}
_sessions_lock = threading.Lock()


def _session(user_id: str) -> Session:
    _user_dir(user_id)  # validates user_id
    with _sessions_lock:
        if user_id not in _sessions:
            _sessions[user_id] = Session(user_id)
        return _sessions[user_id]


# --------------------------------------------------------------------------- #
# Query helpers
# --------------------------------------------------------------------------- #
def _resolve_chat(con: sqlite3.Connection, chat: str):
    """chat may be a JID, a phone number, or part of a name. Returns list of rows."""
    rows = con.execute("SELECT * FROM chats WHERE jid=?", (chat,)).fetchall()
    if rows:
        return rows
    digits = re.sub(r"\D", "", chat)
    if len(digits) >= 7:
        rows = con.execute("SELECT * FROM chats WHERE jid LIKE ?", (f"{digits}@%",)).fetchall()
        if rows:
            return rows
    return con.execute(
        "SELECT * FROM chats WHERE name LIKE ? COLLATE NOCASE ORDER BY last_ts DESC", (f"%{chat}%",)
    ).fetchall()


def _format_messages(rows) -> str:
    out, current_chat = [], None
    for r in rows:
        if r["chat_jid"] != current_chat:
            current_chat = r["chat_jid"]
            out.append(f"\n=== {r['chat_name'] or current_chat} ({current_chat}) ===")
        who = "me" if r["from_me"] else (r["sender_name"] or r["sender"] or "?")
        tag = "" if r["kind"] == "text" else f"[{r['kind']}] "
        out.append(f"[{_fmt_ts(r['ts'])}] {who}: {tag}{r['text']}")
    return "\n".join(out).strip()


# --------------------------------------------------------------------------- #
# MCP tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def login_user(user_id: str, phone: Optional[str] = None) -> str:
    """Start (or resume) a WhatsApp session for user_id.
    First time: returns the path of a QR image to scan (WhatsApp > Linked devices),
    or, if `phone` (e.g. +919876543210) is given, an 8-char pairing code to type on the phone."""
    s = _session(user_id)
    s.start(phone=phone)
    for _ in range(20):  # wait up to ~10s for a QR / pair code / connection
        if s.connected or s.last_qr_path or s.pair_code or s.error:
            break
        time.sleep(0.5)
    if s.connected:
        return f"user '{user_id}' is connected."
    if s.pair_code:
        return f"Enter this pairing code on your phone (Linked devices > Link with phone number): {s.pair_code}"
    if s.last_qr_path:
        return f"Scan the QR image at {s.last_qr_path} (refreshes every ~20s). Then call whatsapp_status."
    return f"Session starting for '{user_id}'. {('Error: ' + s.error) if s.error else 'Call whatsapp_status shortly.'}"


@mcp.tool()
def logout_user(user_id: str) -> str:
    """Unlink this user's device. The local archive is kept."""
    _session(user_id).logout()
    return f"user '{user_id}' logged out (archive kept)."


@mcp.tool()
def list_users() -> list[dict]:
    """List all user_ids that have a local archive/session and whether each is connected."""
    users = []
    for d in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
        s = _sessions.get(d.name)
        users.append({"user_id": d.name, "connected": bool(s and s.connected)})
    return users


@mcp.tool()
def whatsapp_status(user_id: str) -> dict:
    """Connection state, archive size and time range for a user."""
    s = _session(user_id)
    con = _db(user_id)
    n_chats = con.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
    n_msgs, lo, hi = con.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM messages").fetchone()
    con.close()
    return {
        "user_id": user_id,
        "connected": s.connected,
        "chats": n_chats,
        "messages": n_msgs,
        "oldest": _fmt_ts(lo) if lo else None,
        "newest": _fmt_ts(hi) if hi else None,
        "last_error": s.error,
    }


@mcp.tool()
def list_chats(user_id: str, query: Optional[str] = None, only_groups: Optional[bool] = None,
               limit: int = 50) -> list[dict]:
    """List a user's chats by recent activity. Optional name filter and group/direct filter."""
    con = _db(user_id)
    sql = ("SELECT c.jid, c.name, c.is_group, c.last_ts, "
           "(SELECT text FROM messages m WHERE m.chat_jid=c.jid ORDER BY ts DESC LIMIT 1) AS preview "
           "FROM chats c WHERE 1=1")
    args: list = []
    if query:
        sql += " AND (c.name LIKE ? COLLATE NOCASE OR c.jid LIKE ?)"
        args += [f"%{query}%", f"%{query}%"]
    if only_groups is not None:
        sql += " AND c.is_group=?"
        args.append(1 if only_groups else 0)
    sql += " ORDER BY c.last_ts DESC LIMIT ?"
    args.append(limit)
    rows = con.execute(sql, args).fetchall()
    con.close()
    return [{"jid": r["jid"], "name": r["name"], "type": "group" if r["is_group"] else "direct",
             "last_activity": _fmt_ts(r["last_ts"]) if r["last_ts"] else None,
             "preview": (r["preview"] or "")[:80]} for r in rows]


@mcp.tool()
def get_messages(user_id: str, chat_name: Optional[str] = None, days: Optional[int] = None,
                 limit: Optional[int] = None) -> str:
    """Fetch messages for a user.

    - chat_name: name / phone / JID of ONE chat. Omit to load ALL chats.
    - days: only messages from the last N days (e.g. 2). Omit to load everything archived.
    - limit: optional cap on number of messages (newest kept) to protect context size.
    """
    con = _db(user_id)
    where, args = [], []

    if chat_name:
        matches = _resolve_chat(con, chat_name)
        if not matches:
            con.close()
            return f"No chat matching '{chat_name}'. Use list_chats to see available chats."
        if len(matches) > 1 and not any(m["name"] and m["name"].lower() == chat_name.lower() for m in matches):
            cands = "\n".join(f"- {m['name']} ({m['jid']})" for m in matches[:15])
            con.close()
            return f"'{chat_name}' matches several chats; pass a more specific name or a JID:\n{cands}"
        exact = [m for m in matches if m["name"] and m["name"].lower() == chat_name.lower()]
        chosen = exact[0] if exact else matches[0]
        where.append("m.chat_jid = ?")
        args.append(chosen["jid"])

    if days is not None:
        if days < 0:
            con.close()
            return "days must be >= 0"
        where.append("m.ts >= ?")
        args.append(int(time.time()) - days * 86400)

    sql = ("SELECT m.*, c.name AS chat_name FROM messages m LEFT JOIN chats c ON c.jid=m.chat_jid")
    if where:
        sql += " WHERE " + " AND ".join(where)
    if limit:
        sql = f"SELECT * FROM ({sql} ORDER BY m.ts DESC LIMIT ?) ORDER BY chat_jid, ts"
        args.append(limit)
    else:
        sql += " ORDER BY m.chat_jid, m.ts"
    rows = con.execute(sql, args).fetchall()
    con.close()

    if not rows:
        return "No messages found for the given filters."
    scope = f"chat '{chat_name}'" if chat_name else "all chats"
    span = f"last {days} day(s)" if days is not None else "all time"
    return f"{len(rows)} messages from {scope}, {span}:\n" + _format_messages(rows)


@mcp.tool()
def search_messages(user_id: str, query: str, chat_name: Optional[str] = None,
                    days: Optional[int] = None, limit: int = 100) -> str:
    """Substring search over message text/captions. Optional chat_name and days filters."""
    con = _db(user_id)
    where, args = ["m.text LIKE ? COLLATE NOCASE"], [f"%{query}%"]
    if chat_name:
        matches = _resolve_chat(con, chat_name)
        if not matches:
            con.close()
            return f"No chat matching '{chat_name}'."
        where.append("m.chat_jid = ?")
        args.append(matches[0]["jid"])
    if days is not None:
        where.append("m.ts >= ?")
        args.append(int(time.time()) - days * 86400)
    rows = con.execute(
        "SELECT m.*, c.name AS chat_name FROM messages m LEFT JOIN chats c ON c.jid=m.chat_jid "
        f"WHERE {' AND '.join(where)} ORDER BY m.ts DESC LIMIT ?", args + [limit]).fetchall()
    con.close()
    return _format_messages(sorted(rows, key=lambda r: (r["chat_jid"], r["ts"]))) or "No matches."


@mcp.tool()
def get_message_context(user_id: str, chat_name: str, message_id: str, around: int = 5) -> str:
    """A message plus `around` messages before and after it in the same chat."""
    con = _db(user_id)
    matches = _resolve_chat(con, chat_name)
    if not matches:
        con.close()
        return f"No chat matching '{chat_name}'."
    jid = matches[0]["jid"]
    row = con.execute("SELECT ts FROM messages WHERE id=? AND chat_jid=?", (message_id, jid)).fetchone()
    if not row:
        con.close()
        return "Message not found."
    ts = row["ts"]
    before = con.execute("SELECT m.*, c.name AS chat_name FROM messages m LEFT JOIN chats c ON c.jid=m.chat_jid "
                         "WHERE m.chat_jid=? AND m.ts<=? ORDER BY m.ts DESC LIMIT ?", (jid, ts, around + 1)).fetchall()
    after = con.execute("SELECT m.*, c.name AS chat_name FROM messages m LEFT JOIN chats c ON c.jid=m.chat_jid "
                        "WHERE m.chat_jid=? AND m.ts>? ORDER BY m.ts ASC LIMIT ?", (jid, ts, around)).fetchall()
    con.close()
    return _format_messages(list(reversed(before)) + list(after))


# --------------------------------------------------------------------------- #
# Resources
# --------------------------------------------------------------------------- #
@mcp.resource("whatsapp://{user_id}/chats")
def chats_resource(user_id: str) -> str:
    rows = list_chats(user_id, limit=100)
    return "\n".join(f"- {r['name']} ({r['jid']}) — {r['type']}, last {r['last_activity']}" for r in rows)


@mcp.resource("whatsapp://{user_id}/chat/{chat}")
def chat_resource(user_id: str, chat: str) -> str:
    return get_messages(user_id, chat_name=chat, limit=200)


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()

    # Auto-resume sessions that were already linked before.
    for d in DATA_DIR.iterdir():
        if d.is_dir() and (d / "session.sqlite3").exists():
            try:
                _session(d.name).start()
            except Exception:
                pass

    if a.transport == "http":
        mcp.settings.host, mcp.settings.port = a.host, a.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()