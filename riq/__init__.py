"""Resume IQ application factory."""
from __future__ import annotations

import importlib
import logging
import re
import sys
import uuid
from pathlib import Path

from flask import Flask, g, has_request_context, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import BASE_DIR, get_config
from .errors import register_error_handlers
from .extensions import csrf, db, limiter, migrate

__version__ = "1.0.0"

CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
    "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
    "img-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


_REQ_ID_OK = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(g, "request_id", "-") if has_request_context() else "-"
        return True


def _configure_logging(app: Flask) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s"))
    root = logging.getLogger("riq")
    root.handlers[:] = [handler]
    root.setLevel(app.config["LOG_LEVEL"])
    root.propagate = False


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    config = get_config(config_name)
    config.validate()

    app = Flask(
        __name__,
        static_folder=str(BASE_DIR / "web" / "assets"),
        static_url_path="/assets",
    )
    app.config.from_object(config)
    if overrides:
        app.config.update(overrides)
    app.config["PAGES_DIR"] = str(BASE_DIR / "web" / "pages")
    if app.config["TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]

    _configure_logging(app)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    importlib.import_module(f"{__name__}.models")  # registers tables with SQLAlchemy metadata
    from .api import register_blueprints
    from .cli import register_cli
    from .web import web_bp

    register_blueprints(app)
    app.register_blueprint(web_bp)
    register_error_handlers(app)
    register_cli(app)

    @app.before_request
    def _request_id():
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming if _REQ_ID_OK.match(incoming) else uuid.uuid4().hex[:12]

    @app.after_request
    def _security_headers(resp):
        resp.headers["X-Request-ID"] = getattr(g, "request_id", "-")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Content-Security-Policy", CSP)
        if app.config["SESSION_COOKIE_SECURE"]:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        # private data must never be cached by browsers or proxies
        if request.path.startswith("/api/") or not request.path.startswith("/assets/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    app.logger.info("Resume IQ %s started (%s)", __version__, config.ENV_NAME)
    return app
