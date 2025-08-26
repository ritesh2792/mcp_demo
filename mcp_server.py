import sys
import json
import sqlite3
import uuid
from datetime import datetime

DB = "gcp_users.db"

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS gcp_users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def send_response(resp_obj):
    sys.stdout.write(json.dumps(resp_obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle_add_user(params):
    name = params.get("name", "").strip()
    email = params.get("email", "").strip().lower()
    role = params.get("role", "").strip()
    if not (name and email and role):
        return {"error": "name, email and role are required"}
    user_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat() + "Z"
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO gcp_users (id, name, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, email, role, created_at)
        )
        conn.commit()
    except Exception as e:
        conn.close()
        return {"error": f"DB insert error: {e}"}
    conn.close()
    return {
        "result": {
            "id": user_id,
            "name": name,
            "email": email,
            "role": role,
            "created_at": created_at
        }
    }


def handle_list_users(_params):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, role, created_at FROM gcp_users ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    users = [
        {"id": r[0], "name": r[1], "email": r[2], "role": r[3], "created_at": r[4]}
        for r in rows
    ]
    return {"result": {"users": users}}


def handle_update_user(params):
    user_id = params.get("id", "").strip()
    name = params.get("name", "").strip()
    email = params.get("email", "").strip()
    role = params.get("role", "").strip()

    if not user_id:
        return {"error": "id is required"}
    if not (name or email or role):
        return {"error": "At least one field (name/email/role) is required to update"}

    fields = []
    values = []
    if name:
        fields.append("name = ?")
        values.append(name)
    if email:
        fields.append("email = ?")
        values.append(email)
    if role:
        fields.append("role = ?")
        values.append(role)

    values.append(user_id)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    try:
        cur.execute(f"UPDATE gcp_users SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        if cur.rowcount == 0:
            return {"error": "No user found with this ID"}
    except Exception as e:
        conn.close()
        return {"error": f"DB update error: {e}"}
    conn.close()
    return {"result": {"message": "User updated successfully"}}


def handle_delete_user(params):
    user_id = params.get("id", "").strip()
    if not user_id:
        return {"error": "id is required"}
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM gcp_users WHERE id = ?", (user_id,))
        conn.commit()
        if cur.rowcount == 0:
            return {"error": "No user found with this ID"}
    except Exception as e:
        conn.close()
        return {"error": f"DB delete error: {e}"}
    conn.close()
    return {"result": {"message": "User deleted successfully"}}

def main_loop():
    init_db()
    sys.stderr.write("[MCP SERVER] Started and ready\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            send_response({"error": f"invalid json: {e}"})
            continue

        method = req.get("method")
        params = req.get("params", {})

        if method == "add_user":
            resp = handle_add_user(params)
        elif method == "list_users":
            resp = handle_list_users(params)
        elif method == "update_user":
            resp = handle_update_user(params)
        elif method == "delete_user":
            resp = handle_delete_user(params)
        elif method == "ping":
            resp = {"result": {"ok": True}}
        else:
            resp = {"error": f"unknown method: {method}"}

        send_response({"id": req.get("id"), "method": method, **resp})

if __name__ == "__main__":
    main_loop()
