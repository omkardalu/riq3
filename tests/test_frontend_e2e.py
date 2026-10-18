"""Runs the jsdom end-to-end suites (tests/js/*.test.mjs) against a live server + PostgreSQL."""
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from riq import create_app

JS_DIR = Path(__file__).parent / "js"
needs_node = pytest.mark.skipif(
    not (JS_DIR / "node_modules" / "jsdom").exists() or not shutil.which("node"),
    reason="jsdom not installed (run `npm install` in tests/js)",
)


@pytest.fixture(scope="module")
def live_server(app):
    live = create_app("testing", {"WTF_CSRF_ENABLED": True})  # real CSRF protection in browser tests
    srv = make_server("127.0.0.1", 0, live, threaded=True)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture(scope="module")
def fixtures_dir(tmp_path_factory):
    from files import SAMPLE_LINES, make_blank_pdf, make_docx, make_pdf

    d = tmp_path_factory.mktemp("fixtures")
    (d / "rahul.pdf").write_bytes(make_pdf(SAMPLE_LINES))
    (d / "priya.docx").write_bytes(make_docx(["Priya Sharma", "priya@example.com", "Skills", "Java, SQL, Git, HTML, CSS"]))
    (d / "arjun.docx").write_bytes(make_docx(["Arjun Reddy", "arjun@example.com  +91 99887 66554", "Skills", "Python, Docker, AWS, SQL, Git", "Experience", "Cloud intern 4 months", "Education", "B.Tech CSE"]))
    (d / "scanned.pdf").write_bytes(make_blank_pdf())
    return d


def run_suite(base_url: str, pattern: str, fixtures: Path):
    import os

    env = {**os.environ, "BASE_URL": base_url, "FIXTURES_DIR": str(fixtures)}
    r = subprocess.run(["node", "--test", "--test-reporter=spec", pattern], cwd=JS_DIR, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-6000:] + r.stderr[-2000:]


@needs_node
@pytest.mark.parametrize("suite", ["phase2.test.mjs", "phase3.test.mjs", "phase4.test.mjs", "phase5.test.mjs", "phase6.test.mjs"])
def test_frontend_suite(live_server, fixtures_dir, suite):
    run_suite(live_server, suite, fixtures_dir)
