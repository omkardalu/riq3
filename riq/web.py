"""Serves the HTML pages. Pages are static files; all data comes from /api/*."""
from __future__ import annotations

from flask import Blueprint, current_app, redirect, send_from_directory, abort

web_bp = Blueprint("web", __name__)

PUBLIC_PAGES = {
    "login", "create-account", "register", "features", "how-it-works",
}
PROTECTED_PAGES = {
    "homepage", "upload", "ats-score", "profile", "edit-profile", "change-password",
}


@web_bp.get("/")
def index():
    return redirect("/login.html")


@web_bp.get("/<page>.html")
def page(page: str):
    if page not in PUBLIC_PAGES | PROTECTED_PAGES:
        abort(404)
    return send_from_directory(current_app.config["PAGES_DIR"], f"{page}.html", max_age=0)
