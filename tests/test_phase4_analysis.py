import io
import json

import pytest

from files import SAMPLE_LINES, make_blank_pdf, make_docx, make_pdf
from helpers import make_account
from riq.analysis import extract as ex
from riq.analysis.candidate import find_email, find_phone, guess_name, split_sections
from riq.analysis.normalize import normalize_flat, normalize_lines
from riq.analysis.scoring import SCORING_VERSION, analyze_text
from riq.analysis.skills import jd_keywords, match_skills


# ---------- normalisation ----------
def test_normalize_unifies_case_punctuation_whitespace():
    raw = "  Python\u00a0\u2022  \u201cNode.JS\u201d \u2013 REST\tAPI\u200b  "
    assert normalize_flat(raw) == 'python "node.js" - rest api'
    assert normalize_lines("A  B\r\n\r\n  C ") == "a b\n\nc"


# ---------- extraction ----------
def test_extract_pdf_text(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(make_pdf(SAMPLE_LINES))
    r = ex.extract(p, "pdf")
    assert r.status == "ok" and "Rahul Kumar" in r.text and r.pages == 1


def test_extract_docx_includes_tables_in_order(tmp_path):
    p = tmp_path / "a.docx"
    p.write_bytes(make_docx(["Jane Doe", "Skills"], table=[["Python", "5 years"], ["SQL", "3 years"]]))
    r = ex.extract(p, "docx")
    assert r.status == "ok"
    assert "Python | 5 years" in r.text and r.text.index("Jane Doe") < r.text.index("Python")


def test_scanned_pdf_reported_as_scanned_not_scored(tmp_path):
    p = tmp_path / "s.pdf"
    p.write_bytes(make_blank_pdf())
    r = ex.extract(p, "pdf")
    assert r.status == "scanned" and "OCR is not supported" in r.error and r.text == ""


def test_empty_docx_and_corrupt_files(tmp_path):
    (tmp_path / "e.docx").write_bytes(make_docx([]))
    assert ex.extract(tmp_path / "e.docx", "docx").status == "empty"
    (tmp_path / "bad.pdf").write_bytes(b"%PDF-1.4 garbage garbage")
    assert ex.extract(tmp_path / "bad.pdf", "pdf").status == "failed"
    (tmp_path / "bad.docx").write_bytes(b"PK\x03\x04 nope")
    assert ex.extract(tmp_path / "bad.docx", "docx").status == "failed"


# ---------- skill matching ----------
TEXT = "I know Python, JavaScript and node.js. Built REST APIs with C++ and C#. Used React.js, k8s, CI/CD and Java."


@pytest.mark.parametrize("skill,expected", [
    ("Python", True), ("python", True), ("JS", True), ("Node.js", True), ("nodejs", True), ("React", True),
    ("Kubernetes", True), ("REST API", True), ("ci/cd", True), ("C++", True), ("C#", True), ("Java", True),
    ("SQL", False), ("Go", False), ("C", False), ("Rust", False),
])
def test_skill_matching(skill, expected):
    assert match_skills(TEXT, [skill])[0]["matched"] is expected


def test_java_does_not_match_javascript_only():
    assert match_skills("expert in javascript and typescript", ["Java"])[0]["matched"] is False


def test_c_does_not_match_c_plus_plus_or_sharp_only():
    assert match_skills("I write c++ and c# daily", ["C"])[0]["matched"] is False
    assert match_skills("I write c, c++ daily", ["C"])[0]["matched"] is True


def test_multi_word_skill_and_whitespace_tolerance():
    assert match_skills("Applied  Machine\nLearning in production", ["machine learning"])[0]["matched"]
    assert match_skills("worked on ml pipelines", ["Machine Learning"])[0]["matched"]


def test_mentions_counted():
    assert match_skills("python python. Python!", ["Python"])[0]["mentions"] == 3


# ---------- JD keywords ----------
def test_jd_keywords_deterministic_and_skill_free():
    jd = "We need a backend engineer to build scalable microservices. Strong python and SQL. Microservices design, microservices testing."
    a, b = jd_keywords(jd, ["Python", "SQL"]), jd_keywords(jd, ["Python", "SQL"])
    assert a == b
    terms = [t["term"] for t in a]
    assert terms[0] == "microservices" and "python" not in terms and "sql" not in terms
    assert "the" not in terms and "need" not in terms


def test_no_jd_gives_no_terms():
    assert jd_keywords("", ["Python"]) == []


# ---------- candidate parsing ----------
def test_candidate_fields():
    text = "\n".join(SAMPLE_LINES)
    assert guess_name(text) == "Rahul Kumar"
    assert find_email(text) == "rahul@example.com"
    assert find_phone(text) == "+91 98765 43210"
    s = split_sections(text)
    assert set(s) >= {"skills", "experience", "education", "projects"}
    assert "b.tech in computer science, xyz engineering college, 2027" in s["education"]


def test_name_not_taken_from_headings_or_contact_lines():
    assert guess_name("Curriculum Vitae\nrahul@x.com\nSkills\nPython") is None


# ---------- scoring ----------
SKILLS = ["Python", "SQL", "Docker", "AWS"]
JD = "Backend engineer building python services with SQL. Python microservices, microservices testing."
RESUME = "\n".join(SAMPLE_LINES) + "\nBuilt python microservices and testing for services."


def test_score_arithmetic_is_explained_and_adds_up():
    out = analyze_text(RESUME, "r.pdf", SKILLS, JD)
    d = out["details"]
    assert out["matched_skills"] == ["Python", "SQL"] and out["missing_skills"] == ["Docker", "AWS"]
    assert out["matched_percentage"] == 50.0
    assert abs(sum(c["points"] for c in d["components"]) - out["score"]) < 0.02
    skills = next(c for c in d["components"] if c["key"] == "skills")
    assert skills["weight"] == 0.7 and skills["coverage"] == 50.0 and skills["points"] == 35.0
    assert f"Score {out['score']:g}/100" in d["explanation"]
    assert {c["key"] for c in d["components"]} == {"skills", "jd_keywords", "structure"}


def test_weights_without_job_description():
    out = analyze_text(RESUME, "r.pdf", SKILLS, "")
    keys = {c["key"]: c for c in out["details"]["components"]}
    assert set(keys) == {"skills", "structure"} and keys["skills"]["weight"] == 0.9


def test_perfect_and_zero_scores():
    full = analyze_text(RESUME, "r.pdf", ["Python", "SQL"], "")
    assert full["matched_percentage"] == 100.0 and 90 <= full["score"] <= 100
    none = analyze_text("Some unrelated text about gardening and cooking for a long time ok", "x.pdf", ["Python"], "")
    assert none["score"] == 0.0 and none["matched_skills"] == []


def test_identical_inputs_identical_output():
    outs = [json.dumps(analyze_text(RESUME, "r.pdf", SKILLS, JD), sort_keys=True) for _ in range(3)]
    assert outs[0] == outs[1] == outs[2]


def test_skill_order_does_not_change_score():
    a = analyze_text(RESUME, "r.pdf", SKILLS, JD)["score"]
    b = analyze_text(RESUME, "r.pdf", list(reversed(SKILLS)), JD)["score"]
    assert a == b


def test_narrative_mentions_missing_skills():
    d = analyze_text(RESUME, "r.pdf", SKILLS, JD)["details"]
    assert any("Docker" in w for w in d["weaknesses"])
    assert any("Docker" in r for r in d["recommendations"])
    assert d["strengths"]


# ---------- API ----------
def up(c, data, name):
    return c.post("/api/resumes", data={"file": (io.BytesIO(data), name)}, content_type="multipart/form-data").get_json()["resume"]["id"]


def job(c, skills="Python, SQL, Docker", jd=""):
    return c.post("/api/jobs", json={"required_skills": skills, "description": jd}).get_json()["job"]["id"]


@pytest.fixture()
def acct(app):
    return make_account(app, 1)


def test_analyze_resume_end_to_end(acct):
    rid, jid = up(acct, make_pdf(SAMPLE_LINES), "rahul.pdf"), job(acct)
    r = acct.post("/api/analyses", json={"job_id": jid, "resume_id": rid})
    a = r.get_json()["analysis"]
    assert r.status_code == 200 and a["status"] == "completed" and a["scoring_version"] == SCORING_VERSION
    assert a["candidate_name"] == "Rahul Kumar"
    assert a["matched_skills"] == ["Python", "SQL"] and a["missing_skills"] == ["Docker"]
    assert a["details"]["candidate"]["email"] == "rahul@example.com"
    stored = acct.get(f"/api/analyses/{a['id']}").get_json()["analysis"]
    assert stored["score"] == a["score"]


def test_analysis_is_persisted_and_rerun_is_idempotent(acct):
    rid, jid = up(acct, make_pdf(SAMPLE_LINES), "a.pdf"), job(acct)
    first = acct.post("/api/analyses", json={"job_id": jid, "resume_id": rid}).get_json()["analysis"]
    second = acct.post("/api/analyses", json={"job_id": jid, "resume_id": rid}).get_json()["analysis"]
    assert first["id"] == second["id"] and first["score"] == second["score"]
    assert first["details"] == second["details"]
    assert acct.get(f"/api/analyses?job_id={jid}").get_json()["total"] == 1


def test_scanned_pdf_is_unsupported_with_no_score(acct):
    rid, jid = up(acct, make_blank_pdf(), "scan.pdf"), job(acct)
    a = acct.post("/api/analyses", json={"job_id": jid, "resume_id": rid}).get_json()["analysis"]
    assert a["status"] == "unsupported" and a["score"] is None and a["matched_skills"] == []
    assert "OCR" in a["error_message"]


def test_corrupt_pdf_fails_cleanly(acct):
    rid, jid = up(acct, b"%PDF-1.4 total garbage here", "bad.pdf"), job(acct)
    r = acct.post("/api/analyses", json={"job_id": jid, "resume_id": rid})
    assert r.status_code == 200 and r.get_json()["analysis"]["status"] == "failed"
    assert r.get_json()["analysis"]["score"] is None


def test_different_jobs_give_independent_results(acct):
    rid = up(acct, make_pdf(SAMPLE_LINES), "a.pdf")
    j1, j2 = job(acct, "Python"), job(acct, "Docker, Kubernetes")
    a1 = acct.post("/api/analyses", json={"job_id": j1, "resume_id": rid}).get_json()["analysis"]
    a2 = acct.post("/api/analyses", json={"job_id": j2, "resume_id": rid}).get_json()["analysis"]
    assert a1["score"] > a2["score"] and a1["id"] != a2["id"]


def test_list_filter_search_sort(acct):
    jid = job(acct, "Python, SQL, Git")
    ids = {
        "rahul.pdf": up(acct, make_pdf(SAMPLE_LINES), "rahul.pdf"),
        "priya.docx": up(acct, make_docx(["Priya Sharma", "Skills", "Java only here and some more words", "priya@x.com"]), "priya.docx"),
        "scan.pdf": up(acct, make_blank_pdf(), "scan.pdf"),
    }
    for rid in ids.values():
        acct.post("/api/analyses", json={"job_id": jid, "resume_id": rid})
    base = f"/api/analyses?job_id={jid}"
    rows = acct.get(base).get_json()["analyses"]
    assert [r["filename"] for r in rows][0] == "rahul.pdf" and rows[-1]["status"] == "unsupported"  # nulls last
    asc = acct.get(base + "&sort=score&order=asc").get_json()["analyses"]
    assert asc[0]["status"] == "completed" and asc[0]["filename"] == "priya.docx"
    assert [r["filename"] for r in acct.get(base + "&q=priya").get_json()["analyses"]] == ["priya.docx"]
    assert [r["filename"] for r in acct.get(base + "&q=RAHUL%20KUMAR").get_json()["analyses"]] == ["rahul.pdf"]
    assert acct.get(base + "&status=unsupported").get_json()["total"] == 1
    names = [r["candidate_name"] for r in acct.get(base + "&sort=name&order=asc").get_json()["analyses"]]
    assert names == sorted(names, key=str.lower)
    assert acct.get(base + "&sort=bogus").status_code == 422
    assert acct.get(base + "&status=bogus").status_code == 422


def test_analysis_ownership(app):
    a, b = make_account(app, 1), make_account(app, 2)
    rid, jid = up(a, make_pdf(SAMPLE_LINES), "a.pdf"), job(a)
    aid = a.post("/api/analyses", json={"job_id": jid, "resume_id": rid}).get_json()["analysis"]["id"]
    assert b.post("/api/analyses", json={"job_id": jid, "resume_id": rid}).status_code == 404
    b_rid, b_jid = up(b, make_pdf(["Other Person", "python"] + ["x"] * 5), "b.pdf"), job(b)
    assert b.post("/api/analyses", json={"job_id": jid, "resume_id": b_rid}).status_code == 404   # my resume, their job
    assert b.post("/api/analyses", json={"job_id": b_jid, "resume_id": rid}).status_code == 404    # their resume, my job
    assert b.get(f"/api/analyses/{aid}").status_code == 404
    assert b.delete(f"/api/analyses/{aid}").status_code == 404
    assert b.get(f"/api/analyses?job_id={jid}").status_code == 404
    assert b.get("/api/analyses").get_json()["total"] == 0
    assert a.get(f"/api/analyses/{aid}").status_code == 200


def test_deleting_resume_or_job_removes_analyses(acct):
    rid, jid = up(acct, make_pdf(SAMPLE_LINES), "a.pdf"), job(acct)
    acct.post("/api/analyses", json={"job_id": jid, "resume_id": rid})
    acct.delete(f"/api/resumes/{rid}")
    assert acct.get("/api/analyses").get_json()["total"] == 0


def test_bad_ids_rejected(acct):
    assert acct.post("/api/analyses", json={"job_id": "x", "resume_id": 1}).status_code == 422
    assert acct.post("/api/analyses", json={"job_id": 999, "resume_id": 999}).status_code == 404
