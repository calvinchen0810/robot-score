# Robot Score – Game Ranking Portal

A FastAPI web app for tracking robot competition scores with live rankings.

## Features

- **Client page** (`/`) – Phone-optimized. Teams join the active game, then tap +/− buttons to score.
- **Dashboard** (`/dashboard`) – Big-screen live ranking with auto-refresh every 3 seconds.
- **Admin** (`/admin`) – Phone-optimized. Manage series, games, score buttons, and team data.

## Local Development (SQLite)

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run
uvicorn main:app --reload
```

Open:
- Client: http://localhost:8000
- Dashboard: http://localhost:8000/dashboard
- Admin: http://localhost:8000/admin

The local `.env` defaults to SQLite (`robot_score.db` file).

## Deploy to Render.com (PostgreSQL)

1. Push this repo to GitHub.
2. On [render.com](https://render.com), click **New → Blueprint** and connect your repo.
3. Render reads `render.yaml` and creates the web service + PostgreSQL database automatically.
4. The `DATABASE_URL` env var is set from the database – the app auto-detects PostgreSQL.

### Manual deploy (without Blueprint)

1. Create a **PostgreSQL** database on Render.
2. Create a **Web Service** pointing to this repo.
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Add env var `DATABASE_URL` = your PostgreSQL connection string.

## Architecture

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, page routes, startup |
| `database.py` | SQLAlchemy engine (SQLite/PostgreSQL) |
| `models.py` | DB models: Series, Game, Team, ScoreButton, TeamScore |
| `schemas.py` | Pydantic schemas for request/response |
| `routes.py` | All API endpoints under `/api` |
| `templates/` | Jinja2 HTML pages (client, dashboard, admin) |
| `static/` | CSS |

## Workflow

1. **Admin** creates a **Series** (e.g. "2026 Regional") and activates it.
2. **Admin** adds **Score Buttons** (e.g. "Obstacle +5pts", "Penalty −2pts").
3. **Admin** creates **Games** within the series and activates one.
4. **Clients** open `/`, enter a team name, and start scoring.
5. **Dashboard** (`/dashboard`) shows live rankings auto-refreshing.
