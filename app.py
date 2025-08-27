# app.py (tool-agnostic, 3 panes, with "Restart MCP & Refresh" + unified View Users UI)
import os
import json
import time
import subprocess
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from langchain.chat_models import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

load_dotenv()

# =========================
# CONFIG / CLIENTS
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("OPENAI_API_KEY not set in environment")
    st.stop()

llm = ChatOpenAI(
    model_name="gpt-4.1-nano-2025-04-14",
    temperature=0,
    openai_api_key=OPENAI_API_KEY,
)

st.set_page_config(page_title="MCP User Management", layout="wide")

# Apply custom CSS for compact font size
st.markdown(
    """
    <style>
    html, body, [class*="css"]  {
        font-size: 14px;   /* Adjust base font size */
    }
    h1 { font-size: 22px !important; text-align:center;margin-top:0 }
    h2 { font-size: 20px !important; }
    h3 { font-size: 18px !important; }
    h4 { font-size: 16px !important; }
    .stButton button {
        font-size: 14px !important;
        padding: 2px 8px !important;
    }
    .stTextInput>div>div>input {
        font-size: 14px !important;
        padding: 2px 6px !important;
    }
    </style>
    <h1>MCP User Management</h1>
    """, 
    unsafe_allow_html=True
)


# =========================
# DEBUG STORE
# =========================
def debug_reset():
    st.session_state["debug_msgs"] = []
    st.session_state["last_llm_route"] = None
    st.session_state["last_mcp_response"] = None
    st.session_state["selected_tool"] = None

def debug_log(msg):
    st.session_state.setdefault("debug_msgs", [])
    st.session_state["debug_msgs"].append(msg)

if "debug_msgs" not in st.session_state:
    debug_reset()

# =========================
# MCP SERVER (STDIO)
# =========================
MCP_CMD = ["python", "mcp_server.py"]

