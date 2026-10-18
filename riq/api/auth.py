import logging
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify
from flask_wtf.csrf import generate_csrf
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from ..auth import current_user, hash_password, login_required, login_user, logout_user, verify_password
from ..errors import ApiError
from ..extensions import db, limiter
from ..models import User
from ..validation import json_body, raise_if, text, validate_account_fields, validate_password

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
log = logging.getLogger("riq.auth")


def _login_limit():
    return current_app.config["LOGIN_RATE_LIMIT"]


def _register_limit():
    return current_app.config["REGISTER_RATE_LIMIT"]


def _taken(clean: dict, exclude_id: int | None = None) -> dict[str, str]:
    errors = {}
    q = db.session.query(User.id)
    if exclude_id is not None:
        q = q.filter(User.id != exclude_id)
    if q.filter(User.username == clean["username"]).first():
        errors["username"] = "That username is already taken."
    q = db.session.query(User.id)
    if exclude_id is not None:
        q = q.filter(User.id != exclude_id)
    if q.filter(func.lower(User.email) == clean["email"]).first():
        errors["email"] = "An account with this email already exists."
    return errors


@bp.post("/register")
@limiter.limit(_register_limit)
def register():
    data = json_body()
    clean, errors = validate_account_fields(data)
    password = data.get("password")
    validate_password(password, errors, "password", clean["username"])
    if "password" not in errors and data.get("confirm_password") != password:
        errors["confirm_password"] = "Passwords do not match."
    raise_if(errors)  # 422: malformed input
    duplicates = _taken(clean)
    if duplicates:  # 409: well-formed but already registered
        raise ApiError(409, "duplicate_account", "That username or email is already registered.", duplicates)

    user = User(password_hash=hash_password(password), **clean)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:  # lost a race with a concurrent registration
        db.session.rollback()
        raise ApiError(409, "duplicate_account", "That username or email is already registered.",
                       {"username": "That username or email is already registered."})
    login_user(user)
    log.info("account registered id=%s", user.id)
    return jsonify({"user": user.to_dict(), "csrf_token": generate_csrf()}), 201


@bp.post("/login")
@limiter.limit(_login_limit)
def login():
    data = json_body()
    identifier = text(data, "username").lstrip("@").lower()
    password = data.get("password")
    if not identifier or not isinstance(password, str) or not password:
        raise ApiError(422, "validation_error", "Please enter your username and password.",
                       {"username": "Required" if not identifier else "", "password": "Required" if not password else ""})
    user = db.session.query(User).filter(or_(User.username == identifier, func.lower(User.email) == identifier)).first()
    if not verify_password(user, password) or not user.is_active:
        log.warning("failed login for identifier=%r", identifier[:40])
        raise ApiError(401, "invalid_credentials", "Incorrect username or password.")
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()
    login_user(user)
    return jsonify({"user": user.to_dict(), "csrf_token": generate_csrf()})


@bp.post("/logout")
def logout():
    logout_user()
    return jsonify({"ok": True, "csrf_token": generate_csrf()})


@bp.get("/me")
def me():
    user = current_user()
    if user is None:
        raise ApiError(401, "unauthorized", "You are not signed in.")
    return jsonify({"user": user.to_dict()})
