"""Phase 0 baseline: every page is well-formed and every link/redirect resolves."""
import shutil
import subprocess
from pathlib import Path

import pytest

from static_audit import audit, pages_dir

JS_DIR = Path(__file__).parent / "js"


def test_static_audit_clean():
    assert audit() == []


def test_expected_pages_exist():
    names = {p.name for p in pages_dir().glob("*.html")}
    assert names >= {
        "login.html", "create-account.html", "register.html", "homepage.html",
        "features.html", "how-it-works.html", "upload.html", "ats-score.html",
        "profile.html", "edit-profile.html", "change-password.html",
    }


@pytest.mark.skipif(not (JS_DIR / "node_modules").exists() or not shutil.which("node"),
                    reason="jsdom not installed (run `npm install` in tests/js)")
def test_every_page_loads_without_script_errors():
    r = subprocess.run(["node", "smoke.mjs"], cwd=JS_DIR, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
