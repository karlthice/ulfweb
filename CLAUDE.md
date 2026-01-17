# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ULF Web is a chat web application that provides a web interface to llama.cpp. It uses FastAPI (Python) for the backend and vanilla JavaScript for the frontend, with SQLite for persistence.

## Development Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Run the server (development)
python -m backend.main
# Server runs on http://0.0.0.0:8000 by default

# Install dependencies
pip install -r requirements.txt
```

## Architecture

### Backend (FastAPI + SQLite)

- **Entry point:** `backend/main.py` - FastAPI app with lifespan management
- **API prefix:** `/api/v1/`
- **Routers:**
  - `routers/conversations.py` - CRUD for conversations
  - `routers/chat.py` - Streaming chat via SSE to llama.cpp
  - `routers/settings.py` - Per-user LLM parameter settings
- **Storage:** `services/storage.py` - All database operations (async with aiosqlite)
- **Static files:** Frontend served directly from `/frontend/`

### Frontend (Vanilla JS SPA)

- **Entry:** `frontend/index.html` - Single-page application
- **No build tools** - Direct HTML/CSS/JS, uses ES modules
- **Key modules:**
  - `js/api.js` - HTTP client for backend
  - `js/sse.js` - Server-Sent Events handler for streaming responses
  - `js/chat.js` - Chat UI and message rendering
  - `js/conversations.js` - Sidebar conversation management
  - `js/settings.js` - Settings modal
- **External dependency:** marked.js (CDN) for markdown rendering

### Data Flow

1. User sends message → POST `/api/v1/chat/{conversation_id}`
2. Backend saves message, fetches history and user settings
3. Backend streams request to llama.cpp server
4. Response streamed back via SSE
5. Frontend renders streamed markdown in real-time
6. Backend saves final assistant message

### User Model

Users are identified by IP address (no authentication). Each user has isolated:
- Conversations with messages
- LLM parameter settings (temperature, top_k, top_p, repeat_penalty, max_tokens, system_prompt)

## Configuration

**config.yaml** - Primary configuration:
```yaml
server:
  host: "0.0.0.0"
  port: 8000
llama:
  url: "http://localhost:8081"  # llama.cpp server
database:
  path: "data/ulfweb.db"
defaults:  # Default LLM parameters
  temperature: 0.7
  top_k: 40
  top_p: 0.9
  repeat_penalty: 1.1
  max_tokens: 2048
  system_prompt: "You are a helpful assistant."
```

**Environment variables** (override config.yaml with `ULFWEB_` prefix):
- `ULFWEB_LLAMA_URL`, `ULFWEB_DATABASE_PATH`, `ULFWEB_SERVER_HOST`, `ULFWEB_SERVER_PORT`

## Database Schema

SQLite with four tables: `users` (IP-based), `user_settings`, `conversations`, `messages`. Messages have role constraint: `user`, `assistant`, or `system`. Conversations cascade delete their messages.

## Key Files

- `backend/config.py` - Config loading from YAML + env vars
- `backend/models.py` - Pydantic models with validation bounds
- `backend/database.py` - Schema definition and connection management
- `frontend/css/main.css` - Primary styles
- `frontend/css/responsive.css` - Mobile breakpoints
