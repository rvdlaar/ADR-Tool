"""SQLite persistence for ingested document metadata."""
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path

DB_DIR = Path("data")
DB_PATH = DB_DIR / "adrs.db"


def _get_conn():
    DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            original_filename TEXT,
            file_path TEXT,
            file_size INTEGER DEFAULT 0,
            content_type TEXT,
            file_hash TEXT,
            metadata TEXT DEFAULT '{}',
            source TEXT DEFAULT 'api',
            ingested_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_docs_filename ON documents(filename);
        CREATE INDEX IF NOT EXISTS idx_docs_ingested ON documents(ingested_at);
    """)
    conn.close()


def create_document(doc_id=None, filename="", original_filename=None, file_path=None,
                    file_size=0, content_type=None, file_hash=None,
                    metadata=None, source="api"):
    conn = _get_conn()
    if not doc_id:
        doc_id = str(uuid.uuid4())[:12]
    conn.execute(
        """INSERT INTO documents (id, filename, original_filename, file_path,
           file_size, content_type, file_hash, metadata, source)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (doc_id, filename, original_filename or filename, file_path,
         file_size, content_type, file_hash,
         json.dumps(metadata or {}), source)
    )
    conn.commit()
    doc = get_document(doc_id, _conn=conn)
    conn.close()
    return doc


def get_document(doc_id, _conn=None):
    close = _conn is None
    conn = _conn or _get_conn()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if close:
        conn.close()
    if not row:
        return None
    return _row_to_dict(row)


def list_documents(limit=50, offset=0):
    conn = _get_conn()
    count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM documents ORDER BY ingested_at DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows], count


def delete_document(doc_id):
    conn = _get_conn()
    result = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    deleted = result.rowcount > 0
    conn.close()
    return deleted


def _row_to_dict(row):
    d = dict(row)
    try:
        d["metadata"] = json.loads(d.get("metadata", "{}"))
    except (json.JSONDecodeError, TypeError):
        d["metadata"] = {}
    return d


init_db()
