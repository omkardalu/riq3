import pytest

from helpers import REG, login, register
from riq import create_app
from riq.models import User


def test_register_creates_account_and_session(client, db_session):
    r = register(client)
    assert r.status_code == 201
    user = r.get_json()["user"]
    assert user["username"] == "abctech" and "password" not in str(user)
    assert client.get("/api/auth/me").get_json()["user"]["email"] == "hr@abc.example"
    assert db_session.query(User).count() == 1


def test_password_is_hashed_never_plaintext(client, db_session):
    register(client)
    stored = db_session.query(User).one().password_hash
    assert "correct-horse-1" not in stored
    assert stored.startswith(("scrypt:", "pbkdf2:"))


def test_session_cookie_flags(client):
    r = register(client)
    cookie = next(h for h in r.headers.getlist("Set-Cookie") if h.startswith("riq_session"))
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


@pytest.mark.parametrize("field,value,key", [
    ("company_name", "A", "company_name"),
    ("email", "not-an-email", "email"),
    ("phone", "abc", "phone"),
    ("industry", "Piracy", "industry"),
    ("username", "x", "username"),
    ("username", "bad name!", "username"),
    ("password", "short", "password"),
])
def test_register_validation(client, field, value, key):
    body = {**REG, field: value}
    if field == "password":
        body["confirm_password"] = value
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 422
    assert key in r.get_json()["error"]["fields"]


def test_register_password_mismatch(client):
    r = register(client, confirm_password="different-pass-1")
    assert r.status_code == 422
    assert "confirm_password" in r.get_json()["error"]["fields"]


def test_register_rejects_non_json(client):
    r = client.post("/api/auth/register", data="x=1")
    assert r.status_code == 400


def test_duplicate_username_and_email(client):
    assert register(client).status_code == 201
    other = client.application.test_client()
    r = register(other, email="new@abc.example")
    assert r.status_code == 409 and "username" in r.get_json()["error"]["fields"]
    r = register(other, username="different", email="HR@ABC.EXAMPLE")  # case-insensitive
    assert r.status_code == 409 and "email" in r.get_json()["error"]["fields"]


def test_username_is_case_insensitive_and_strips_at(client):
    register(client, username="@MixedCase")
    assert client.get("/api/auth/me").get_json()["user"]["username"] == "mixedcase"


def test_login_by_username_and_email(client):
    register(client)
    client.post("/api/auth/logout")
    assert login(client).status_code == 200
    client.post("/api/auth/logout")
    assert login(client, "HR@abc.example").status_code == 200
    assert login(client, "@ABCTECH").status_code == 200


def test_login_failures_are_generic(client):
    register(client)
    client.post("/api/auth/logout")
    wrong_pw = login(client, "abctech", "nope-nope-nope")
    unknown = login(client, "nobody", "nope-nope-nope")
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.get_json()["error"]["message"] == unknown.get_json()["error"]["message"]
    assert client.get("/api/auth/me").status_code == 401


def test_login_requires_fields(client):
    assert client.post("/api/auth/login", json={}).status_code == 422


def test_logout_ends_session(client):
    register(client)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/profile").status_code == 401


def test_private_api_requires_login(client):
    for method, url in [("get", "/api/profile"), ("put", "/api/profile"), ("post", "/api/profile/password")]:
        r = getattr(client, method)(url, json={})
        assert r.status_code == 401, url
        assert r.get_json()["error"]["code"] == "unauthorized"


def test_disabled_account_session_is_rejected(client, db_session):
    register(client)
    db_session.query(User).update({"is_active": False})
    db_session.commit()
    assert client.get("/api/auth/me").status_code == 401
    assert login(client).status_code == 401


def test_profile_update_persists(client):
    register(client)
    r = client.put("/api/profile", json={
        "company_name": "New Name", "username": "@NewUser", "email": "new@abc.example",
        "phone": "+91 99999 11111", "address": "New address 1", "industry": "Finance"})
    assert r.status_code == 200
    again = client.get("/api/profile").get_json()["user"]
    assert again["company_name"] == "New Name" and again["username"] == "newuser" and again["industry"] == "Finance"
    client.post("/api/auth/logout")
    assert login(client, "newuser").status_code == 200


