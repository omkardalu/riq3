# Resume IQ

Resume screening for recruiters: set the skills and job description for a role, upload PDF/DOCX
resumes, and get an explainable ATS score per candidate.

Stack: Flask · PostgreSQL · SQLAlchemy/Alembic · plain HTML/CSS/JS front end.

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

docker compose up -d db              # or use any PostgreSQL 14+ you already have
cp .env.example .env                 # then set SECRET_KEY

flask --app app db upgrade           # create tables
flask --app app run                  # http://127.0.0.1:5000
```

Health check: `GET /api/health` -> `{"status":"ok","database":"ok"}` (503 if the database is down).

## Tests

```bash
createdb riq_test                    # or: psql -c 'CREATE DATABASE riq_test'
export TEST_DATABASE_URL=postgresql://riq:riq@localhost:5432/riq_test
pytest
```

The test schema is built from the real Alembic migrations, so migrations are tested too.
