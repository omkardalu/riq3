"""Phase 7 security review, expressed as tests (so it stays true)."""
import io
import logging
import stat
import time
import zipfile
from pathlib import Path

import pytest

from files import SAMPLE_LINES, make_pdf
from helpers import REG, login, make_account, register
from riq import create_app

PUBLIC_API = {"health.health", "health.csrf_token", "auth.register", "auth.login", "auth.logout", "auth.me"}


def api_rules(app):
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/"):
            yield rule


def build(app, rule):
    return app.url_map.bind("localhost").build(rule.endpoint, {a: 1 for a in rule.arguments})


def upload(c, data, name="r.pdf"):
    return c.post("/api/resumes", data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data")


def isolated_client(app, ip):
    c = app.test_client()
    c.environ_base["REMOTE_ADDR"] = ip  # the in-memory rate limiter keys on IP
    return c


# ---------------- authorization ----------------
def test_every_private_api_route_rejects_anonymous_requests(app, client):
    checked = 0
    for rule in api_rules(app):
        if rule.endpoint in PUBLIC_API:
            continue
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            r = client.open(build(app, rule), method=method, json={})
            assert r.status_code == 401, f"{method} {rule.rule} returned {r.status_code} to an anonymous caller"
            checked += 1
    assert checked >= 15  # guards against the loop silently checking nothing


def test_every_write_endpoint_requires_a_csrf_token():
    app = create_app("testing", {"WTF_CSRF_ENABLED": True})
    c = app.test_client()
    checked = 0
    for rule in api_rules(app):
        for method in rule.methods & {"POST", "PUT", "DELETE", "PATCH"}:
            r = c.open(build(app, rule), method=method, json={})
            assert r.status_code == 400 and r.get_json()["error"]["code"] == "csrf_failed", f"{method} {rule.rule}"
            checked += 1
    assert checked >= 12


def test_csrf_token_from_another_session_is_rejected():
    app = create_app("testing", {"WTF_CSRF_ENABLED": True})
    a, b = app.test_client(), app.test_client()
    token_a = a.get("/api/csrf").get_json()["csrf_token"]
    b.get("/api/csrf")
    r = b.post("/api/auth/login", json={"username": "x", "password": "y"}, headers={"X-CSRFToken": token_a})
    assert r.status_code == 400


# ---------------- sessions & cookies ----------------
def test_expired_session_is_rejected_by_the_server():
    app = create_app("testing", {"PERMANENT_SESSION_LIFETIME": 1})
    c = app.test_client()
    assert register(c).status_code == 201
    assert c.get("/api/auth/me").status_code == 200
    time.sleep(2.2)
    assert c.get("/api/auth/me").status_code == 401
    assert c.get("/profile.html").status_code == 302


def test_secure_cookie_and_hsts_when_configured_for_https():
    app = create_app("testing", {"SESSION_COOKIE_SECURE": True})
    r = register(app.test_client())
    cookie = next(h for h in r.headers.getlist("Set-Cookie") if h.startswith("riq_session"))
    for flag in ("Secure", "HttpOnly", "SameSite=Lax"):
        assert flag in cookie
    assert "max-age=31536000" in r.headers["Strict-Transport-Security"]


def test_session_cookie_is_signed_not_forgeable(client):
    register(client)
    client.set_cookie("riq_session", "eyJ1aWQiOjEsInB3diI6MX0.aaaaaa.bbbbbbbbbbbbbbbbbbbbbbbbbbb")
    assert client.get("/api/auth/me").status_code == 401


# ---------------- errors, logging, headers ----------------
def test_unhandled_errors_do_not_leak_internals():
    app = create_app("testing")

    @app.get("/api/_boom")
    def boom():
        raise RuntimeError("secret-internal-detail /etc/passwd")

    r = app.test_client().get("/api/_boom", headers={"X-Request-ID": "abc-123"})
    assert r.status_code == 500
    body = r.get_data(as_text=True)
    assert "secret-internal-detail" not in body and "Traceback" not in body and "RuntimeError" not in body
    assert r.get_json()["error"]["request_id"] == "abc-123" and r.headers["X-Request-ID"] == "abc-123"


def test_request_id_is_generated_and_sanitised(client):
    assert len(client.get("/api/health").headers["X-Request-ID"]) == 12
    r = client.get("/api/health", headers={"X-Request-ID": "bad id with spaces"})
    assert r.headers["X-Request-ID"] != "bad id with spaces" and " " not in r.headers["X-Request-ID"]


def test_logs_never_contain_passwords_or_typed_usernames(client, caplog):
    logger = logging.getLogger("riq")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG, logger="riq")
    try:
        register(client)
        client.post("/api/auth/logout")
        login(client, "pasted-my-password-here", "wrong-pass-Zq9")
        login(client, "abctech", "correct-horse-1")
        client.post("/api/profile/password", json={"current_password": "correct-horse-1", "new_password": "N3w-secret-pass-77",
                                                   "confirm_password": "N3w-secret-pass-77"})
    finally:
        logger.removeHandler(caplog.handler)
    text = caplog.text
    assert "failed login" in text                       # security events are logged...
    for secret in ("correct-horse-1", "wrong-pass-Zq9", "N3w-secret-pass-77", "pasted-my-password-here"):
        assert secret not in text                       # ...without secrets
    assert "hr@abc.example" not in text   # not even the email address


