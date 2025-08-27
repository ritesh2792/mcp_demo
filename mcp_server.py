# mcp_server.py
import sys
import json
import sqlite3
from datetime import datetime

DB = "gcp_users.db"

# -----------------------------
# DB INIT
# -----------------------------
def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    # TEXT id so we can store short IDs like U001
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

# -----------------------------
# ID GENERATION: U001, U002, ...
# -----------------------------
def next_user_id(cur) -> str:
    """
    Find the maximum numeric part of IDs that look like 'U<digits>'
    and return the next one, zero-padded to 3 digits (U001, U002, ...).
    If none found, start at U001.
    """
    cur.execute("""
        SELECT id
        FROM gcp_users
        WHERE id GLOB 'U[0-9]*'
        ORDER BY CAST(substr(id, 2) AS INTEGER) DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        return "U001"
    last_id = row[0]  # e.g. "U007"
    try:
        n = int(last_id[1:]) + 1
    except Exception:
        n = 1
    return f"U{n:03d}"

# -----------------------------
# HANDLERS
# -----------------------------
def handle_add_user(params):
    name = (params.get("name") or "").strip()
    email = (params.get("email") or "").strip().lower()
    role = (params.get("role") or "").strip()
    if not (name and email and role):
        return {"error": "name, email and role are required"}

    created_at = datetime.utcnow().isoformat() + "Z"
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    try:
        # Generate short ID like U001, U002...
        user_id = next_user_id(cur)
        cur.execute(
            "INSERT INTO gcp_users (id, name, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, email, role, created_at)
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.close()
        return {"error": f"DB insert error (likely duplicate email): {e}"}
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
    cur.execute("""
        SELECT id, name, email, role, created_at
        FROM gcp_users
        ORDER BY CAST(substr(id, 2) AS INTEGER) ASC
    """)
    rows = cur.fetchall()
    conn.close()
    users = [
        {"id": r[0], "name": r[1], "email": r[2], "role": r[3], "created_at": r[4]}
        for r in rows
    ]
    return {"result": {"users": users}}

def handle_get_user(params):
    uid = (params.get("id") or "").strip()
    if not uid:
        return {"error": "id is required"}

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, role, created_at FROM gcp_users WHERE id = ?", (uid,))
    row = cur.fetchone()
    conn.close()

    if not row:
        # Return empty result; client can show "No user found."
        return {"result": {}}

    user = {"id": row[0], "name": row[1], "email": row[2], "role": row[3], "created_at": row[4]}
    return {"result": {"user": user}}

def handle_update_user(params):
    user_id = (params.get("id") or "").strip()
    name = (params.get("name") or "").strip()
    email = (params.get("email") or "").strip()
    role = (params.get("role") or "").strip()

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
    except sqlite3.IntegrityError as e:
        conn.close()
        return {"error": f"DB update error (likely duplicate email): {e}"}
    except Exception as e:
        conn.close()
        return {"error": f"DB update error: {e}"}
    conn.close()
    return {"result": {"message": "User updated successfully"}}

def handle_delete_user(params):
    user_id = (params.get("id") or "").strip()
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

# -------------------------------------------------
# Example New Tool (kept commented for live demo)
# -------------------------------------------------
def handle_send_email(params):
    """
    Demo email sender.
    In reality you'd integrate with SMTP or Gmail API here.
    """
    to = (params.get("to") or "").strip()
    subject = (params.get("subject") or "").strip()
    body = (params.get("body") or "").strip()
    if not (to and subject and body):
        return {"error": "to, subject and body are required"}
    # Pretend email sent
    return {
        "result": {
            "message": f"Email successfully sent to {to}",
            "subject": subject,
            "preview": body[:50] + ("..." if len(body) > 50 else "")
        }
    }

# -----------------------------
# TOOL DISCOVERY
# -----------------------------
def handle_list_tools(_params):
    tools = [
        {
            "name": "add_user",
            "description": "Add a new GCP user",
            "required": ["name", "email", "role"],
            "params_schema": {
                "name":  {"type": "string", "description": "Full name"},
                "email": {"type": "string", "description": "Email (unique)"},
                "role":  {"type": "string", "description": "Role e.g. viewer, editor, admin"},
            },
        },
        {
            "name": "list_users",
            "description": "List all users",
            "required": [],
            "params_schema": {},
        },
        {
            "name": "get_user",
            "description": "Get a single user by short ID (e.g., U001)",
            "required": ["id"],
            "params_schema": {
                "id": {"type": "string", "description": "Short user ID like U001"},
            },
        },
        {
            "name": "update_user",
            "description": "Update fields for an existing user by short ID",
            "required": ["id"],  # id required; others optional
            "params_schema": {
                "id":    {"type": "string", "description": "Short user ID like U001"},
                "name":  {"type": "string", "description": "New name (optional)"},
                "email": {"type": "string", "description": "New email (optional)"},
                "role":  {"type": "string", "description": "New role (optional)"},
            },
        },
        {
            "name": "delete_user",
            "description": "Delete user by short ID",
            "required": ["id"],
            "params_schema": {
                "id": {"type": "string", "description": "Short user ID like U001"},
            },
        },
        # -------------------------------------
        # Example new tool (uncomment to enable)
        {
            "name": "send_email",
            "description": "Send an email to a user (demo)",
            "required": ["to", "subject", "body"],
            "params_schema": {
                "to": {"type": "string", "description": "Recipient email"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body"},
            },
        },
        # -------------------------------------
    ]
    return {"result": {"tools": tools}}

# -----------------------------
# MAIN LOOP (STDIO)
# -----------------------------
def main_loop():
    init_db()
    # Clear statement: STDIO (no TCP host/port)
    sys.stderr.write("[MCP SERVER] Started and ready — transport=STDIO (no host/port)\n")
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
        params = req.get("params", {}) or {}

        if method == "add_user":
            resp = handle_add_user(params)
        elif method == "list_users":
            resp = handle_list_users(params)
        elif method == "get_user":
            resp = handle_get_user(params)
        elif method == "update_user":
            resp = handle_update_user(params)
        elif method == "delete_user":
            resp = handle_delete_user(params)
        elif method == "list_tools":
            resp = handle_list_tools(params)
        elif method == "send_email":
            resp = handle_send_email(params)  # <— uncomment for demo
        elif method == "ping":
            resp = {"result": {"ok": True}}
        else:
            resp = {"error": f"unknown method: {method}"}

        send_response({"id": req.get("id"), "method": method, **resp})

if __name__ == "__main__":
    main_loop()
