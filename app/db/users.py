"""
SQLite-backed user store for ADR Tool API.
Replaces the in-memory MOCK_USERS_DB with persistent storage.
"""
import os
import sqlite3
from contextlib import contextmanager
from typing import Optional

import bcrypt

# Database path - configurable via env, defaults to app directory
DB_PATH = os.getenv("USER_DB_PATH", os.path.join(os.path.dirname(__file__), "users.db"))


@contextmanager
def get_db():
    """Get a database connection with WAL mode for concurrent reads."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the user database schema and seed default users."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                disabled INTEGER DEFAULT 0,
                scopes TEXT NOT NULL DEFAULT 'adr:read',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Seed default users if table is empty
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            _seed_default_users(conn)


def _seed_default_users(conn: sqlite3.Connection):
    """Seed default users with unique bcrypt hashes."""
    default_users = [
        {
            "username": "admin",
            "email": "admin@adr-tool.local",
            "password": "password123",
            "full_name": "Admin User",
            "scopes": "adr:read,adr:write,adr:delete,admin:users,admin:settings",
        },
        {
            "username": "user",
            "email": "user@adr-tool.local",
            "password": "password123",
            "full_name": "Regular User",
            "scopes": "adr:read,adr:write",
        },
        {
            "username": "reader",
            "email": "reader@adr-tool.local",
            "password": "password123",
            "full_name": "Read-Only User",
            "scopes": "adr:read",
        },
    ]

    for user in default_users:
        # Each user gets a unique bcrypt hash (different salt)
        password_hash = bcrypt.hashpw(
            user["password"].encode("utf-8"),
            bcrypt.gensalt(rounds=12)
        ).decode("utf-8")

        conn.execute(
            """INSERT INTO users (username, email, password_hash, full_name, scopes)
               VALUES (?, ?, ?, ?, ?)""",
            (user["username"], user["email"], password_hash, user["full_name"], user["scopes"]),
        )


def get_user_by_username(username: str) -> Optional[dict]:
    """Look up a user by username. Returns dict or None."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND disabled = 0",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "password_hash": row["password_hash"],
            "full_name": row["full_name"],
            "disabled": bool(row["disabled"]),
            "scopes": row["scopes"].split(","),
        }


def verify_user_password(username: str, password: str) -> Optional[dict]:
    """Authenticate a user by username and password. Returns user dict or None."""
    user = get_user_by_username(username)
    if user is None:
        return None

    if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        return None

    return user


def create_user(username: str, email: str, password: str, scopes: str = "adr:read", full_name: str = "") -> dict:
    """Create a new user. Raises sqlite3.IntegrityError if username exists."""
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=12)
    ).decode("utf-8")

    with get_db() as conn:
        conn.execute(
            """INSERT INTO users (username, email, password_hash, full_name, scopes)
               VALUES (?, ?, ?, ?, ?)""",
            (username, email, password_hash, full_name, scopes),
        )
    return get_user_by_username(username)


# Initialize database on import
init_db()
