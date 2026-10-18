# Resume IQ

Resume screening for recruiters. A company signs up, enters the skills and job description for a role,
uploads PDF/DOCX resumes and gets an **explainable, repeatable ATS score** for every candidate, with search,
history and a full score breakdown. Rule-based (no AI model): the same resume + job always gives the same score
([how it is calculated](SCORING.md)).

**Stack:** Flask 3 - PostgreSQL - SQLAlchemy + Alembic - plain HTML/CSS/JS front end (no build step).

## Quick start (clean machine)

Requirements: Python 3.11+, PostgreSQL 14+ (or Docker), Node 18+ only if you want to run the browser tests.

```bash
git clone <this repo> && cd riq3
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

docker compose up -d db            # PostgreSQL with databases "riq" and "riq_test"
#   no Docker? create them yourself:  createdb riq && createdb riq_test   (user riq / password riq, or edit .env)

cp .env.example .env               # set SECRET_KEY: python -c "import secrets; print(secrets.token_hex(32))"
flask --app app db upgrade         # create the tables
flask --app app run                # http://127.0.0.1:5000
```
Health check: `GET /api/health` -> `{"status":"ok","database":"ok"}` (HTTP 503 if the database is down).

## Demo
```bash
flask --app app demo               # demo login + 5 sample resumes in ./demo_resumes
```
Then follow [DEMO.md](DEMO.md) (5 minutes, with the exact results to expect).

## Tests
```bash
bash scripts/verify.sh                          # migrations, drift check, lint, page audit, full suite
cd tests/js && npm install && cd ../..       # once, enables the browser (jsdom) end-to-end tests
pytest                                       # everything, every phase
```
The suite builds its schema from the real migrations on the `riq_test` database
(`TEST_DATABASE_URL`) and drives the real pages against a real server. What each phase is proven by: [REGRESSION.md](REGRESSION.md).
Manual checks that automation cannot do (visual layout on phones): [CHECKLIST.md](CHECKLIST.md).

## Features
- Two-step company sign-up, login/logout, profile editing, password change (sessions of other devices are signed out).
- Upload PDF/DOCX resumes (5 MB each, per-account quota, duplicates refused), saved privately and listed after refresh.
- Required skills + job description -> per-resume score with matched/missing skills, strengths, weaknesses,
  recommendations and a points breakdown. Scanned PDFs are reported as **unsupported** instead of getting an invented score.
- Results page with search, status filter, sorting, run history, applicant detail view and original-file download.

## Project layout
```
app.py                 entry point (flask --app app / gunicorn app:app)
riq/                   application package
  __init__.py          app factory, security headers, request ids, logging
  config.py            environment-driven config (+ strict production validation)
  models.py            User, Resume, JobDescription, Analysis
  auth.py  validation.py  storage.py  errors.py  web.py  cli.py  demo.py
  api/                 auth, profile, resumes, jobs, analyses, health
  analysis/            extract, normalize, skills, candidate, scoring, engine
web/pages/*.html       the 11 pages (static, data comes from /api)
web/assets/            shared JS (riq.js, site.js), CSS, favicon
migrations/            Alembic migrations
tests/                 pytest + jsdom browser suites
scripts/               verify.sh, init-db.sql
```

## API at a glance (all JSON, all under `/api`)
`GET /health` - `GET /csrf` - `POST /auth/register|login|logout` - `GET /auth/me` - `GET|PUT /profile` - `POST /profile/password` -
`GET|POST|DELETE /resumes` - `GET|DELETE /resumes/<id>` - `GET /resumes/<id>/file` - `GET|POST /jobs` - `GET|DELETE /jobs/<id>` -
`POST /analyses` - `GET /analyses?job_id&q&status&sort&order&limit&offset` - `GET|DELETE /analyses/<id>`.
Errors: `{"error": {"code", "message", "fields"?, "request_id"? }}`. All writes need the `X-CSRFToken` header (from `/api/csrf`).

## More
[SCORING.md](SCORING.md) how scores work - [SECURITY.md](SECURITY.md) review + known limits -
[DEPLOYMENT.md](DEPLOYMENT.md) production setup - [DEMO.md](DEMO.md) walkthrough - [phases.md](phases.md) the plan this implements.

## Known limitations
No OCR (scanned PDFs unsupported), no legacy `.doc`, no semantic matching (a skill must be named or be a listed alias),
no email verification / password reset yet. See [SECURITY.md](SECURITY.md).
