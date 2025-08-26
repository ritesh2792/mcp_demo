from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import List, Dict, Any
import uuid
from datetime import datetime

DB_PATH = Path("users.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS gcp_users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Ensure table exists
with get_conn() as conn:
    conn.execute(SCHEMA)
    conn.commit()


def add_user(name: str, email: str, role: str) -> Dict[str, Any]:
    user_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO gcp_users (id, name, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, name.strip(), email.strip().lower(), role.strip()),
        )
        conn.commit()
    return {
        "id": user_id,
        "name": name,
        "email": email.strip().lower(),
        "role": role,
        "created_at": created_at,
    }


def list_users() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, name, email, role, created_at FROM gcp_users ORDER BY datetime(created_at) DESC").fetchall()
    return [dict(r) for r in rows]
