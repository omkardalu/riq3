import logging

from flask import Blueprint, jsonify
from sqlalchemy.exc import IntegrityError

from ..auth import hash_password, login_required, verify_password
from ..errors import ApiError
from ..extensions import db
from ..validation import json_body, raise_if, validate_account_fields, validate_password
from .auth import _taken
from flask import session

bp = Blueprint("profile", __name__, url_prefix="/api/profile")
log = logging.getLogger("riq.profile")


@bp.get("")
@login_required
def get_profile(user):
    return jsonify({"user": user.to_dict()})


@bp.put("")
@login_required
def update_profile(user):
    clean, errors = validate_account_fields(json_body())
    raise_if(errors)
    duplicates = _taken(clean, exclude_id=user.id)
    if duplicates:
        raise ApiError(409, "duplicate_account", "That username or email is already in use.", duplicates)
    for key, value in clean.items():
        setattr(user, key, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError(409, "duplicate_account", "That username or email is already in use.",
                       {"username": "That username or email is already in use."})
    return jsonify({"user": user.to_dict()})


@bp.post("/password")
@login_required
def change_password(user):
    data = json_body()
    errors: dict[str, str] = {}
    current, new = data.get("current_password"), data.get("new_password")
    if not isinstance(current, str) or not current:
        errors["current_password"] = "Please enter your current password."
    validate_password(new, errors, "new_password", user.username)
    if "new_password" not in errors and data.get("confirm_password") != new:
        errors["confirm_password"] = "Passwords do not match."
    raise_if(errors)
    if not verify_password(user, current):
        raise ApiError(403, "wrong_password", "Current password is incorrect.",
                       {"current_password": "Current password is incorrect."})
    if new == current:
        raise ApiError(422, "validation_error", "Please correct the highlighted fields.",
                       {"new_password": "New password must be different from the current one."})
    user.password_hash = hash_password(new)
    user.pw_version += 1  # signs out every other session
    db.session.commit()
    session["pwv"] = user.pw_version  # keep this one
    log.info("password changed id=%s", user.id)
    return jsonify({"ok": True})
