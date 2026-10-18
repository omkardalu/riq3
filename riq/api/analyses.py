from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, or_

from ..analysis.engine import run_analysis
from ..auth import get_owned_or_404, login_required
from ..errors import ApiError
from ..extensions import db, limiter
from ..models import ANALYSIS_STATUSES, Analysis, JobDescription, Resume
from ..validation import json_body

bp = Blueprint("analyses", __name__, url_prefix="/api/analyses")


def _int(value, name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(422, "validation_error", f"{name} must be a number.", {name: "Must be a number."})


@bp.post("")
@limiter.limit(lambda: current_app.config["ANALYSIS_RATE_LIMIT"])
@login_required
def create_analysis(user):
    data = json_body()
    job = get_owned_or_404(JobDescription, _int(data.get("job_id"), "job_id"), user)
    resume = get_owned_or_404(Resume, _int(data.get("resume_id"), "resume_id"), user)
    analysis = run_analysis(user.id, resume, job)
    return jsonify({"analysis": analysis.to_dict(full=True)}), 200


SORTS = {
    "score": Analysis.score, "date": Analysis.created_at, "matched": Analysis.matched_percentage,
}


@bp.get("")
@login_required
def list_analyses(user):
    q = db.session.query(Analysis).join(Resume, Analysis.resume_id == Resume.id).filter(Analysis.user_id == user.id)
    job_id = request.args.get("job_id")
    if job_id:
        get_owned_or_404(JobDescription, _int(job_id, "job_id"), user)
        q = q.filter(Analysis.job_id == int(job_id))
    status = request.args.get("status")
    if status:
        if status not in ANALYSIS_STATUSES:
            raise ApiError(422, "validation_error", "Unknown status filter.", {"status": "Unknown status."})
        q = q.filter(Analysis.status == status)
    search = (request.args.get("q") or "").strip()
    if search:
        like = f"%{search.lower()}%"
        q = q.filter(or_(func.lower(Resume.original_filename).like(like),
                         func.lower(Analysis.details["candidate"]["name"].as_string()).like(like)))
    sort = request.args.get("sort", "score")
    direction = request.args.get("order", "desc")
    if sort == "name":
        col = func.lower(func.coalesce(Analysis.details["candidate"]["name"].as_string(), Resume.original_filename))
    elif sort in SORTS:
        col = SORTS[sort]
    else:
        raise ApiError(422, "validation_error", "Unknown sort.", {"sort": "Use score, name, matched or date."})
    ordered = col.asc().nulls_last() if direction == "asc" else col.desc().nulls_last()
    total = q.count()
    limit = min(max(_int(request.args.get("limit", 200), "limit"), 1), 500)
    offset = max(_int(request.args.get("offset", 0), "offset"), 0)
    rows = q.order_by(ordered, Analysis.id.asc()).limit(limit).offset(offset).all()
    return jsonify({"analyses": [a.to_dict() for a in rows], "total": total})


@bp.get("/<int:analysis_id>")
@login_required
def get_analysis(user, analysis_id):
    return jsonify({"analysis": get_owned_or_404(Analysis, analysis_id, user).to_dict(full=True)})


@bp.delete("/<int:analysis_id>")
@login_required
def delete_analysis(user, analysis_id):
    db.session.delete(get_owned_or_404(Analysis, analysis_id, user))
    db.session.commit()
    return jsonify({"ok": True})
