# app.py
import os
import sqlite3
import streamlit as st
import subprocess
import time
import json
from dotenv import load_dotenv
from langchain.chat_models import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

load_dotenv()

# =========================
# CONFIGURATION
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("OPENAI_API_KEY not set in environment")
    st.stop()
print("[INIT] Loaded OPENAI_API_KEY.")

# LangChain Chat Model
llm = ChatOpenAI(
    model_name="gpt-4.1-nano-2025-04-14",
    temperature=0,
    openai_api_key=OPENAI_API_KEY,
)
print("[INIT] LangChain ChatOpenAI client initialized.")

DB_NAME = "gcp_users.db"

# =========================
# START MCP SERVER SUBPROCESS
# =========================
MCP_CMD = ["python", "mcp_server.py"]

def start_mcp_server():
    print("[MCP] Starting MCP server subprocess...")
    proc = subprocess.Popen(
        MCP_CMD,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    time.sleep(0.5)
    print("[MCP] MCP server started and ready.")
    return proc

if "mcp_process" not in st.session_state:
    st.session_state.mcp_process = start_mcp_server()

mcp_proc = st.session_state.mcp_process

def call_mcp(method, params=None):
    """
    Send a JSON request to MCP server and wait for response.
    """
    print(f"[MCP] Sending request: {method} {params}")
    if mcp_proc.poll() is not None:
        return {"error": "MCP server not running"}
    req = {"id": str(time.time()), "method": method, "params": params or {}}
    mcp_proc.stdin.write(json.dumps(req) + "\n")
    mcp_proc.stdin.flush()
    resp_line = mcp_proc.stdout.readline()
    if not resp_line:
        return {"error": "No response from MCP server"}
    try:
        resp = json.loads(resp_line)
        print(f"[MCP] Response: {resp}")
        return resp
    except Exception as e:
        return {"error": f"Invalid JSON from MCP: {resp_line}, error={e}"}

# =========================
# GPT / LangChain INTERPRETATION
# =========================
def interpret_query_with_llm(query: str) -> str:
    print(f"[LLM] Interpreting query: {query}")
    system_prompt = """
    You are an assistant that interprets user queries for managing GCP users.
    Actions available: ADD (add user), UPDATE (update user details), DELETE (delete user), VIEW (view users)
    Return exactly one word in uppercase: ADD, UPDATE, DELETE, VIEW.
    """
    response = llm([SystemMessage(content=system_prompt), HumanMessage(content=query)])
    action = response.content.strip().upper()
    print(f"[LLM] Action detected: {action}")
    return action

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(page_title="GCP User Management", layout="wide")

# Centered page heading
st.markdown(
    "<h1 style='text-align: center; color: #333; font-size: 32px;'>GCP User Management</h1>",
    unsafe_allow_html=True
)

# ======= Sidebar Chat Box =======
st.sidebar.markdown("### Chat Box")
user_query = st.sidebar.text_input("Enter your query (e.g., 'I want to add a new GCP user')")
if st.sidebar.button("Submit Query") and user_query.strip():
    print(f"[INPUT] User asked: {user_query}")
    action = interpret_query_with_llm(user_query)
    st.session_state['action'] = action
    st.session_state['query_done'] = True

# ======= Main Area =======
st.markdown("<h3 style='text-align: center; color: #111; font-size: 22px;'>Display / Results</h3>", unsafe_allow_html=True)

if 'query_done' in st.session_state and st.session_state['query_done']:
    action = st.session_state['action']
    print(f"[FLOW] Handling action: {action}")

    if action == "ADD":
        st.subheader("Add New GCP User")
        name = st.text_input("Name", key="add_name")
        email = st.text_input("Email", key="add_email")
        role = st.text_input("Role", key="add_role")
        if st.button("Add User"):
            print("[UI] Add User button clicked")
            if name and email and role:
                resp = call_mcp("add_user", {"name": name, "email": email, "role": role})
                if "result" in resp:
                    st.success(f"User added successfully with ID: {resp['result'].get('id')}")
                else:
                    st.error(resp.get("error", "Unknown error"))
            else:
                st.warning("Please fill all fields.")

    elif action == "UPDATE":
        st.subheader("Update User Details")
        user_id = st.number_input("User ID", min_value=1, step=1, key="upd_user_id")
        new_name = st.text_input("New Name (optional)", key="update_name")
        new_email = st.text_input("New Email (optional)", key="update_email")
        new_role = st.text_input("New Role (optional)", key="update_role")
        if st.button("Update User"):
            print(f"[UI] Update User clicked for ID {user_id}")
            params = {"user_id": user_id}
            if new_name: params["name"] = new_name
            if new_email: params["email"] = new_email
            if new_role: params["role"] = new_role
            resp = call_mcp("update_user", params)
            if "result" in resp:
                st.success("User updated successfully!")
            else:
                st.error(resp.get("error", "Update failed"))

    elif action == "DELETE":
        st.subheader("Delete GCP User")
        user_id = st.number_input("User ID", min_value=1, step=1)
        if st.button("Delete User"):
            print(f"[UI] Delete User clicked for ID {user_id}")
            resp = call_mcp("delete_user", {"user_id": user_id})
            if "result" in resp:
                st.success("User deleted successfully!")
            else:
                st.error(resp.get("error", "Delete failed"))

    elif action == "VIEW":
        st.subheader("View Users")
        view_choice = st.radio("Choose view option:", ["All Users", "Particular User"], horizontal=True)
        if view_choice == "All Users":
            if st.button("Show All Users"):
                print("[UI] Show All Users clicked")
                resp = call_mcp("list_users", {})
                if "result" in resp and resp["result"].get("users"):
                    st.dataframe(resp["result"]["users"], use_container_width=True)
                else:
                    st.info("No users found in the database.")
        else:
            user_id = st.number_input("Enter User ID to View", min_value=1, step=1)
            if st.button("Show User"):
                print(f"[UI] Show User clicked for ID {user_id}")
                resp = call_mcp("get_user", {"user_id": user_id})
                if "result" in resp and resp["result"]:
                    st.table([resp["result"]])
                else:
                    st.info(f"No user found with ID {user_id}")
    else:
        print("[WARN] Unknown action detected.")
        st.error("Sorry, I couldn't interpret the query.")
