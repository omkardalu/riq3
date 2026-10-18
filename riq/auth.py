"""Session-based authentication helpers."""
from __future__ import annotations

from functools import wraps

from flask import g, session
from werkzeug.security import check_password_hash, generate_password_hash

from .errors import ApiError
from .extensions import db
from .models import User

# A real hash to compare against when the account does not exist (keeps timing uniform).
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(user: User | None, password: str) -> bool:
    if user is None:
        check_password_hash(_DUMMY_HASH, password)
        return False
    return check_password_hash(user.password_hash, password)


def login_user(user: User) -> None:
    session.clear()  # prevents session fixation; also rotates the CSRF token
    session["uid"] = user.id
    session["pwv"] = user.pw_version
    session.permanent = True


def logout_user() -> None:
    session.clear()


def current_user() -> User | None:
    """The signed-in user, or None. Sessions are invalid if the account was disabled/deleted
    or the password changed since the session was created."""
    if "_riq_user" in g.__dict__:
        return g._riq_user
    user = None
    uid = session.get("uid")
    if uid is not None:
        candidate = db.session.get(User, uid)
        if candidate and candidate.is_active and candidate.pw_version == session.get("pwv"):
            user = candidate
        else:
            session.clear()
    g._riq_user = user
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            raise ApiError(401, "unauthorized", "Your session has expired. Please sign in again.")
        return fn(user, *args, **kwargs)

    return wrapper


def get_owned_or_404(model, obj_id: int, user: User):
    """Fetch a row only if it belongs to `user`. Foreign rows look exactly like missing rows."""
    obj = db.session.get(model, obj_id)
    if obj is None or obj.user_id != user.id:
        raise ApiError(404, "not_found", "That item was not found.")
    return obj
