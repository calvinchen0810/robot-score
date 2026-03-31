from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from sqlalchemy import inspect, text
from database import engine, Base
from routes import router as api_router

# Create tables on startup
Base.metadata.create_all(bind=engine)

# Lightweight migration: add missing columns
with engine.connect() as conn:
    cols = [c["name"] for c in inspect(engine).get_columns("games")]
    if "paused_remaining" not in cols:
        conn.execute(text("ALTER TABLE games ADD COLUMN paused_remaining FLOAT"))
        conn.commit()

    # Add round_id to team_scores if missing
    ts_cols = [c["name"] for c in inspect(engine).get_columns("team_scores")]
    if "round_id" not in ts_cols:
        conn.execute(text("ALTER TABLE team_scores ADD COLUMN round_id INTEGER"))
        conn.commit()

app = FastAPI(title="Robot Score")

app.include_router(api_router)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def client_page(request: Request):
    return templates.TemplateResponse(request, "client.html")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse(request, "admin.html")
