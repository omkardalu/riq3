"""Phase 7 operations: migrations, production configuration, real gunicorn run, demo walkthrough."""
import http.client
import io
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from flask_migrate import check, downgrade, upgrade
from sqlalchemy import inspect

from helpers import login
from riq.config import BASE_DIR, ProductionConfig
from riq.demo import DEMO_JOB_DESCRIPTION, DEMO_JOB_TITLE, DEMO_SKILLS, RESUMES

MIGRATIONS = str(BASE_DIR / "migrations")
TABLES = {"users", "resumes", "job_descriptions", "analyses"}


# ---------------- migrations ----------------
def test_migrations_match_the_models(app):
    """`flask db check` fails if someone edits a model without writing a migration."""
    with app.app_context():
        check(directory=MIGRATIONS)


def test_migrations_roundtrip_from_empty(app):
    from riq.extensions import db

    with app.app_context():
        downgrade(directory=MIGRATIONS, revision="base")
        assert not (TABLES & set(inspect(db.engine).get_table_names()))
        upgrade(directory=MIGRATIONS)
        assert TABLES <= set(inspect(db.engine).get_table_names())
        check(directory=MIGRATIONS)


# ---------------- production configuration ----------------
def test_production_config_accepts_a_proper_setup(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/riq")
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "k" * 48)
    monkeypatch.setattr(ProductionConfig, "SESSION_COOKIE_SECURE", True)
    ProductionConfig.validate()
    assert ProductionConfig.DEBUG is False and ProductionConfig.TESTING is False


@pytest.mark.parametrize("secret,secure,has_db,expect", [
    ("dev-only-insecure-secret-change-me", True, True, "SECRET_KEY"),
    ("short", True, True, "SECRET_KEY"),
    ("k" * 48, False, True, "SESSION_COOKIE_SECURE"),
    ("k" * 48, True, False, "DATABASE_URL"),
])
def test_production_config_rejects_unsafe_setups(monkeypatch, secret, secure, has_db, expect):
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", secret)
    monkeypatch.setattr(ProductionConfig, "SESSION_COOKIE_SECURE", secure)
    if has_db:
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/riq")
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match=expect):
        ProductionConfig.validate()


def test_no_secrets_committed_to_the_repository():
    out = subprocess.run(["git", "ls-files"], cwd=BASE_DIR, capture_output=True, text=True).stdout.split()
    assert ".env" not in out and not any(f.startswith("instance/") for f in out)
    assert not any(f.endswith((".pem", ".key", ".sqlite", ".db")) for f in out)
    env_example = (BASE_DIR / ".env.example").read_text()
    assert "change-me" in env_example                       # placeholder, not a real secret
    assert ".env" in (BASE_DIR / ".gitignore").read_text()


# ---------------- real gunicorn in production mode ----------------
def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    return resp, data


def test_gunicorn_production_smoke(app):
    port = _free_port()
    env = {**os.environ, "APP_ENV": "production", "SECRET_KEY": "s3cr3t-" + "x" * 48, "PORT": str(port), "WEB_CONCURRENCY": "2",
           "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", "postgresql://riq:riq@localhost:5432/riq_test"),
           "SESSION_COOKIE_SECURE": "true", "UPLOAD_FOLDER": str(Path(app.config["UPLOAD_FOLDER"]) / "gunicorn")}
    proc = subprocess.Popen([sys.executable, "-m", "gunicorn", "-c", "gunicorn.conf.py", "--bind", f"127.0.0.1:{port}", "app:app"],
                            cwd=BASE_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                resp, data = _request(port, "GET", "/api/health")
                if resp.status == 200:
                    break
            except OSError:
                time.sleep(0.25)
        else:
            raise AssertionError("gunicorn did not become healthy:\n" + proc.stdout.read(4000).decode(errors="replace"))
        assert json.loads(data)["database"] == "ok"
        assert resp.getheader("Strict-Transport-Security") and resp.getheader("X-Request-ID")

        resp, data = _request(port, "GET", "/api/csrf")
        token = json.loads(data)["csrf_token"]
        cookie = resp.getheader("Set-Cookie")
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
        session = cookie.split(";")[0]

        # CSRF is enforced in production mode (no token -> rejected)
        resp, _ = _request(port, "POST", "/api/auth/login", {"username": "a", "password": "b"},
                           {"Content-Type": "application/json", "Cookie": session})
        assert resp.status == 400

        reg = {"company_name": "Prod Smoke", "email": "smoke@example.com", "phone": "+91 90000 12345", "address": "1 Test Road",
               "industry": "IT", "username": "smokeuser", "password": "smoke-pass-123", "confirm_password": "smoke-pass-123"}
        resp, data = _request(port, "POST", "/api/auth/register", reg,
                              {"Content-Type": "application/json", "X-CSRFToken": token, "Cookie": session})
        assert resp.status == 201, data
        resp, _ = _request(port, "GET", "/profile.html")                       # anonymous -> redirected to login
        assert resp.status == 302 and "/login.html" in resp.getheader("Location")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


# ---------------- the documented demo ----------------
def test_demo_command_and_walkthrough_produce_the_documented_results(app, tmp_path):
    runner = app.test_cli_runner()
    out_dir = tmp_path / "demo_resumes"
    result = runner.invoke(args=["demo", "--output", str(out_dir)])
    assert result.exit_code == 0, result.output
    assert "username 'demo'" in result.output and len(list(out_dir.iterdir())) == len(RESUMES)

    c = app.test_client()
    assert login(c, "demo", "Demo-Pass-123").status_code == 200
    ids = {}
    for f in sorted(out_dir.iterdir()):
        r = c.post("/api/resumes", data={"file": (io.BytesIO(f.read_bytes()), f.name)}, content_type="multipart/form-data")
        assert r.status_code == 201, (f.name, r.get_json())
        ids[f.name] = r.get_json()["resume"]["id"]
    job = c.post("/api/jobs", json={"title": DEMO_JOB_TITLE, "required_skills": DEMO_SKILLS,
                                    "description": DEMO_JOB_DESCRIPTION}).get_json()["job"]
    for rid in ids.values():
        assert c.post("/api/analyses", json={"job_id": job["id"], "resume_id": rid}).status_code == 200

    rows = c.get(f"/api/analyses?job_id={job['id']}").get_json()["analyses"]
    got = [(r["candidate_name"], r["status"], r["score"]) for r in rows]
    # These numbers are documented in DEMO.md. If scoring changes, update both.
    assert got == [("Anita Rao", "completed", 91.76), ("Vikram Shah", "completed", 54.35),
                   ("Meera Iyer", "completed", 26.35), ("Rohan Das", "completed", 7.84), ("Scanned Resume", "unsupported", None)]


def test_demo_command_is_idempotent_and_refuses_production(app, tmp_path):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["demo", "--output", str(tmp_path / "a")]).exit_code == 0
    again = runner.invoke(args=["demo", "--output", str(tmp_path / "a"), "--password", "Another-Pass-9"])
    assert again.exit_code == 0 and "password reset" in again.output
    assert login(app.test_client(), "demo", "Another-Pass-9").status_code == 200
    app.config["ENV_NAME"] = "production"
    try:
        r = runner.invoke(args=["demo", "--output", str(tmp_path / "b")])
        assert r.exit_code != 0 and "production" in r.output
        assert not (tmp_path / "b").exists()
    finally:
        app.config["ENV_NAME"] = "testing"
