"""Resume IQ application factory."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from flask import Flask, request
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


def _configure_logging(app: Flask) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
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

    from . import models  # noqa: F401  (register tables with SQLAlchemy metadata)
    from .api import register_blueprints
    from .web import web_bp

    register_blueprints(app)
    app.register_blueprint(web_bp)
    register_error_handlers(app)

    @app.after_request
    def _security_headers(resp):
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
