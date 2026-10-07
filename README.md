<div align="center">

# 🦇 Bat-Board

**A Batman-themed personal productivity dashboard — missions, habit streaks, a multi-mode focus timer, and activity logging, wrapped in a dark command-center UI.**

![React](https://img.shields.io/badge/React-18.2-61DAFB?style=flat&logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688?style=flat&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4.3-06B6D4?style=flat&logo=tailwindcss&logoColor=white)
[![License](https://img.shields.io/badge/License-MIT-yellow)](https://github.com/alkokandiy/bat-board/blob/main/LICENSE)

</div>

---

## Screenshots

<div align="center">

| Focus Timer | Dashboard | Missions | Calendar |
|:-----------:|:---------:|:--------:|:--------:|
| ![Focus Timer](frontend/src/bat-board1.png) | ![Dashboard](frontend/src/bat-board2.png) | ![Missions](frontend/src/bat-board3.png) | ![Calendar](frontend/src/bat-board4.png) |

</div>

---

## Overview

10 dedicated views, no router — state-driven via `currentView` in `App.jsx`. Every module is complete and CRUD-backed against a real **FastAPI + PostgreSQL** backend behind **JWT auth**.

---

## Features

| Module | Description |
|--------|-------------|
| **Dashboard** | Summary cards (pending missions, max habit streak, bat level) + welcome block |
| **Missions** | Full CRUD, search, sort, filter by status/tags, pin/dismiss |
| **Habits** | Streak tracking, daily check-in, completion history |
| **Focus Hourglass** | Fullscreen Pomodoro timer with 4 visual modes (Normal, Flip Clock, Bat-Signal spotlight reveal, Batmobile route tracker), mission/habit targeting, integrated soundtrack |
| **John Wick Timer** | Stylized countdown with blood-drip animation and gun-sight UI |
| **Countdown** | Custom countdowns to user-set dates |
| **Calendar** | Monthly view with events linked to missions |
| **Notes** | Two-pane, Apple Notes-style editor with CRUD, search, sort, pin, tags, auto-save |
| **Logs** | Activity/event log (points earned, completions, etc.) |
| **Profile** | Account settings, bat-level display |

---

## Tech Stack

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.2 (JSX) | UI library |
| Vite | 4.4.5 | Build tool & dev server |
| Tailwind CSS | 3.4.3 | Utility-first styling |
| State Management | React built-ins (`useState`, `useRef`, `useCallback`) | No external state library |
| Fonts | Inter (UI), Share Tech Mono (monospace), Bebas Neue (display), Rajdhani (body) | Typography |

**Custom Tailwind tokens:** `matte-obsidian`, `electric-bat-yellow`, `dark-slate`, `bat-surface`, `bat-card`

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.12+ | Runtime |
| FastAPI | 0.111.0 | Web framework |
| SQLAlchemy | 2.0.29 | ORM |
| Alembic | 1.12.1 | Database migrations |
| Uvicorn | 0.29.0 | ASGI server (dev) |
| Gunicorn | 22.0.0 | ASGI server (prod) |
| Pydantic | v2.7.1 | Data validation |
| structlog | 24.1.0 | Structured logging |
| slowapi | 0.1.9 | Rate limiting (5/min register, 10/min login) |

### Database

| Environment | Engine |
|-------------|--------|
| Development | SQLite (`batboard.db`) |
| Production | PostgreSQL 16 (`postgres:16-alpine` via Docker Compose) |

**7 tables:** `bat_account`, `bat_missions`, `bat_habits`, `habit_completion_logs`, `bat_log`, `bat_focus`, `bat_calendar_events`

### Auth

- **JWT** (HS256, via `python-jose`)
- Passwords hashed with **bcrypt** (`passlib`)
- Access token: **24h** · Refresh token: **30 days**, auto-refreshed hourly
- `OAuth2PasswordBearer` scheme, tokens stored in `localStorage`

### Sync

No WebSockets/SSE — timer accuracy is handled client-side via `setInterval` + `Date.now()`

### Deployment

Docker + Docker Compose, deployable to **Railway**

---

## Getting Started

### Prerequisites

- **Docker & Docker Compose** (or Node 18+ / Python 3.12+ for local dev without containers)

### Run with Docker

```bash
# Clone the repository
git clone https://github.com/your-username/bat-board.git
cd bat-board

# Start all services
docker compose up

# Access the app
open http://localhost:5173
```

### Local Development (without Docker)

**Backend:**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit SECRET_KEY
uvicorn main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | `sqlite:///./batboard.db` | PostgreSQL URL (Railway sets this) |
| `SECRET_KEY` | Recommended | default string | JWT signing key — set a strong one |
| `ENVIRONMENT` | No | `production` | `development` enables API docs |
| `CORS_ORIGINS` | No | `["http://localhost:5173"]` | JSON array or comma-separated |
| `LOG_FORMAT` | No | `console` | `json` for structured logging |
| `TELEGRAM_BOT_TOKEN` | For Telegram | — | Bot token from BotFather (voice, images, briefings, reminders) |
| `TELEGRAM_WEBHOOK_SECRET` | For Telegram | — | Shared secret for the Telegram webhook |
| `CRON_SECRET` | For briefings | — | Shared secret for the briefings/reminders cron tick (see below). Unset → the tick endpoint returns 503 and the feature stays dormant |
| `SYSTEM_PROVIDER` | For free tier | — | Built-in provider for new users (`gemini`/`anthropic`/`openai`/`deepseek`/`kimi`). Set all three `SYSTEM_*` vars to turn the free tier on |
| `SYSTEM_MODEL` | For free tier | — | Model id for `SYSTEM_PROVIDER` |
| `SYSTEM_PROVIDER_KEY` | For free tier | — | The operator-funded key. While unset, users with no key of their own see the setup prompt (unchanged). While set, they get Alfred for free up to the daily cap; BYOK stays unlimited |
| `FREE_TIER_DAILY_CAP` | No | `15` | Messages/day for free-tier users before they're nudged to add their own key |

---

## API Endpoints

### Authentication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/auth/register` | No | Create account |
| `POST` | `/api/auth/login` | No | Get tokens |
| `POST` | `/api/auth/refresh` | No | Refresh tokens |
| `GET` | `/api/auth/me` | Yes | Current user |

### Account

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/account` | Yes | Get account |
| `PUT` | `/api/account` | Yes | Update account |
| `PUT` | `/api/account/password` | Yes | Change password |
| `POST` | `/api/account/reset-points` | Yes | Reset points to zero |

### Missions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/missions` | Yes | List missions |
| `POST` | `/api/missions` | Yes | Create mission |
| `PUT` | `/api/missions/{id}` | Yes | Update mission |
| `DELETE` | `/api/missions/{id}` | Yes | Delete mission |

### Habits

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/habits` | Yes | List habits |
| `POST` | `/api/habits` | Yes | Create habit |
| `PUT` | `/api/habits/{id}` | Yes | Update habit |
| `DELETE` | `/api/habits/{id}` | Yes | Delete habit |
| `POST` | `/api/habits/{id}/check-in` | Yes | Complete habit |

### Calendar

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/calendar/events` | Yes | List calendar events |
| `POST` | `/api/calendar/events` | Yes | Create calendar event |
| `PUT` | `/api/calendar/events/{id}` | Yes | Update calendar event |
| `DELETE` | `/api/calendar/events/{id}` | Yes | Delete calendar event |

### Focus Sessions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/focus/sessions` | Yes | Start focus session |
| `PUT` | `/api/focus/sessions/{id}` | Yes | End focus session |
| `GET` | `/api/focus/sessions` | Yes | List focus sessions |

### Logs

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/logs` | Yes | List activity logs |
| `POST` | `/api/logs` | Yes | Create log entry |

### System

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/health` | No | Health check |

---

## Project Structure

```
bat-board/
├── backend/
│   ├── main.py              # FastAPI app — all endpoints
│   ├── models.py            # SQLAlchemy ORM models
│   ├── config.py            # Settings & env vars
│   ├── database.py          # DB engine & session
│   ├── auth.py              # JWT & password utilities
│   ├── alembic/             # Database migrations
│   ├── tests/               # Backend test suite
│   ├── Dockerfile           # Backend container
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Root component — state-driven routing
│   │   ├── main.jsx         # Entry point
│   │   ├── index.css        # Global styles & Tailwind config
│   │   ├── components/      # 13 UI modules
│   │   │   ├── DashboardLayout.jsx
│   │   │   ├── MissionsPanel.jsx
│   │   │   ├── HabitsPanel.jsx
│   │   │   ├── FocusPanel.jsx
│   │   │   ├── BatFocusTimer.jsx
│   │   │   ├── FlipTimer.jsx
│   │   │   ├── JohnWickPanel.jsx
│   │   │   ├── CountdownPanel.jsx
│   │   │   ├── CalendarPanel.jsx
│   │   │   ├── NotesPanel.jsx
│   │   │   ├── LogsPanel.jsx
│   │   │   ├── ProfileSettings.jsx
│   │   │   └── AudioPlayer.jsx
│   │   └── utils/           # Helper functions
│   ├── public/              # Static assets
│   ├── index.html           # Vite entry
│   ├── tailwind.config.cjs  # Tailwind custom tokens
│   └── vite.config.js       # Vite config
├── docker-compose.yml       # Multi-service orchestration
├── Dockerfile               # Root Dockerfile (Railway)
└── railway.toml             # Railway deployment config
```

---

## Deploy to Railway

### One-click Deploy

1. Push repo to GitHub
2. Create a new Railway project from the repo
3. Add a PostgreSQL plugin
4. Set environment variables in Railway dashboard:
   - `SECRET_KEY` — a random 64-character string
   - `ENVIRONMENT` — `production`
   - `CORS_ORIGINS` — `["*"]` or your frontend domain
5. Railway uses the root `Dockerfile` and sets `DATABASE_URL` automatically via the PostgreSQL plugin

### Enabling Alfred's briefings & reminders (cron)

Alfred's morning/night briefings and reminders are fired by a small endpoint
that must be called about once a minute from **outside** the app
(`POST /api/internal/cron/tick`). This avoids an in-process scheduler, so it
stays correct no matter how many web workers run. Until you complete these
steps the feature is dormant (the endpoint returns `503`) and nothing is sent.

**1. Generate a secret** (run locally, copy the output):

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**2. Add it to the app service** on Railway → Variables:

- `CRON_SECRET` = the value you just generated

Redeploy so the web service picks it up.

**3. Create a pinger that calls the tick every minute.** Either option works:

- **Railway Cron service** (recommended): add a new service in the same project
  from a minimal image, set its **Cron Schedule** to `* * * * *`, and set its
  start command to:

  ```bash
  curl -fsS -X POST https://<your-app-domain>/api/internal/cron/tick \
    -H "X-Cron-Secret: $CRON_SECRET"
  ```

  Give that service the same `CRON_SECRET` variable.

- **External uptime pinger** (e.g. cron-job.org, UptimeRobot): schedule a
  `POST` to `https://<your-app-domain>/api/internal/cron/tick` every minute
  with a request header `X-Cron-Secret: <your secret>`.

**4. Verify.** A correct call returns `200` with a JSON summary, e.g.
`{"ok": true, "users": 1, "briefings_sent": 0, ...}`. A missing/wrong secret
returns `401`; an unconfigured `CRON_SECRET` returns `503`.

> Briefings and reminders are delivered over **Telegram**, so a user must have
> linked their Telegram account (Profile → Link Telegram) to receive them.
> Each briefing/reminder fires **at most once per local day**, in the user's
> own timezone, and a window missed by more than ~3 hours is skipped rather
> than sent late. Users ask Alfred to set these up conversationally
> ("set up a morning briefing at 7", "remind me to take my medicine every day
> at 9am").

---

## License

MIT