def test_profile_update_validation_and_duplicates(client):
    register(client)
    other = client.application.test_client()
    register(other, username="second", email="second@abc.example")
    base = {"company_name": "ABC", "username": "abctech", "email": "hr@abc.example", "phone": "+91 98765 43210",
            "address": "x" * 10, "industry": "IT"}
    assert client.put("/api/profile", json={**base, "email": "bad"}).status_code == 422
    r = client.put("/api/profile", json={**base, "username": "second"})
    assert r.status_code == 409 and "username" in r.get_json()["error"]["fields"]
    assert client.put("/api/profile", json=base).status_code == 200  # keeping own values is fine


def test_profile_update_cannot_target_other_users(client, db_session):
    register(client)
    other = client.application.test_client()
    register(other, username="second", email="second@abc.example", company_name="Second Co")
    client.put("/api/profile", json={"id": 2, "user_id": 2, "company_name": "Hacked", "username": "abctech",
                                     "email": "hr@abc.example", "phone": "+91 98765 43210", "industry": "IT"})
    assert db_session.query(User).filter_by(username="second").one().company_name == "Second Co"


def test_change_password_flow(client):
    register(client)
    other_session = client.application.test_client()
    login(other_session)  # a second device
    url = "/api/profile/password"
    assert client.post(url, json={"current_password": "wrong-wrong-1", "new_password": "brand-new-pass-1",
                                  "confirm_password": "brand-new-pass-1"}).status_code == 403
    assert client.post(url, json={"current_password": "correct-horse-1", "new_password": "short",
                                  "confirm_password": "short"}).status_code == 422
    assert client.post(url, json={"current_password": "correct-horse-1", "new_password": "brand-new-pass-1",
                                  "confirm_password": "mismatch-xx-1"}).status_code == 422
    assert client.post(url, json={"current_password": "correct-horse-1", "new_password": "correct-horse-1",
                                  "confirm_password": "correct-horse-1"}).status_code == 422
    ok = client.post(url, json={"current_password": "correct-horse-1", "new_password": "brand-new-pass-1",
                                "confirm_password": "brand-new-pass-1"})
    assert ok.status_code == 200
    assert client.get("/api/auth/me").status_code == 200           # this session survives
    assert other_session.get("/api/auth/me").status_code == 401    # other sessions are signed out
    client.post("/api/auth/logout")
    assert login(client).status_code == 401                        # old password dead
    assert login(client, password="brand-new-pass-1").status_code == 200


def test_page_guards(client):
    r = client.get("/profile.html")
    assert r.status_code == 302 and r.headers["Location"].startswith("/login.html?next=/profile.html")
    assert client.get("/login.html").status_code == 200
    assert client.get("/features.html").status_code == 200
    assert client.get("/").headers["Location"].endswith("/login.html")
    register(client)
    assert client.get("/profile.html").status_code == 200
    assert client.get("/login.html").status_code == 302   # already signed in
    assert client.get("/").headers["Location"].endswith("/homepage.html")


def test_csrf_enforced_when_enabled():
    app = create_app("testing", {"WTF_CSRF_ENABLED": True})
    c = app.test_client()
    r = c.post("/api/auth/register", json=REG)
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "csrf_failed"
    token = c.get("/api/csrf").get_json()["csrf_token"]
    r = c.post("/api/auth/register", json=REG, headers={"X-CSRFToken": token})
    assert r.status_code == 201
    # after login the token rotated; the old one no longer works for writes
    stale = c.post("/api/auth/logout", headers={"X-CSRFToken": token})
    assert stale.status_code == 400
    fresh = c.post("/api/auth/logout", headers={"X-CSRFToken": r.get_json()["csrf_token"]})
    assert fresh.status_code == 200


def test_login_is_rate_limited():
    app = create_app("testing", {"RATELIMIT_ENABLED": True, "LOGIN_RATE_LIMIT": "3 per minute"})
    c = app.test_client()
    codes = [login(c, "nobody", "whatever-1").status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]
    assert c.post("/api/auth/login", json={}).get_json()["error"]["code"] == "rate_limited"
