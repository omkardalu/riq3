import logging

from flask import Blueprint, current_app, jsonify, request, send_file
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .. import storage
from ..auth import get_owned_or_404, login_required
from ..errors import ApiError
from ..extensions import db
from ..models import Resume

bp = Blueprint("resumes", __name__, url_prefix="/api/resumes")
log = logging.getLogger("riq.resumes")


def _quota(user) -> dict:
    used = db.session.query(func.coalesce(func.sum(Resume.size_bytes), 0)).filter(Resume.user_id == user.id).scalar()
    return {
        "used_bytes": int(used),
        "limit_bytes": current_app.config["USER_STORAGE_QUOTA_BYTES"],
        "max_file_bytes": current_app.config["MAX_RESUME_BYTES"],
        "allowed_types": list(current_app.config["ALLOWED_RESUME_EXTENSIONS"]),
    }


@bp.get("")
@login_required
def list_resumes(user):
    rows = db.session.query(Resume).filter_by(user_id=user.id).order_by(Resume.created_at.desc(), Resume.id.desc()).all()
    return jsonify({"resumes": [r.to_dict() for r in rows], "quota": _quota(user)})


@bp.post("")
@login_required
def upload_resume(user):
    cfg = current_app.config
    file = request.files.get("file")
    if file is None or not file.filename:
        raise ApiError(400, "no_file", "Choose a resume file to upload.")

    name = storage.clean_display_name(file.filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext == "doc":
        raise ApiError(415, "unsupported_type", "Legacy .doc files are not supported. Save the resume as .docx or PDF and try again.")
    if ext not in cfg["ALLOWED_RESUME_EXTENSIONS"]:
        raise ApiError(415, "unsupported_type", "Only PDF and DOCX resumes are supported.")

    limit = cfg["MAX_RESUME_BYTES"]
    data = file.stream.read(limit + 1)  # never read more than the limit
    if len(data) > limit:
        raise ApiError(413, "file_too_large", f"'{name}' is larger than the {limit / (1024 * 1024):g} MB limit.")
    if not data:
        raise ApiError(422, "empty_file", f"'{name}' is empty.")
    problem = storage.sniff_type(data, ext)
    if problem:
        raise ApiError(415, "invalid_file", problem)

    digest = storage.sha256_hex(data)
    existing = db.session.query(Resume).filter_by(user_id=user.id, sha256=digest).first()
    if existing:
        raise ApiError(409, "duplicate_file", f"This resume was already uploaded as '{existing.original_filename}'.",
                       {"existing_id": existing.id})

    quota = _quota(user)
    if quota["used_bytes"] + len(data) > quota["limit_bytes"]:
        raise ApiError(413, "quota_exceeded", "Your resume storage is full. Delete some resumes to free up space.")

    stored = storage.save_bytes(user.id, ext, data)
    resume = Resume(user_id=user.id, original_filename=name, stored_name=stored, file_ext=ext,
                    size_bytes=len(data), sha256=digest)
    db.session.add(resume)
    try:
        db.session.commit()
    except IntegrityError:  # concurrent duplicate upload
        db.session.rollback()
        storage.delete_file(user.id, stored, ext)
        raise ApiError(409, "duplicate_file", "This resume was already uploaded.")
    except Exception:
        db.session.rollback()
        storage.delete_file(user.id, stored, ext)  # no orphan files if the DB write fails
        raise
    log.info("resume uploaded id=%s user=%s bytes=%s", resume.id, user.id, len(data))
    return jsonify({"resume": resume.to_dict(), "quota": _quota(user)}), 201


@bp.get("/<int:resume_id>")
@login_required
def get_resume(user, resume_id):
    return jsonify({"resume": get_owned_or_404(Resume, resume_id, user).to_dict()})


@bp.get("/<int:resume_id>/file")
@login_required
def download_resume(user, resume_id):
    r = get_owned_or_404(Resume, resume_id, user)
    path = storage.path_for(user.id, r.stored_name, r.file_ext)
    if not path.exists():
        raise ApiError(404, "file_missing", "The stored file is missing.")
    return send_file(path, as_attachment=True, download_name=r.original_filename)


def _remove(user, resume: Resume) -> None:
    storage.delete_file(user.id, resume.stored_name, resume.file_ext)
    db.session.delete(resume)


@bp.delete("/<int:resume_id>")
@login_required
def delete_resume(user, resume_id):
    _remove(user, get_owned_or_404(Resume, resume_id, user))
    db.session.commit()
    return jsonify({"ok": True, "quota": _quota(user)})


@bp.delete("")
@login_required
def delete_all(user):
    rows = db.session.query(Resume).filter_by(user_id=user.id).all()
    for r in rows:
        _remove(user, r)
    db.session.commit()
    return jsonify({"ok": True, "deleted": len(rows), "quota": _quota(user)})
