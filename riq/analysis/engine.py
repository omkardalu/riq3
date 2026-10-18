"""Runs an analysis for one (resume, job) pair and persists the outcome."""
from __future__ import annotations

import logging

from .. import storage
from ..extensions import db
from ..models import (
    STATUS_COMPLETED, STATUS_FAILED, STATUS_PROCESSING, STATUS_UNSUPPORTED, Analysis, JobDescription, Resume, utcnow,
)
from . import extract as ex
from .scoring import SCORING_VERSION, analyze_text

log = logging.getLogger("riq.analysis")


def ensure_text(user_id: int, resume: Resume) -> None:
    """Extract (once) and cache the resume text. Failed extractions are retried on the next run."""
    if resume.extraction_status in (ex.STATUS_OK, ex.STATUS_SCANNED, ex.STATUS_EMPTY):
        return
    path = storage.path_for(user_id, resume.stored_name, resume.file_ext)
    if not path.exists():
        resume.extraction_status, resume.extraction_error = ex.STATUS_FAILED, "The stored file is missing."
        return
    result = ex.extract(path, resume.file_ext)
    resume.extraction_status = result.status
    resume.extraction_error = result.error
    resume.extracted_text = result.text or None
    resume.page_count = result.pages
    db.session.flush()


def run_analysis(user_id: int, resume: Resume, job: JobDescription) -> Analysis:
    """Idempotent: re-running replaces the previous result for the same resume + job."""
    analysis = db.session.query(Analysis).filter_by(resume_id=resume.id, job_id=job.id).first()
    if analysis is None:
        analysis = Analysis(user_id=user_id, resume_id=resume.id, job_id=job.id)
        db.session.add(analysis)
    analysis.status = STATUS_PROCESSING
    analysis.error_message = None
    analysis.score = analysis.matched_percentage = None
    analysis.matched_skills, analysis.missing_skills, analysis.details = [], [], {}
    db.session.commit()  # processing state is visible while work happens

    try:
        ensure_text(user_id, resume)
        if resume.extraction_status != ex.STATUS_OK:
            analysis.status = STATUS_UNSUPPORTED if resume.extraction_status == ex.STATUS_SCANNED else STATUS_FAILED
            analysis.error_message = resume.extraction_error or "The resume could not be read."
            analysis.details = {"candidate": {"name": _name_from_filename(resume.original_filename), "name_source": "filename"},
                                "extraction_status": resume.extraction_status}
        else:
            out = analyze_text(resume.extracted_text or "", resume.original_filename, list(job.required_skills), job.description)
            analysis.status = STATUS_COMPLETED
            analysis.score = out["score"]
            analysis.matched_percentage = out["matched_percentage"]
            analysis.matched_skills = out["matched_skills"]
            analysis.missing_skills = out["missing_skills"]
            analysis.details = out["details"]
    except Exception:  # noqa: BLE001 - a bad resume must not take the request down
        log.exception("analysis crashed resume=%s job=%s", resume.id, job.id)
        db.session.rollback()
        analysis = db.session.get(Analysis, analysis.id)
        analysis.status = STATUS_FAILED
        analysis.error_message = "Something went wrong while analyzing this resume."
    analysis.scoring_version = SCORING_VERSION
    analysis.completed_at = utcnow()
    db.session.commit()
    return analysis


def _name_from_filename(filename: str) -> str:
    import re

    return re.sub(r"[_\-.]+", " ", filename.rsplit(".", 1)[0]).strip().title() or "Unknown candidate"
