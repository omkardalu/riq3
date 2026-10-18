import re

from flask import Blueprint, current_app, jsonify
from sqlalchemy import func

from ..auth import get_owned_or_404, login_required
from ..extensions import db
from ..models import Analysis, JobDescription
from ..validation import json_body, raise_if, text

bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")


def parse_skills(raw, errors: dict, cfg) -> list[str]:
    """Accept a list or a comma/newline separated string; trim, de-duplicate (case-insensitive)."""
    if isinstance(raw, str):
        raw = re.split(r"[,\n;]", raw)
    if not isinstance(raw, list):
        errors["required_skills"] = "Enter at least one required skill."
        return []
    seen, out = set(), []
    for item in raw:
        if not isinstance(item, str):
            errors["required_skills"] = "Skills must be text."
            return []
        s = re.sub(r"\s+", " ", item).strip()
        if not s or s.lower() in seen:
            continue
        if len(s) > cfg["MAX_SKILL_LENGTH"]:
            errors["required_skills"] = f"'{s[:20]}...' is too long (max {cfg['MAX_SKILL_LENGTH']} characters per skill)."
            return []
        seen.add(s.lower())
        out.append(s)
    if not out:
        errors["required_skills"] = "Enter at least one required skill."
    elif len(out) > cfg["MAX_REQUIRED_SKILLS"]:
        errors["required_skills"] = f"At most {cfg['MAX_REQUIRED_SKILLS']} skills are allowed."
    return out


@bp.post("")
@login_required
def create_job(user):
    cfg = current_app.config
    data = json_body()
    errors: dict[str, str] = {}
    skills = parse_skills(data.get("required_skills"), errors, cfg)
    description = text(data, "description")
    title = text(data, "title") or "Untitled role"
    if len(description) > cfg["MAX_JOB_DESCRIPTION_CHARS"]:
        errors["description"] = f"Job description is too long (max {cfg['MAX_JOB_DESCRIPTION_CHARS']} characters)."
    if len(title) > 150:
        errors["title"] = "Title must be at most 150 characters."
    raise_if(errors)
    job = JobDescription(user_id=user.id, title=title, description=description, required_skills=skills)
    db.session.add(job)
    db.session.commit()
    return jsonify({"job": job.to_dict()}), 201


@bp.get("")
@login_required
def list_jobs(user):
    counts = dict(
        db.session.query(Analysis.job_id, func.count(Analysis.id)).filter(Analysis.user_id == user.id).group_by(Analysis.job_id).all()
    )
    jobs = db.session.query(JobDescription).filter_by(user_id=user.id).order_by(JobDescription.created_at.desc(), JobDescription.id.desc()).all()
    return jsonify({"jobs": [{**j.to_dict(), "analysis_count": counts.get(j.id, 0)} for j in jobs]})


@bp.get("/<int:job_id>")
@login_required
def get_job(user, job_id):
    return jsonify({"job": get_owned_or_404(JobDescription, job_id, user).to_dict()})


@bp.delete("/<int:job_id>")
@login_required
def delete_job(user, job_id):
    db.session.delete(get_owned_or_404(JobDescription, job_id, user))
    db.session.commit()
    return jsonify({"ok": True})
