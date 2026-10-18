"""Phase 0 baseline: every page is well-formed and every link/redirect resolves."""
from static_audit import audit, pages_dir


def test_static_audit_clean():
    assert audit() == []


def test_expected_pages_exist():
    names = {p.name for p in pages_dir().glob("*.html")}
    assert names >= {
        "login.html", "create-account.html", "register.html", "homepage.html",
        "features.html", "how-it-works.html", "upload.html", "ats-score.html",
        "profile.html", "edit-profile.html", "change-password.html",
    }
