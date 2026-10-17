from flask import Blueprint, jsonify
from flask_wtf.csrf import generate_csrf
from sqlalchemy import text

from .. import __version__
from ..extensions import csrf, db

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
@csrf.exempt
def health():
    """Liveness + database connectivity. Returns 503 when the database is unreachable."""
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok", "database": "ok", "version": __version__})
    except Exception:  # noqa: BLE001 - any failure means "not healthy"
        db.session.rollback()
        return jsonify({"status": "degraded", "database": "error", "version": __version__}), 503


@bp.get("/csrf")
def csrf_token():
    """Token the frontend sends back in the X-CSRFToken header on every write."""
    return jsonify({"csrf_token": generate_csrf()})
