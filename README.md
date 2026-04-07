# Agentic AI – Google Ecosystem

A **multi-agent AI system** built on the Google ecosystem that helps users manage
tasks, schedules, and information by interacting with their Google Calendar, Notes
(Google Tasks), and Maps through the **Model Context Protocol (MCP)**, and persisting
all relevant data in **AlloyDB** (Google's PostgreSQL-compatible cloud database).

---

## Architecture

```
User
 │
 ▼
OrchestratorAgent  (Gemini LLM, intent routing)
 ├── CalendarAgent  ──▶  Google Calendar API  (MCP tool)
 ├── NotesAgent     ──▶  Google Tasks API     (MCP tool)
 ├── MapsAgent      ──▶  Google Maps API      (MCP tool)
 └── TaskAgent      ──▶  AlloyDB              (persistence)
                           │
                    AlloyDB (PostgreSQL-compatible)
                    ┌──────────────────────────────┐
                    │ users        tasks            │
                    │ notes        calendar_events  │
                    │ locations    agent_sessions   │
                    │ agent_messages               │
                    └──────────────────────────────┘
```

### Components

| Component | Description |
|-----------|-------------|
| `agents/orchestrator.py` | Top-level agent – classifies user intent and delegates to specialist agents |
| `agents/calendar_agent.py` | Manages Google Calendar events (list / create / update / delete) |
| `agents/notes_agent.py` | Manages notes via Google Tasks (list / create / update / search / delete) |
| `agents/maps_agent.py` | Location queries – geocoding, place search, directions, distance matrix |
| `agents/task_agent.py` | Task management backed by AlloyDB |
| `tools/calendar_tool.py` | MCP-compatible Google Calendar tool functions |
| `tools/notes_tool.py` | MCP-compatible Google Tasks (notes) tool functions |
| `tools/maps_tool.py` | MCP-compatible Google Maps tool functions |
| `database/alloydb_client.py` | Async SQLAlchemy client for AlloyDB (with connector & direct-URL modes) |
| `database/models.py` | SQLAlchemy ORM models |
| `config/settings.py` | Pydantic settings (loaded from `.env`) |
| `main.py` | CLI entry-point (interactive chat + MCP server launcher) |

---

## Quick Start

### 1. Clone and install dependencies

```bash
git clone https://github.com/arkadipbasu/Agentic_AI_Google_ecosystem.git
cd Agentic_AI_Google_ecosystem
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env with your credentials (see below)
```

Required credentials:

| Variable | Where to get it |
|----------|----------------|
| `GOOGLE_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `GOOGLE_CREDENTIALS_PATH` | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) – OAuth 2.0 Client ID (Desktop app) |
| `GOOGLE_MAPS_API_KEY` | [Google Maps Platform](https://console.cloud.google.com/google/maps-apis) |
| `ALLOYDB_INSTANCE_URI` | Your AlloyDB instance URI |
| `ALLOYDB_DB_*` | AlloyDB database name / user / password |

> **Tip:** For local development without AlloyDB, leave `ALLOYDB_INSTANCE_URI` and
> `DATABASE_URL` empty. The system will automatically fall back to a local SQLite
> database (`agentic_ai_local.db`).

### 3. Run the interactive assistant

```bash
python main.py
```

### 4. Single-prompt mode

```bash
python main.py --prompt "What meetings do I have this week?"
python main.py --prompt "Find the nearest coffee shop to 1600 Amphitheatre Pkwy"
python main.py --prompt "Create a task: submit quarterly report by Friday"
```

### 5. Launch standalone MCP servers

The individual tool servers can be exposed as standalone MCP servers over stdio,
making them compatible with any MCP client (e.g., Claude Desktop, custom integrations):

```bash
python main.py mcp-server --service calendar
python main.py mcp-server --service notes
python main.py mcp-server --service maps
```

---

## Google API Scopes Required

Enable the following APIs in [Google Cloud Console](https://console.cloud.google.com/apis/library):

- **Google Calendar API** – `https://www.googleapis.com/auth/calendar`
- **Google Tasks API** – `https://www.googleapis.com/auth/tasks`
- **Google Maps Platform APIs** – Maps JavaScript API, Places API, Directions API, Geocoding API, Distance Matrix API

---

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

---

## Project Structure

```
Agentic_AI_Google_ecosystem/
├── agents/
│   ├── __init__.py
│   ├── calendar_agent.py    # Google Calendar specialist
│   ├── maps_agent.py        # Google Maps specialist
│   ├── notes_agent.py       # Google Tasks (notes) specialist
│   ├── orchestrator.py      # Top-level multi-agent orchestrator
│   └── task_agent.py        # AlloyDB-backed task manager
├── config/
│   ├── __init__.py
│   └── settings.py          # Pydantic settings from .env
├── database/
│   ├── __init__.py
│   ├── alloydb_client.py    # Async AlloyDB / SQLAlchemy client
│   └── models.py            # ORM models
├── tools/
│   ├── __init__.py
│   ├── calendar_tool.py     # MCP tool – Google Calendar
│   ├── maps_tool.py         # MCP tool – Google Maps
│   └── notes_tool.py        # MCP tool – Google Tasks / Notes
├── tests/
│   └── test_agents_and_tools.py
├── .env.example             # Environment variable template
├── .gitignore
├── main.py                  # CLI entry-point
├── README.md
└── requirements.txt
```

---

## License

MIT
