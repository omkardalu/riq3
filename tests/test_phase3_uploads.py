import io
from pathlib import Path

import pytest

from files import SAMPLE_LINES, make_docx, make_pdf
from helpers import make_account
from riq import create_app
from riq.models import Resume


def upload(c, data, name="resume.pdf"):
    return c.post("/api/resumes", data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data")


@pytest.fixture()
def acct(app):
    return make_account(app, 1)


def test_requires_login(client):
    assert client.get("/api/resumes").status_code == 401
    assert upload(client, make_pdf(["x"])).status_code == 401
    assert client.post("/api/jobs", json={}).status_code == 401


def test_upload_pdf_and_docx_then_list_persists(acct):
    r1 = upload(acct, make_pdf(SAMPLE_LINES), "rahul.pdf")
    r2 = upload(acct, make_docx(SAMPLE_LINES), "priya.docx")
    assert r1.status_code == r2.status_code == 201
    body = acct.get("/api/resumes").get_json()   # "refresh"
    assert [r["filename"] for r in body["resumes"]] == ["priya.docx", "rahul.pdf"]
    assert body["quota"]["used_bytes"] == sum(r["size_bytes"] for r in body["resumes"])
    assert body["quota"]["max_file_bytes"] == 5 * 1024 * 1024


def test_download_returns_the_same_bytes(acct):
    data = make_pdf(SAMPLE_LINES)
    rid = upload(acct, data, "a.pdf").get_json()["resume"]["id"]
    r = acct.get(f"/api/resumes/{rid}/file")
    assert r.status_code == 200 and r.data == data
    assert "attachment" in r.headers["Content-Disposition"]


@pytest.mark.parametrize("name,data,status,code", [
    ("notes.txt", b"hello", 415, "unsupported_type"),
    ("old.doc", b"\xd0\xcf\x11\xe0" + b"0" * 50, 415, "unsupported_type"),
    ("noext", b"hello", 415, "unsupported_type"),
    ("fake.pdf", b"this is not a pdf", 415, "invalid_file"),
    ("fake.docx", b"PK\x03\x04 not really", 415, "invalid_file"),
    ("empty.pdf", b"", 422, "empty_file"),
])
def test_invalid_uploads_rejected_with_clear_errors(acct, name, data, status, code):
    r = upload(acct, data, name)
    assert r.status_code == status
    assert r.get_json()["error"]["code"] == code
    assert acct.get("/api/resumes").get_json()["resumes"] == []


def test_docx_extension_with_pdf_content_rejected(acct):
    assert upload(acct, make_pdf(["x"]), "sneaky.docx").status_code == 415


def test_path_traversal_filename_is_neutralised(acct, app):
    r = upload(acct, make_pdf(["x"]), "../../etc/passwd.pdf")
    assert r.status_code == 201
    assert r.get_json()["resume"]["filename"] == "passwd.pdf"
    root = Path(app.config["UPLOAD_FOLDER"]).resolve()
    for f in root.rglob("*"):
        assert root in f.resolve().parents or f.resolve() == root


def test_oversize_rejected():
    app = create_app("testing", {"MAX_RESUME_BYTES": 2000, "MAX_CONTENT_LENGTH": 50_000})
    c = make_account(app, 1)
    big = make_pdf(["x" * 50] * 60, pages=3)
    assert len(big) > 2000
    r = upload(c, big)
    assert r.status_code == 413 and "limit" in r.get_json()["error"]["message"].lower()


def test_request_larger_than_hard_cap_gets_413_json():
    app = create_app("testing", {"MAX_CONTENT_LENGTH": 1000})
    c = make_account(app, 1)
    r = upload(c, b"%PDF-" + b"0" * 5000)
    assert r.status_code == 413 and r.get_json()["error"]["code"] == "file_too_large"


def test_duplicate_file_rejected_even_if_renamed(acct):
    data = make_pdf(SAMPLE_LINES)
    assert upload(acct, data, "a.pdf").status_code == 201
    r = upload(acct, data, "renamed.pdf")
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "duplicate_file"
    assert len(acct.get("/api/resumes").get_json()["resumes"]) == 1


def test_same_file_allowed_for_different_accounts(app):
    data = make_pdf(SAMPLE_LINES)
    assert upload(make_account(app, 1), data).status_code == 201
    assert upload(make_account(app, 2), data).status_code == 201


def test_storage_quota_enforced():
    app = create_app("testing", {"USER_STORAGE_QUOTA_BYTES": 3000})
    c = make_account(app, 1)
    codes = [upload(c, make_pdf([f"resume number {i}"]), f"{i}.pdf").status_code for i in range(6)]
    assert 413 in codes and codes[0] == 201
    assert c.get("/api/resumes").get_json()["quota"]["used_bytes"] <= 3000


def test_files_stored_privately_with_random_names(acct, app, db_session):
    upload(acct, make_pdf(SAMPLE_LINES), "Confidential Name.pdf")
    r = db_session.query(Resume).one()
    on_disk = list(Path(app.config["UPLOAD_FOLDER"]).rglob("*.pdf"))
    assert len(on_disk) == 1 and on_disk[0].stem == r.stored_name
    assert "Confidential" not in on_disk[0].name
    assert acct.get(f"/assets/{on_disk[0].name}").status_code == 404
    assert acct.get(f"/{on_disk[0].name}").status_code == 404


def test_delete_removes_file_and_row(acct, app):
    rid = upload(acct, make_pdf(SAMPLE_LINES)).get_json()["resume"]["id"]
    assert acct.delete(f"/api/resumes/{rid}").status_code == 200
    assert acct.get(f"/api/resumes/{rid}").status_code == 404
    assert list(Path(app.config["UPLOAD_FOLDER"]).rglob("*.pdf")) == []
    assert acct.delete(f"/api/resumes/{rid}").status_code == 404


def test_delete_all(acct):
    for i in range(3):
        upload(acct, make_pdf([f"r{i}"]), f"{i}.pdf")
    r = acct.delete("/api/resumes")
    assert r.get_json()["deleted"] == 3
    assert acct.get("/api/resumes").get_json()["resumes"] == []


def test_users_cannot_touch_each_others_resumes(app):
    a, b = make_account(app, 1), make_account(app, 2)
    rid = upload(a, make_pdf(SAMPLE_LINES)).get_json()["resume"]["id"]
    assert b.get("/api/resumes").get_json()["resumes"] == []
    for method, url in [("get", f"/api/resumes/{rid}"), ("get", f"/api/resumes/{rid}/file"), ("delete", f"/api/resumes/{rid}")]:
        assert getattr(b, method)(url).status_code == 404, url
    assert a.get(f"/api/resumes/{rid}").status_code == 200   # still there


# ---------------- jobs ----------------

def test_job_create_normalises_skills(acct):
    r = acct.post("/api/jobs", json={"title": "Backend Dev", "description": "Build APIs",
                                     "required_skills": "Python, sql\nPYTHON; Git ,  , Node.js"})
    assert r.status_code == 201
    assert r.get_json()["job"]["required_skills"] == ["Python", "sql", "Git", "Node.js"]


def test_job_accepts_list_and_default_title(acct):
    j = acct.post("/api/jobs", json={"required_skills": ["React", "react", " Docker "]}).get_json()["job"]
    assert j["required_skills"] == ["React", "Docker"] and j["title"] == "Untitled role" and j["description"] == ""


@pytest.mark.parametrize("body,field", [
    ({"required_skills": []}, "required_skills"),
    ({"required_skills": "  ,\n "}, "required_skills"),
    ({}, "required_skills"),
    ({"required_skills": ["x" * 61]}, "required_skills"),
    ({"required_skills": [f"s{i}" for i in range(101)]}, "required_skills"),
    ({"required_skills": ["a"], "description": "d" * 20001}, "description"),
    ({"required_skills": [1, 2]}, "required_skills"),
])
def test_job_validation(acct, body, field):
    r = acct.post("/api/jobs", json=body)
    assert r.status_code == 422 and field in r.get_json()["error"]["fields"]


def test_job_list_get_delete_and_ownership(app):
    a, b = make_account(app, 1), make_account(app, 2)
    jid = a.post("/api/jobs", json={"required_skills": ["Python"]}).get_json()["job"]["id"]
    assert len(a.get("/api/jobs").get_json()["jobs"]) == 1
    assert b.get("/api/jobs").get_json()["jobs"] == []
    assert b.get(f"/api/jobs/{jid}").status_code == 404
    assert b.delete(f"/api/jobs/{jid}").status_code == 404
    assert a.delete(f"/api/jobs/{jid}").status_code == 200
    assert a.get(f"/api/jobs/{jid}").status_code == 404
