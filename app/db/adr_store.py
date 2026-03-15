"""SQLite persistence for ADRs — replaces in-memory _adrs_db dict."""
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
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS adrs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'Proposed',
            y_statement TEXT,
            context TEXT,
            decision_drivers TEXT,
            decision TEXT,
            alternatives_considered TEXT,
            consequences TEXT,
            impact TEXT,
            reversibility TEXT,
            related_decisions TEXT,
            author TEXT,
            tags TEXT DEFAULT '[]',
            ai_generated INTEGER DEFAULT 0,
            ai_model TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_adrs_status ON adrs(status);
        CREATE INDEX IF NOT EXISTS idx_adrs_author ON adrs(author);
        CREATE INDEX IF NOT EXISTS idx_adrs_created ON adrs(created_at);
    """)
    conn.close()


def create_adr(title, context, decision, consequences, author=None,
               tags=None, ai_generated=False, ai_model=None,
               y_statement=None, decision_drivers=None, alternatives_considered=None,
               impact=None, reversibility=None, related_decisions=None):
    conn = _get_conn()
    adr_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()
    conn.execute(
        """INSERT INTO adrs (id, title, status, y_statement, context, decision_drivers,
           decision, alternatives_considered, consequences, impact, reversibility,
           related_decisions, author, tags, ai_generated, ai_model, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (adr_id, title, "Proposed", y_statement, context, decision_drivers,
         decision, alternatives_considered, consequences, impact, reversibility,
         related_decisions, author, json.dumps(tags or []), int(ai_generated), ai_model, now, now)
    )
    conn.commit()
    adr = get_adr(adr_id, _conn=conn)
    conn.close()
    return adr


def get_next_number():
    """Get the next ADR number for sequential numbering."""
    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) FROM adrs").fetchone()[0]
    conn.close()
    return total + 1


def get_adr(adr_id, _conn=None):
    close = _conn is None
    conn = _conn or _get_conn()
    row = conn.execute("SELECT * FROM adrs WHERE id = ?", (adr_id,)).fetchone()
    if close:
        conn.close()
    return _row_to_dict(row) if row else None


def list_adrs(limit=20, offset=0, status=None, author=None, search=None, tags=None):
    conn = _get_conn()
    sql = "SELECT * FROM adrs WHERE 1=1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if author:
        sql += " AND author LIKE ?"
        params.append(f"%{author}%")
    if search:
        sql += " AND (title LIKE ? OR context LIKE ? OR decision LIKE ?)"
        params.extend([f"%{search}%"] * 3)
    if tags:
        for tag in tags:
            sql += " AND tags LIKE ?"
            params.append(f'%"{tag}"%')

    count_sql = sql.replace("SELECT *", "SELECT COUNT(*)", 1)
    count = conn.execute(count_sql, params).fetchone()[0]

    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows], count


def update_adr(adr_id, **fields):
    conn = _get_conn()
    if "tags" in fields and isinstance(fields["tags"], list):
        fields["tags"] = json.dumps(fields["tags"])
    fields["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [adr_id]
    conn.execute(f"UPDATE adrs SET {set_clause} WHERE id = ?", values)
    conn.commit()
    adr = get_adr(adr_id, _conn=conn)
    conn.close()
    return adr


def delete_adr(adr_id):
    conn = _get_conn()
    result = conn.execute("DELETE FROM adrs WHERE id = ?", (adr_id,))
    conn.commit()
    deleted = result.rowcount > 0
    conn.close()
    return deleted


def get_stats():
    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) FROM adrs").fetchone()[0]
    rows = conn.execute("SELECT status, COUNT(*) as cnt FROM adrs GROUP BY status").fetchall()
    by_status = {r["status"]: r["cnt"] for r in rows}
    ai_count = conn.execute("SELECT COUNT(*) FROM adrs WHERE ai_generated = 1").fetchone()[0]
    conn.close()
    return {"total": total, "by_status": by_status, "ai_generated": ai_count}


def _row_to_dict(row):
    d = dict(row)
    d["ai_generated"] = bool(d.get("ai_generated", 0))
    try:
        d["tags"] = json.loads(d.get("tags", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    return d


init_db()
