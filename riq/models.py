"""Database models: users, resumes, job descriptions and analyses."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric,
    String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .extensions import db

# JSONB on PostgreSQL, plain JSON elsewhere.
JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Analysis lifecycle
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_UNSUPPORTED = "unsupported"  # e.g. scanned PDF without a text layer
ANALYSIS_STATUSES = (STATUS_PENDING, STATUS_PROCESSING, STATUS_COMPLETED, STATUS_FAILED, STATUS_UNSUPPORTED)

# Text extraction outcome stored on a resume
EXTRACTION_STATUSES = ("pending", "ok", "empty", "scanned", "failed")


class User(db.Model):
    """A company account (the recruiter side of Resume IQ)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)  # stored lowercase
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)  # stored lowercase
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    address: Mapped[str] = mapped_column(Text, nullable=False, default="")
    industry: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # bumped on password change; sessions carrying an older value are rejected
    pw_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    jobs = relationship("JobDescription", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    analyses = relationship("Analysis", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "company_name": self.company_name,
            "phone": self.phone,
            "address": self.address,
            "industry": self.industry,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Resume(db.Model):
    __tablename__ = "resumes"
    __table_args__ = (
        UniqueConstraint("user_id", "sha256", name="uq_resume_user_sha256"),
        CheckConstraint("size_bytes >= 0", name="ck_resume_size_nonneg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # uuid on disk, never user-controlled
    file_ext: Mapped[str] = mapped_column(String(8), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extraction_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    extraction_error: Mapped[str | None] = mapped_column(String(255))
    page_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    user = relationship("User", back_populates="resumes")
    analyses = relationship("Analysis", back_populates="resume", cascade="all, delete-orphan", passive_deletes=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.original_filename,
            "type": self.file_ext,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "extraction_status": self.extraction_status,
            "uploaded_at": self.created_at.isoformat() if self.created_at else None,
        }


class JobDescription(db.Model):
    __tablename__ = "job_descriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False, default="Untitled role")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    required_skills: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    user = relationship("User", back_populates="jobs")
    analyses = relationship("Analysis", back_populates="job", cascade="all, delete-orphan", passive_deletes=True)

    def to_dict(self, with_counts: bool = False) -> dict:
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "required_skills": list(self.required_skills or []),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        return data


class Analysis(db.Model):
    __tablename__ = "analyses"
    __table_args__ = (
        UniqueConstraint("resume_id", "job_id", name="uq_analysis_resume_job"),
        CheckConstraint(
            "status IN ('pending','processing','completed','failed','unsupported')", name="ck_analysis_status"
        ),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_analysis_score_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_PENDING)
    score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    matched_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2))
    matched_skills: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    missing_skills: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    details: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)  # candidate info, breakdown, explanation
    scoring_version: Mapped[str | None] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user = relationship("User", back_populates="analyses")
    resume = relationship("Resume", back_populates="analyses")
    job = relationship("JobDescription", back_populates="analyses")

    def to_dict(self, full: bool = False) -> dict:
        data = {
            "id": self.id,
            "resume_id": self.resume_id,
            "job_id": self.job_id,
            "filename": self.resume.original_filename if self.resume else None,
            "status": self.status,
            "score": float(self.score) if self.score is not None else None,
            "matched_percentage": float(self.matched_percentage) if self.matched_percentage is not None else None,
            "unmatched_percentage": (
                round(100 - float(self.matched_percentage), 2) if self.matched_percentage is not None else None
            ),
            "matched_skills": list(self.matched_skills or []),
            "missing_skills": list(self.missing_skills or []),
            "scoring_version": self.scoring_version,
            "error_message": self.error_message,
            "candidate_name": (self.details or {}).get("candidate", {}).get("name"),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if full:
            data["details"] = self.details or {}
            data["job"] = self.job.to_dict() if self.job else None
        return data