def start_mcp_server():
    debug_log("[INIT] Starting MCP server (stdio)...")
    proc = subprocess.Popen(
        MCP_CMD,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    time.sleep(0.25)  # brief warm-up
    debug_log("[INIT] MCP server started.")
    return proc


if "mcp_process" not in st.session_state:
    st.session_state.mcp_process = start_mcp_server()
mcp_proc = st.session_state.mcp_process

def call_mcp(method, params=None):
    """Send one JSON line to MCP server, read one JSON line back."""
    payload = {"id": str(time.time()), "method": method, "params": params or {}}
    debug_log(f"[MCP] -> {method} {params}")
    if mcp_proc.poll() is not None:
        resp = {"error": "MCP server not running"}
        st.session_state["last_mcp_response"] = resp
        return resp
    try:
        mcp_proc.stdin.write(json.dumps(payload) + "\n")
        mcp_proc.stdin.flush()
    except Exception as e:
        resp = {"error": f"failed to write to MCP stdin: {e}"}
        st.session_state["last_mcp_response"] = resp
        return resp
    try:
        line = mcp_proc.stdout.readline()
        if not line:
            resp = {"error": "No response from MCP server"}
            st.session_state["last_mcp_response"] = resp
            return resp
        resp = json.loads(line)
        debug_log(f"[MCP] <- {resp}")
        st.session_state["last_mcp_response"] = resp
        return resp
    except Exception as e:
        resp = {"error": f"invalid MCP response: {e}"}
        st.session_state["last_mcp_response"] = resp
        return resp

# =========================
# TOOL DISCOVERY (RUNTIME)
# =========================
def fetch_tools():
    """Ask server which tools exist + their simple schemas."""
    resp = call_mcp("list_tools", {})
    if resp.get("error"):
        st.error(f"Failed to fetch tools: {resp['error']}")
        return {}
    tools = (resp.get("result") or {}).get("tools", [])
    out = {}
    for t in tools:
        out[t["name"]] = {
            "description": t.get("description", ""),
            "params_schema": t.get("params_schema", {}),
            "required": t.get("required", []),
        }
    debug_log(f"[DISCOVERY] Tools available: {list(out.keys())}")
    return out

if "tools" not in st.session_state:
    st.session_state.tools = fetch_tools()

def has_tool(name: str) -> bool:
    return name in st.session_state.tools

# =========================
# LLM ROUTER (GENERIC)
# =========================
def route_with_llm(user_text: str, tools_catalog: dict) -> dict:
    """
    Ask LLM to pick ONE tool from the discovered list and propose params.
    Output MUST be JSON like: {"tool":"add_user","params":{"name":"..."}}
    """
    tool_list = [
        {
            "name": name,
            "description": data["description"],
            "required": data["required"],
            "params_schema": data["params_schema"],
        }
        for name, data in tools_catalog.items()
    ]
    system = (
        "You are a router. You must choose exactly one tool from the provided list.\n"
        "Return ONLY valid JSON with keys: tool (string) and params (object).\n"
        "If nothing matches, set tool to 'unknown' and params to {}.\n"
        "TOOLS:\n" + json.dumps(tool_list, ensure_ascii=False)
    )
    user = f"User request:\n{user_text}"
    resp = llm([SystemMessage(content=system), HumanMessage(content=user)])
    content = resp.content.strip()

    try:
        parsed = json.loads(content)
    except Exception:
        start = content.find("{"); end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(content[start:end+1])
            except Exception:
                parsed = {"tool":"unknown","params":{}}
        else:
            parsed = {"tool":"unknown","params":{}}

    
# Debug and tracking
    st.session_state["last_llm_route"] = {"raw": content, "parsed": parsed}
    st.session_state["llm_selected_tool"] = parsed.get("tool")
    # Reset invoked tool for this new query until something actually runs
    st.session_state["invoked_tool"] = parsed.get("tool")
    return parsed
# =========================
# SCHEMA → WIDGETS (GENERIC)
# =========================
def make_widget(field_name: str, spec: dict, default_val: str):
    """
    Build a Streamlit input widget from a simple schema spec.
    Supported: type: string|number|integer|boolean, enum, description
    """
    label = f"{field_name} ({spec.get('type','string')})"
    if spec.get("description"):
        label += f" — {spec['description']}"
    ftype = (spec.get("type") or "string").lower()
    enum = spec.get("enum")

    key = f"fld_{field_name}"

    if enum and isinstance(enum, list) and len(enum) > 0:
        idx = 0
        if default_val in enum:
            idx = enum.index(default_val)
        return st.selectbox(label, enum, index=idx, key=key)

    if ftype in ("number", "integer"):
        try:
            num_default = float(default_val) if default_val != "" else 0.0
        except Exception:
            num_default = 0.0
        if ftype == "integer":
            return st.number_input(label, value=int(num_default), step=1, key=key)
        else:
            return st.number_input(label, value=float(num_default), key=key)
    elif ftype == "boolean":
        bool_default = str(default_val).lower() in ("true", "1", "yes")
        return st.checkbox(label, value=bool_default, key=key)
    else:
        if field_name.lower() in ("body", "message", "description"):
            return st.text_area(label, value=str(default_val), key=key, height=120)
        return st.text_input(label, value=str(default_val), key=key)

def build_param_form(tool_name: str, tool_schema: dict, suggested: dict):
    """
    Render a form for any tool based on its params_schema + required.
    Returns (submitted: bool, params: dict)
    """
    required = tool_schema.get("required", [])
    schema_def = tool_schema.get("params_schema", {})

    with st.form(key=f"{tool_name}_form"):
        st.markdown(f"#### {tool_name} — Parameters")
        values = {}
        for field, spec in schema_def.items():
            default_val = suggested.get(field, "")
            values[field] = make_widget(field, spec, str(default_val))
        if required:
            st.caption(f"Required: {', '.join(required)}")
        pretty_name = tool_name.replace("_", " ").title()
        submitted = st.form_submit_button(pretty_name)


    if submitted:
        clean = {}
        for k, v in values.items():
            if isinstance(v, str):
                if v != "":
                    clean[k] = v
            else:
                clean[k] = v
        return True, clean
    return False, {}

# =========================
# GENERIC RESULT RENDERING
# =========================
def render_result(resp: dict):
    if resp.get("error"):
        st.error(resp["error"])
        return

    result = resp.get("result", None)
    if result is None:
        st.json(resp)
        return

    # Direct list case
    if isinstance(result, list) and result and isinstance(result[0], dict):
        st.dataframe(pd.DataFrame(result), use_container_width=True)
        return

    # Dict cases
    if isinstance(result, dict):
        # list-of-dicts under a single key
        for key, val in result.items():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                st.dataframe(pd.DataFrame(val), use_container_width=True)
                return
            if isinstance(val, dict):
                st.table(pd.DataFrame([val]))
                return
        # flat dict
        try:
            st.table(pd.DataFrame([result]))
            return
        except Exception:
            pass

    st.json(resp)

# =========================
# VIEW USERS (unified UI)
# =========================
def has_any_view_tools():
    return has_tool("list_users") or has_tool("get_user")

def view_users_unified_ui():
    """
    Unified UI for viewing users.
    - Always shows radio for "Single user" vs "All users"
    - Uses get_user when Single user is chosen, list_users for All users
    - Updates st.session_state["invoked_tool"] to reflect the actual tool invoked
    """
    if not has_any_view_tools():
        st.warning("No view tools available on the server.")
        return

    st.markdown("#### View Users")
    mode = st.radio("Choose view", ["Single user", "All users"], horizontal=True, key="view_mode_radio")

    if mode == "All users":
        # Button to fetch all
        if st.button("Show All", key="btn_show_all_users"):
            if has_tool("list_users"):
                st.session_state["invoked_tool"] = "list_users"    # reflect actual call
                resp = call_mcp("list_users", {})
                render_result(resp)
            else:
                st.warning("The 'list_users' tool is not available on the server.")

    else:
        # Single user flow
        id_label = "id"
        if has_tool("get_user"):
            schema = st.session_state.tools["get_user"]
            ps = (schema.get("params_schema") or {})
            if "id" in ps and ps["id"].get("description"):
                id_label = f"id — {ps['id']['description']}"

        uid = st.text_input(id_label, key="view_single_user_id")
        if st.button("Show", key="btn_show_single_user"):
            clean_id = (uid or "").strip()
            if not clean_id:
                st.warning("Please enter a user id.")
            else:
                if has_tool("get_user"):
                    st.session_state["invoked_tool"] = "get_user"   # reflect actual call
                    resp = call_mcp("get_user", {"id": clean_id})
                    render_result(resp)
                else:
                    st.warning("The 'get_user' tool is not available on the server.")

# =========================
# UI: THREE PANES
# =========================
left, middle, right = st.columns([1, 2, 1], gap="large")

# ---------- LEFT: Chat ----------
with left:
    st.markdown("### Chat")

    with st.form(key="chat_form"):
        user_query = st.text_input(
            "Type your request (e.g., 'add a user', 'update user id U005', 'delete user U010', 'show users')"
        )
        chat_submitted = st.form_submit_button("Submit")

    
    # On every new query → clear debug pane
    if chat_submitted:
        debug_reset()

    if chat_submitted and user_query.strip():
        # Always fetch latest tools so new tools appear without code changes
        st.session_state.tools = fetch_tools()
        route = route_with_llm(user_query, st.session_state.tools)
        st.session_state["route"] = route
        st.session_state["stage"] = "routed"

# ---------- MIDDLE: Action ----------
with middle:
    st.markdown("### Action")

    if st.session_state.get("stage") != "routed":
        st.info("Enter a request in the Chat pane to begin.")
    else:
        route = st.session_state.get("route", {"tool": "unknown", "params": {}})
        tool_name = route.get("tool") or "unknown"
        params_suggested = route.get("params") or {}

        tools = st.session_state.tools

        # SPECIAL: Unified View UI if user intent is 'view/show' OR the selected tool is list/get
        if (tool_name in ("list_users", "get_user")) and (has_tool("list_users") or has_tool("get_user")):
            view_users_unified_ui()
        else:
            if tool_name == "unknown" or tool_name not in tools:
                st.info("I don’t have the information.")
            else:
                schema = tools[tool_name]
                submitted, final_params = build_param_form(tool_name, schema, params_suggested)
                if submitted:
                    resp = call_mcp(tool_name, final_params)
                    render_result(resp)

# ---------- RIGHT: LLM & Tool Debug ----------
with right:
    st.markdown("### LLM & Tool Debug")
    st.write("**LLM-selected tool:**", st.session_state.get("llm_selected_tool"))
    st.write("**Invoked tool (latest):**", st.session_state.get("invoked_tool"))

    # with st.expander("LLM Routing (raw & parsed)", expanded=True):
    #     st.json(st.session_state.get("last_llm_route"))
    with st.expander("Discovered tools (from MCP server)"):
        tool_names = list(st.session_state.tools.keys())
        if tool_names:
            st.write(" |  ".join(tool_names))
        else:
            st.info("No tools discovered.")
    # with st.expander("Last MCP Response", expanded=True):
    #     st.json(st.session_state.get("last_mcp_response"))
    with st.expander("Debug log"):
        st.write("\n".join(st.session_state.get("debug_msgs", [])))
