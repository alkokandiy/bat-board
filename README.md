# Bat-Board

A Batman-themed personal productivity dashboard with missions, habits, focus timer, and activity logging.

## Stack

- **Backend**: Python 3.12 + FastAPI + SQLAlchemy + PostgreSQL/SQLite
- **Frontend**: React 18 + Vite + Tailwind CSS
- **Auth**: JWT (access + refresh tokens)

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL (optional, SQLite used by default)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit SECRET_KEY
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open http://localhost:5173

### Docker Compose

```bash
docker compose up
```

## Deploy to Railway

### One-click deploy

1. Push repo to GitHub
2. Create a new Railway project from the repo
3. Add a PostgreSQL plugin
4. Set environment variables in Railway dashboard:
   - `SECRET_KEY` — a random 64-character string
   - `ENVIRONMENT` — `production`
   - `CORS_ORIGINS` — `["*"]` or your frontend domain
5. Railway uses the root `Dockerfile` and sets `DATABASE_URL` automatically via the PostgreSQL plugin

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | No | `sqlite:///./batboard.db` | PostgreSQL URL (Railway sets this) |
| `SECRET_KEY` | Recommended | default string | JWT signing key (set a strong one) |
| `ENVIRONMENT` | No | `production` | `development` enables docs |
| `CORS_ORIGINS` | No | `["http://localhost:5173"]` | JSON array or comma-separated |
| `LOG_FORMAT` | No | `console` | `json` for structured logging |

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | No | Create account |
| POST | `/api/auth/login` | No | Get tokens |
| POST | `/api/auth/refresh` | No | Refresh tokens |
| GET | `/api/auth/me` | Yes | Current user |
| GET | `/api/health` | No | Health check |
| GET/PUT | `/api/account` | Yes | Get/update account |
| GET/POST | `/api/missions` | Yes | List/create missions |
| PUT/DELETE | `/api/missions/{id}` | Yes | Update/delete mission |
| GET/POST | `/api/habits` | Yes | List/create habits |
| PUT/DELETE | `/api/habits/{id}` | Yes | Update/delete habit |
| POST | `/api/habits/{id}/check-in` | Yes | Complete habit |
| GET/POST | `/api/logs` | Yes | List/create logs |
| GET/POST | `/api/focus/sessions` | Yes | List/start focus |
| PUT | `/api/focus/sessions/{id}` | Yes | End focus session |
