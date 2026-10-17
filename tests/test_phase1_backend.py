"""Phase 1: app boots, connects to PostgreSQL, schema comes from migrations, CRUD works."""
import pytest
from sqlalchemy.exc import IntegrityError

from riq import create_app
from riq.models import Analysis, JobDescription, Resume, User


def make_user(session, n=1):
    u = User(username=f"user{n}", email=f"user{n}@example.com", password_hash="x", company_name=f"Co {n}")
    session.add(u)
    session.commit()
    return u


def test_database_is_postgresql(db_session):
    assert db_session.get_bind().dialect.name == "postgresql"


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["database"] == "ok"


def test_health_reports_database_failure():
    bad = create_app("testing", {"SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://x:y@127.0.0.1:1/nope?connect_timeout=1"})
    r = bad.test_client().get("/api/health")
    assert r.status_code == 503
    assert r.get_json()["status"] == "degraded"


def test_unknown_api_route_returns_json_404(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == "not_found"


def test_unknown_page_returns_html_404(client):
    r = client.get("/nope.html")
    assert r.status_code == 404
    assert b"404" in r.data


def test_wrong_method_is_json(client):
    r = client.post("/api/health")
    assert r.status_code == 405
    assert r.get_json()["error"]["code"] == "method_not_allowed"


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"


def test_user_crud(db_session):
    u = make_user(db_session)
    assert u.id and u.is_active and u.pw_version == 1 and u.created_at
    u.company_name = "Renamed"
    db_session.commit()
    assert db_session.get(User, u.id).company_name == "Renamed"
    db_session.delete(u)
    db_session.commit()
    assert db_session.get(User, u.id) is None


def test_username_and_email_unique(db_session):
    make_user(db_session)
    db_session.add(User(username="user1", email="other@example.com", password_hash="x", company_name="A"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_resume_job_analysis_crud_and_cascade(db_session):
    u = make_user(db_session)
    r = Resume(user_id=u.id, original_filename="a.pdf", stored_name="uuid-1", file_ext="pdf", size_bytes=10, sha256="a" * 64)
    j = JobDescription(user_id=u.id, title="Dev", description="Build things", required_skills=["Python", "SQL"])
    db_session.add_all([r, j])
    db_session.commit()
    a = Analysis(user_id=u.id, resume_id=r.id, job_id=j.id, status="completed", score=81.5,
                 matched_percentage=50, matched_skills=["Python"], missing_skills=["SQL"],
                 details={"candidate": {"name": "A B"}}, scoring_version="v1")
    db_session.add(a)
    db_session.commit()

    fetched = db_session.get(Analysis, a.id)
    assert float(fetched.score) == 81.5
    assert fetched.matched_skills == ["Python"]
    assert fetched.to_dict()["candidate_name"] == "A B"
    assert fetched.to_dict()["unmatched_percentage"] == 50.0
    assert db_session.get(JobDescription, j.id).required_skills == ["Python", "SQL"]

    db_session.delete(u)  # deleting the account removes everything it owns
    db_session.commit()
    assert db_session.query(Resume).count() == 0
    assert db_session.query(JobDescription).count() == 0
    assert db_session.query(Analysis).count() == 0


def test_duplicate_resume_hash_per_user_rejected(db_session):
    u = make_user(db_session)
    for name in ("s1", "s2"):
        db_session.add(Resume(user_id=u.id, original_filename="a.pdf", stored_name=name, file_ext="pdf", size_bytes=1, sha256="b" * 64))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_same_hash_allowed_for_different_users(db_session):
    u1, u2 = make_user(db_session, 1), make_user(db_session, 2)
    for u, name in ((u1, "s1"), (u2, "s2")):
        db_session.add(Resume(user_id=u.id, original_filename="a.pdf", stored_name=name, file_ext="pdf", size_bytes=1, sha256="c" * 64))
    db_session.commit()


def test_db_constraints_reject_bad_score_and_status(db_session):
    u = make_user(db_session)
    r = Resume(user_id=u.id, original_filename="a.pdf", stored_name="s", file_ext="pdf", size_bytes=1, sha256="d" * 64)
    j = JobDescription(user_id=u.id, title="t", description="", required_skills=[])
    db_session.add_all([r, j])
    db_session.commit()
    db_session.add(Analysis(user_id=u.id, resume_id=r.id, job_id=j.id, status="bogus"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    db_session.add(Analysis(user_id=u.id, resume_id=r.id, job_id=j.id, status="completed", score=140))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_production_config_requires_secrets(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from riq.config import ProductionConfig

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        ProductionConfig.validate()
