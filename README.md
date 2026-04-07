# Multi-Agent Google Assistant

A production-grade multi-agent AI system running on Google Cloud that manages tasks, schedules, notes, and location queries through a unified REST API.

## Architecture

```
Client → POST /chat → Orchestrator (Gemini routing)
                         ├── CalendarAgent → Google Calendar API
                         ├── NotesAgent    → Google Keep API
                         ├── MapsAgent     → Google Maps Platform
                         └── TasksAgent    → Google Tasks API
                                   ↕
                            AlloyDB (sessions, events, notes, tasks)
```

All agents run on **Cloud Run** (serverless). Reasoning is powered by **Vertex AI Gemini**. Data is persisted in **AlloyDB for PostgreSQL**.

---

## File Structure

```
.
├── main.py                    # FastAPI app — REST API
├── config.py                  # Settings (env / Secret Manager)
├── db.py                      # AlloyDB models + async session
├── agents/
│   ├── base_agent.py          # Abstract base — Gemini function-calling loop
│   ├── orchestrator.py        # Routes user intent to sub-agents
│   ├── calendar_agent.py      # Calendar domain agent
│   └── sub_agents.py          # Notes, Maps, Tasks agents
├── tools/
│   ├── calendar_tool.py       # Google Calendar MCP wrappers
│   ├── notes_tool.py          # Google Keep MCP wrappers
│   ├── maps_tool.py           # Google Maps MCP wrappers
│   └── tasks_tool.py          # Google Tasks MCP wrappers
├── Dockerfile
├── deploy.sh                  # One-shot Cloud Run deployment
├── requirements.txt
└── .env.example
```

---

## Deployment Guide (Google Cloud Console)

### Step 1 — Prerequisites

1. **Google Cloud project** with billing enabled (you already have this).
2. **Google Calendar API** enabled (you already have this).
3. Download and install the [gcloud CLI](https://cloud.google.com/sdk/docs/install).
4. Authenticate: `gcloud auth login && gcloud auth application-default login`

### Step 2 — Google Workspace Service Account

The agents use a **service account with domain-wide delegation** to call Calendar, Keep, and Tasks APIs on behalf of users.

1. Go to **IAM & Admin → Service Accounts** → Create service account → name it `multi-agent-sa`.
2. Download the JSON key → save as `google-sa-key.json` in this folder.
3. In **Google Admin Console** (`admin.google.com`):
   - Security → API controls → Domain-wide delegation → Add new
   - Client ID: paste the service account's `client_id`
   - OAuth scopes:
     ```
     https://www.googleapis.com/auth/calendar
     https://www.googleapis.com/auth/keep
     https://www.googleapis.com/auth/tasks
     ```

### Step 3 — Google Maps API Key

1. Go to **APIs & Services → Credentials** → Create credentials → API Key.
2. Restrict to: Maps JavaScript API, Geocoding API, Places API, Directions API, Distance Matrix API.
3. Copy the key — you'll paste it into `deploy.sh`.

### Step 4 — Edit deploy.sh

Open `deploy.sh` and set:
```bash
PROJECT_ID="your-gcp-project-id"    # your real project ID
```
And replace the placeholder values:
```bash
"CHANGE_ME_DB_PASSWORD"  →  a strong password
"YOUR_GOOGLE_MAPS_API_KEY"  →  key from Step 3
```

### Step 5 — Run deployment

```bash
chmod +x deploy.sh
./deploy.sh
```

This will (in order):
1. Enable all required Google Cloud APIs
2. Create a service account with correct IAM roles
3. Create an AlloyDB cluster and primary instance (~5 min)
4. Store secrets in Secret Manager
5. Build and push the Docker image via Cloud Build
6. Deploy to Cloud Run with VPC connector to AlloyDB
7. Run a health check

### Step 6 — Test the API

```bash
# New chat session
curl -X POST https://YOUR-SERVICE-URL/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Schedule a dentist appointment next Tuesday at 2pm", "user_id": "user1"}'

# Continue same session
curl -X POST https://YOUR-SERVICE-URL/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Also create a task to confirm the appointment", "session_id": "SESSION_ID", "user_id": "user1"}'

# Find nearby coffee shops
curl -X POST https://YOUR-SERVICE-URL/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find coffee shops near MG Road Bangalore", "user_id": "user1"}'
```

---

## API Reference

### `POST /chat`
| Field | Type | Description |
|-------|------|-------------|
| `message` | string | User's natural language request |
| `session_id` | string? | Omit to start a new session |
| `user_id` | string | Your app's user identifier |

**Response:**
```json
{
  "session_id": "uuid",
  "routed_to": ["calendar"],
  "summary": "I've scheduled your dentist appointment for Tuesday...",
  "responses": [{ "agent": "calendar", "result": "...", "tool_called": "create_event" }]
}
```

### `GET /sessions/{session_id}` — Retrieve session history
### `DELETE /sessions/{session_id}` — Clear session
### `GET /health` — Liveness probe

---

## Local Development

```bash
# 1. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Set up env
cp .env.example .env
# Edit .env with your values

# 3. Start AlloyDB Auth Proxy locally (or use Cloud SQL Proxy for dev)
./alloydb-auth-proxy "projects/PROJECT/locations/REGION/clusters/CLUSTER/instances/INSTANCE"

# 4. Run
uvicorn main:app --reload --port 8080
```

---

## Extending

To add a new agent (e.g. Gmail):
1. Create `tools/gmail_tool.py` with a `GMAIL_TOOLS` manifest.
2. Create `agents/gmail_agent.py` extending `BaseAgent`.
3. Register it in `agents/orchestrator.py`'s `AGENTS` dict.
4. Add the Gmail scope to the service account delegation.

That's it — the orchestrator automatically routes relevant queries to the new agent.
