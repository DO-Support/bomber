"""FastAPI application: the live job-material-variance dashboard.

Replaces the old stdlib `serve.py`. Sits behind nginx (TLS + reverse proxy) and
runs under gunicorn/uvicorn. App-level session login gates every data route.

Run locally (dev):
    uvicorn jobvariance.app:app --reload --port 8765
Production (in container):
    gunicorn jobvariance.app:app -c gunicorn_conf.py
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from . import auth
from .build import render_html
from .config import Settings, get_settings
from .db import get_engine

_TEMPLATES = Path(__file__).parent / "templates"
_SUBTITLE = "Standard vs actual issued (Rand + units) · iSync live · pick any date range"


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _login_page(error: str | None = None) -> str:
    html = (_TEMPLATES / "login.html").read_text(encoding="utf-8")
    banner = ""
    if error:
        banner = (
            '<div class="mb-4 rounded-lg bg-rose-100 text-rose-700 '
            'dark:bg-rose-500/15 dark:text-rose-300 text-sm px-4 py-2.5">'
            f"{error}</div>"
        )
    return html.replace("__ERROR__", banner)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Job Material Variance", docs_url=None, redoc_url=None)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="jmv_session",
        max_age=settings.session_max_age,
        https_only=settings.session_https_only,
        same_site="lax",
    )

    # --- health: unprotected, cheap. ?deep=1 also pings the DB. ---
    @app.get("/healthz")
    def healthz(deep: int = 0) -> JSONResponse:
        if deep:
            try:
                import sqlalchemy as sa

                with get_engine().connect() as c:
                    c.execute(sa.text("SELECT 1"))
            except Exception as e:  # noqa: BLE001
                return JSONResponse(
                    {"status": "degraded", "db": str(e)},
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return JSONResponse({"status": "ok", "db": "ok"})
        return JSONResponse({"status": "ok"})

    # --- auth ---
    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        if request.session.get("user"):
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        return HTMLResponse(_login_page())

    @app.post("/login", response_class=HTMLResponse)
    def login_submit(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
    ):
        if auth.verify_credentials(username, password, settings):
            request.session["user"] = username
            return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        return HTMLResponse(
            _login_page("Invalid username or password."),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    @app.post("/logout")
    @app.get("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    # --- dashboard (protected) ---
    @app.get("/", response_class=HTMLResponse)
    @app.get("/index.html", response_class=HTMLResponse)
    def index(request: Request):
        if not request.session.get("user"):
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        html = render_html([], "Job Material Variance", _SUBTITLE, live=True)
        return HTMLResponse(html)

    # --- data (protected) ---
    @app.get("/data")
    def data(request: Request, _user: str = Depends(auth.current_user)) -> JSONResponse:
        params = request.query_params
        try:
            d_from = _parse_date(params["from"])
            d_to = _parse_date(params["to"])
        except (KeyError, ValueError):
            return JSONResponse(
                {"error": "from and to required as YYYY-MM-DD"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if d_to < d_from:
            return JSONResponse(
                {"error": "to must be on or after from"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        # Guardrail against pathological full-history scans.
        if d_to - d_from > timedelta(days=400):
            return JSONResponse(
                {"error": "range too large (max 400 days)"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from .cache import get_variance_payload

            payload = get_variance_payload(get_engine(), d_from, d_to)
            return JSONResponse(payload)
        except Exception as e:  # noqa: BLE001  # surface DB/query errors to the page
            return JSONResponse(
                {"error": str(e)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # 401 on /data → JSON the frontend can detect and redirect on.
    @app.exception_handler(status.HTTP_401_UNAUTHORIZED)
    def _unauth(request: Request, exc):  # noqa: ANN001
        return JSONResponse({"error": "unauthenticated", "login": "/login"},
                            status_code=status.HTTP_401_UNAUTHORIZED)

    return app


app = create_app()
