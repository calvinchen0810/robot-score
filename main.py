from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from routes import router as api_router


def _run_migrations():
    from alembic.config import Config
    from alembic import command
    import os, logging
    logging.getLogger("alembic").setLevel(logging.WARNING)
    alembic_cfg = Config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


_run_migrations()

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
