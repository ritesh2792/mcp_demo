# GCP User Admin — MCP Tools + Streamlit

This demo lets you:
- Say: "I want to add a new GCP user" → Chatbot collects name, email, role → calls MCP `add_user` → inserts into SQLite
- Say: "Show me all the users" → Chatbot calls MCP `list_users` → shows a table

## 1) Create & activate a venv
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
````

## 2) Install dependencies

```bash
pip install -r requirements.txt
```

## 3) Configure OpenAI

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY
```

## 4) Initialize database (auto)

The first run creates `users.db` and the `gcp_users` table automatically.

## 5) Run the app

```bash
streamlit run app.py
```

### Notes

* The Streamlit app uses `fastmcp.Client` to spawn `mcp_server.py` via stdio and call tools.
* If you want to run the server independently (HTTP or SSE), adjust the client creation accordingly.
* `id` is a UUID4; `created_at` is UTC ISO timestamp.
* Emails are normalized to lowercase and must be unique; duplicate insertions will raise an SQLite error—add your own try/except and message if you want custom UX.

```
```