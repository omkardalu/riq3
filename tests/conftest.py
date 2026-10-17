import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

os.environ.setdefault("APP_ENV", "testing")


@pytest.fixture(scope="session")
def app():
    """App wired to the PostgreSQL test database, schema built by the real Alembic migrations."""
    from flask_migrate import upgrade

    from riq import create_app
    from riq.extensions import db

    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.session.execute(db.text("DROP TABLE IF EXISTS alembic_version"))
        db.session.commit()
        upgrade(directory=str(Path(__file__).parent.parent / "migrations"))
    yield app
    shutil.rmtree(app.config["UPLOAD_FOLDER"], ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_db(request, app):
    """Empty every table (and uploads) between tests."""
    if "app" not in request.fixturenames and not any(
        f in request.fixturenames for f in ("client", "db_session", "app_ctx")
    ):
        yield
        return
    from riq.extensions import db

    yield
    with app.app_context():
        db.session.remove()
        db.session.execute(db.text("TRUNCATE analyses, resumes, job_descriptions, users RESTART IDENTITY CASCADE"))
        db.session.commit()
    up = Path(app.config["UPLOAD_FOLDER"])
    if up.exists():
        for child in up.iterdir():
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_session(app):
    from riq.extensions import db

    with app.app_context():
        yield db.session
