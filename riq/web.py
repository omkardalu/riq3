"""Serves the HTML pages. Pages are static files; all data comes from /api/*."""
from __future__ import annotations

from urllib.parse import quote

from flask import Blueprint, abort, current_app, redirect, request, send_from_directory
from sqlalchemy.exc import SQLAlchemyError

from .auth import current_user
from .extensions import db

web_bp = Blueprint("web", __name__)

PUBLIC_PAGES = {"login", "create-account", "register", "features", "how-it-works"}
PROTECTED_PAGES = {"homepage", "upload", "ats-score", "profile", "edit-profile", "change-password"}
AUTH_PAGES = {"login", "create-account", "register"}  # pointless once signed in


def _signed_in(database_required: bool) -> bool:
    """Public pages must still load when the database is down (treated as signed out);
    protected pages need the database, so the error propagates to a clean 503."""
    try:
        return current_user() is not None
    except SQLAlchemyError:
        db.session.rollback()
        if database_required:
            raise
        return False


@web_bp.get("/")
def index():
    return redirect("/homepage.html" if _signed_in(False) else "/login.html")


@web_bp.get("/favicon.ico")
def favicon():
    return send_from_directory(current_app.static_folder + "/img", "favicon.svg", mimetype="image/svg+xml", max_age=86400)


@web_bp.get("/<page>.html")
def page(page: str):
    if page not in PUBLIC_PAGES | PROTECTED_PAGES:
        abort(404)
    signed_in = _signed_in(database_required=page in PROTECTED_PAGES)
    if page in PROTECTED_PAGES and not signed_in:
        return redirect(f"/login.html?next={quote(request.path)}")
    if page in AUTH_PAGES and signed_in:
        return redirect("/homepage.html")
    return send_from_directory(current_app.config["PAGES_DIR"], f"{page}.html", max_age=0)
