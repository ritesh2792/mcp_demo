# app.py
import os
import json
import time
import subprocess
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
st.markdown(
    "<h1 style='text-align:center;margin-top:0'>MCP User Management</h1>",
    unsafe_allow_html=True,
)

# =========================
# MCP SERVER SUBPROCESS (STDIO)
# =========================
MCP_CMD = ["python", "mcp_server.py"]

def start_mcp_server():
    print("[INIT] Starting MCP server (stdio)...")
    proc = subprocess.Popen(
        MCP_CMD, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1
    )
    time.sleep(0.25)
    print("[INIT] MCP server started.")
    return proc

if "mcp_process" not in st.session_state:
    st.session_state.mcp_process = start_mcp_server()
mcp_proc = st.session_state.mcp_process

def call_mcp(method, params=None):
    """Send one JSON line to MCP server, read one JSON line back."""
    print(f"[MCP] -> {method} {params}")
    if mcp_proc.poll() is not None:
        return {"error": "MCP server not running"}
    req = {"id": str(time.time()), "method": method, "params": params or {}}
    try:
        mcp_proc.stdin.write(json.dumps(req) + "\n")
        mcp_proc.stdin.flush()
    except Exception as e:
        return {"error": f"failed to write to MCP stdin: {e}"}
    try:
        line = mcp_proc.stdout.readline()
        if not line:
            return {"error": "No response from MCP server"}
        resp = json.loads(line)
        print(f"[MCP] <- {resp}")
        return resp
    except Exception as e:
        return {"error": f"invalid MCP response: {e}"}

# =========================
# TOOL DISCOVERY (RUNTIME)
# =========================
def fetch_tools():
    """Ask server which tools exist + their simple schemas."""
    resp = call_mcp("list_tools", {})
    if resp.get("error"):
        st.error(f"Failed to fetch tools: {resp['error']}")
        return {}
    tools = resp.get("result", {}).get("tools", [])
    # Normalize to dict: {tool_name: {description, params_schema, required}}
    out = {}
    for t in tools:
        out[t["name"]] = {
            "description": t.get("description", ""),
            "params_schema": t.get("params_schema", {}),
            "required": t.get("required", []),
        }
    print(f"[DISCOVERY] Tools available: {list(out.keys())}")
    return out

if "tools" not in st.session_state:
    st.session_state.tools = fetch_tools()

# =========================
# LLM ROUTER (DYNAMIC)
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
        "Do not invent tools. If nothing fits, set tool to 'unknown' and params to {}.\n"
        "TOOLS:\n" + json.dumps(tool_list, ensure_ascii=False)
    )
    user = f"User request:\n{user_text}"
    resp = llm([SystemMessage(content=system), HumanMessage(content=user)])
    content = resp.content.strip()

    # Try to parse JSON in multiple ways
    try:
        return json.loads(content)
    except Exception:
        start = content.find("{"); end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start:end+1])
            except Exception:
                return {"tool":"unknown","params":{}}
        return {"tool":"unknown","params":{}}

def missing_required(schema_required, provided_params):
    return [key for key in schema_required if not provided_params.get(key)]

# =========================
# UI LAYOUT
# =========================
left, right = st.columns([1, 2])

with left:
    st.markdown("### Chat")
    user_query = st.text_input("Type your request (e.g., 'add a gcp user', 'show users', 'update user ...')")
    colA, colB = st.columns(2)
    with colA:
        submit = st.button("Submit")
    with colB:
        refresh = st.button("Refresh Tools")

    if refresh:
        st.session_state.tools = fetch_tools()
        st.success("Tools refreshed.")

    if submit and user_query.strip():
        st.session_state.route = route_with_llm(user_query, st.session_state.tools)
        st.session_state.stage = "routed"

with right:
    st.markdown("### Results & Forms")

    # Show current tool catalog (collapsible)
    with st.expander("Discovered tools (from MCP server)"):
        st.json(st.session_state.tools)

    if st.session_state.get("stage") == "routed":
        route = st.session_state.get("route", {"tool":"unknown","params":{}})
        tool_name = route.get("tool","unknown")
        params = route.get("params", {}) or {}
        st.write(f"**Selected tool:** `{tool_name}`")
        st.write("**Proposed params:**", params)

        tools = st.session_state.tools
        if tool_name not in tools:
            st.warning("Unknown tool selected by the LLM. Please rephrase or refresh tools.")
        elif tool_name == "unknown":
            st.info("LLM could not map your request to a known tool. Try again or specify the action more clearly.")
        else:
            schema = tools[tool_name]
            required = schema.get("required", [])
            schema_def = schema.get("params_schema", {})

            # Build inputs for missing required params (and allow editing provided ones)
            st.markdown("#### Provide/confirm parameters")
            form_vals = {}
            for key, field_def in schema_def.items():
                label = f"{key} ({field_def.get('type','string')})"
                default_val = str(params.get(key) or "")
                form_vals[key] = st.text_input(label, value=default_val, key=f"{tool_name}_{key}")

            need = missing_required(required, form_vals)
            if need:
                st.warning(f"Missing required: {', '.join(need)}")

            if st.button(f"Run: {tool_name}"):
                final_params = {k: (v if v != "" else None) for k, v in form_vals.items()}
                # Strip None (let server decide defaults)
                final_params = {k:v for k,v in final_params.items() if v is not None}
                resp = call_mcp(tool_name, final_params)

                if resp.get("error"):
                    st.error(resp["error"])
                else:
                    st.success("Tool executed.")
                    st.json(resp)
