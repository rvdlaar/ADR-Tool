"""
SQLite-backed user store for ADR Tool API.
Replaces the in-memory MOCK_USERS_DB with persistent storage.
Passwords are hashed with bcrypt.
"""
import os
import sqlite3
import threading
from typing import Optional, Dict, Any, List

import bcrypt

# Database path - configurable via env var
_DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "users.db"
)
DB_PATH = os.getenv("USER_DB_PATH", _DEFAULT_DB)

_local = threading.local()


def _get_connection() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        db_dir = os.path.dirname(os.path.abspath(DB_PATH))
        os.makedirs(db_dir, exist_ok=True)
        _local.conn = sqlite3.connect(os.path.abspath(DB_PATH))
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db() -> None:
    """Initialize the users table and seed default users if empty."""
    conn = _get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            full_name TEXT,
            password_hash TEXT NOT NULL,
            scopes TEXT NOT NULL DEFAULT 'adr:read',
            disabled INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()

    cursor = conn.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    if count == 0:
        _seed_default_users(conn)


def _seed_default_users(conn: sqlite3.Connection) -> None:
    """
    Seed default users with unique, strong bcrypt hashes.

    Default credentials (change in production):
      admin  / Adm1nStr0ng2024
      user   / Us3rSecure2024
      reader / R3ad0nlySafe2024
    """
    seed_users = [
        {
            "username": "admin",
            "email": "admin@adr-tool.local",
            "full_name": "ADR Admin",
            "password": "Adm1nStr0ng2024",
            "scopes": "adr:read,adr:write,adr:delete,admin:users,admin:settings",
        },
        {
            "username": "user",
            "email": "user@adr-tool.local",
            "full_name": "ADR User",
            "password": "Us3rSecure2024",
            "scopes": "adr:read,adr:write",
        },
        {
            "username": "reader",
            "email": "reader@adr-tool.local",
            "full_name": "ADR Reader",
            "password": "R3ad0nlySafe2024",
            "scopes": "adr:read",
        },
    ]
    for u in seed_users:
        pw_hash = bcrypt.hashpw(
            u["password"].encode("utf-8"), bcrypt.gensalt(12)
        ).decode("utf-8")
        conn.execute(
            "INSERT INTO users (username, email, full_name, password_hash, scopes, disabled) VALUES (?, ?, ?, ?, ?, 0)",
            (u["username"], u["email"], u["full_name"], pw_hash, u["scopes"]),
        )
    conn.commit()


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Fetch a user by username. Returns None if not found."""
    conn = _get_connection()
    cursor = conn.execute(
        "SELECT id, username, email, full_name, password_hash, scopes, disabled FROM users WHERE username = ?",
        (username,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "id": str(row["id"]),
        "username": row["username"],
        "email": row["email"],
        "full_name": row["full_name"],
        "password_hash": row["password_hash"],
        "scopes": row["scopes"].split(","),
        "disabled": bool(row["disabled"]),
    }


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate a user with username and password.
    Uses bcrypt for secure password verification.
    Returns user dict if authentication succeeds, None otherwise.
    """
    user = get_user_by_username(username)
    if user is None:
        return None
    if user.get("disabled", False):
        return None
    try:
        if not bcrypt.checkpw(
            password.encode("utf-8"), user["password_hash"].encode("utf-8")
        ):
            return None
    except Exception:
        return None
    return user


def create_user(
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    scopes: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Create a new user with bcrypt-hashed password."""
    conn = _get_connection()
    pw_hash = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(12)
    ).decode("utf-8")
    scope_str = ",".join(scopes) if scopes else "adr:read"
    conn.execute(
        "INSERT INTO users (username, email, full_name, password_hash, scopes, disabled) VALUES (?, ?, ?, ?, ?, 0)",
        (username, email, full_name, pw_hash, scope_str),
    )
    conn.commit()
    return get_user_by_username(username)


def list_users() -> List[Dict[str, Any]]:
    """List all users (without password hashes)."""
    conn = _get_connection()
    cursor = conn.execute(
        "SELECT id, username, email, full_name, scopes, disabled FROM users"
    )
    return [
        {
            "id": str(r["id"]),
            "username": r["username"],
            "email": r["email"],
            "full_name": r["full_name"],
            "scopes": r["scopes"].split(","),
            "disabled": bool(r["disabled"]),
        }
        for r in cursor.fetchall()
    ]


# Initialize the database on import
init_db()