def test_no_cors_headers_so_other_sites_cannot_read_the_api(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in r.headers


@pytest.mark.parametrize("path", [
    "/.env", "/app.py", "/phases.md", "/riq/config.py", "/migrations/env.py", "/instance/uploads", "/.git/config",
    "/assets/../app.py", "/assets/%2e%2e/app.py", "/assets/..%2fapp.py", "/web/pages/login.html", "/requirements.txt",
])
def test_source_and_secrets_are_not_served(client, path):
    assert client.get(path).status_code == 404


# ---------------- uploads & file storage ----------------
def test_stored_files_and_folders_are_private(app):
    c = make_account(app, 1)
    assert upload(c, make_pdf(SAMPLE_LINES)).status_code == 201
    files = list(Path(app.config["UPLOAD_FOLDER"]).rglob("*.pdf"))
    assert len(files) == 1
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
    assert stat.S_IMODE(files[0].parent.stat().st_mode) == 0o700


def test_upload_size_limit_is_exact():
    app = create_app("testing", {"MAX_RESUME_BYTES": 5000, "MAX_CONTENT_LENGTH": 100_000})
    c = make_account(app, 1)
    at_limit = b"%PDF-1.4\n" + b"0" * (5000 - 9)
    assert len(at_limit) == 5000
    assert upload(c, at_limit, "ok.pdf").status_code == 201
    assert upload(c, at_limit + b"0", "big.pdf").status_code == 413


def test_zip_bomb_docx_is_rejected(app):
    c = make_account(app, 1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", b"\0" * (101 * 1024 * 1024))   # ~100 KB compressed, 101 MB unpacked
    assert buf.tell() < 1024 * 1024
    r = upload(c, buf.getvalue(), "bomb.docx")
    assert r.status_code == 415 and "too large once unpacked" in r.get_json()["error"]["message"]


def test_upload_and_analysis_endpoints_are_rate_limited():
    app = create_app("testing", {"RATELIMIT_ENABLED": True, "UPLOAD_RATE_LIMIT": "2 per minute", "ANALYSIS_RATE_LIMIT": "2 per minute"})
    c = isolated_client(app, "10.20.30.40")
    register(c)
    codes = [upload(c, make_pdf([f"resume {i}"]), f"{i}.pdf").status_code for i in range(4)]
    assert codes[:2] == [201, 201] and codes[2:] == [429, 429]
    codes = [c.post("/api/analyses", json={"job_id": 1, "resume_id": 1}).status_code for _ in range(4)]
    assert codes[-1] == 429


def test_register_is_rate_limited():
    app = create_app("testing", {"RATELIMIT_ENABLED": True, "REGISTER_RATE_LIMIT": "2 per hour"})
    c = isolated_client(app, "10.20.30.41")
    codes = [register(c, username=f"user{i}", email=f"user{i}@x.example").status_code for i in range(4)]
    assert codes[:2] == [201, 201] and codes[2:] == [429, 429]


# ---------------- database failures ----------------
BAD_DB = {"SQLALCHEMY_DATABASE_URI": "postgresql+psycopg://x:y@127.0.0.1:1/nope?connect_timeout=1"}


def test_database_outage_gives_clean_503s_not_stack_traces(app):
    good = make_account(app, 1)
    cookie = good.get_cookie("riq_session")
    down = create_app("testing", BAD_DB).test_client()

    r = down.post("/api/auth/login", json={"username": "a", "password": "b"})
    assert r.status_code == 503 and r.get_json()["error"]["code"] == "database_unavailable"
    assert "psycopg" not in r.get_data(as_text=True) and "127.0.0.1" not in r.get_data(as_text=True)

    down.set_cookie("riq_session", cookie.value)          # a valid session, but the database is gone
    assert down.get("/api/profile").status_code == 503
    page = down.get("/profile.html")
    assert page.status_code == 503 and b"temporarily unavailable" in page.data
    assert down.get("/login.html").status_code == 200       # static pages still work
    assert down.get("/api/health").status_code == 503
