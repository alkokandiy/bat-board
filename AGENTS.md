# bat-board — working notes for coding agents

A multi-user, Batman-themed life operating system with an AI companion, **Alfred**.
Deployed on Railway from `main`; `preDeployCommand` runs `alembic upgrade head`.
Merging to `main` therefore ships to real users — treat it that way.

## Stack

- **Backend** `backend/` — FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, PyJWT,
  bcrypt, Fernet, slowapi, structlog, httpx. Python venv at `backend/.venv`.
- **Frontend** `frontend/` — React 18 + Vite + Tailwind + vitest.
- **DB** — PostgreSQL in production, SQLite in tests. Migrations must work on both.

## Commands

```bash
cd backend && .venv/bin/python -m pytest tests/ -q      # 294 tests
cd frontend && npx vitest run                           # 56 tests
cd frontend && npm run build
```

Never run a dev server to "check" something; run the tests.

## Layout and conventions

- `backend/main.py` holds older inline routes; **new endpoints go in
  `backend/routers/<area>.py`** with Pydantic contracts in `backend/schemas/`.
- **Routers stay thin.** All business logic lives in `backend/services/`, because
  the web API and Alfred's tools must call the *same* code and never disagree.
- Alfred's tools: `services/alfred_tools.py` (schemas + `execute_tool`), driven by
  `services/alfred_agent.py`. Destructive tools go through a confirmation gate.
- Scheduling is **not** in-process: `POST /api/internal/cron/tick` is pinged every
  minute by an external cron. Anything periodic belongs in `services/scheduler.py`
  and must be safe to run repeatedly and from multiple workers.
- Per-user timezones: use `services/timezones.py`, never naive "today".
- Migrations are numbered (`021` is current head). New migration = next number,
  additive where possible, and must be reversible.
- Comments explain **why**, not what — especially the non-obvious decision behind a
  line. Match the surrounding density; don't narrate the code.

## Rules that must not be broken

1. **Multi-user.** Never hard-code the owner's name, timezone, gender or data.
   Every query is scoped by `owner_id`.
2. **Work earns no Bat Points.** The corporate track (`services/work_service.py`)
   is the job; points measure the person. Nothing in it touches `points` or
   `bat_level`. Work can also be switched off per user — `work_service.is_enabled`
   is the single source of truth, and "off" must mean off everywhere.
3. **Don't break existing users.** Columns are added nullable or with a default;
   no destructive migration without being told.
4. Secrets come from env via `config.py`. Never log or return an API key.
5. Tests are part of the change, not an afterthought — and a bug fix gets a test
   that fails before the fix.

## If you are a delegated agent

- **Do not** `git commit`, `git push`, merge, or open a PR. Leave the working tree
  dirty and report what you changed; the orchestrating agent reviews and commits.
- Stay inside the scope you were given. If the task looks wrong or wider than
  stated, say so and stop rather than widening it.
- Run the relevant test suite yourself and report the real result. Never report a
  test as passing without running it.
