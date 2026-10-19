# Deployment

Tested here: gunicorn + PostgreSQL 16 in production mode (`tests/test_phase7_ops.py::test_gunicorn_production_smoke`).
Not tested here: any specific hosting platform or a Docker image (none is provided).

## Requirements
- Python 3.11+ (developed on 3.12), PostgreSQL 14+, HTTPS in front of the app (cookies are `Secure`).
- Persistent disk for `UPLOAD_FOLDER` (uploaded resumes are files, not database rows). Back it up with the database.

## Configuration (environment variables)
| Variable | Required in production | Notes |
|---|---|---|
| `APP_ENV=production` | yes | enables strict validation; the app refuses to start with an unsafe config |
| `SECRET_KEY` | yes | >= 32 random characters: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | yes | `postgresql://user:pass@host:5432/dbname` (`postgres://` also accepted) |
| `SESSION_COOKIE_SECURE` | yes (default true) | must be true; serve over HTTPS |
| `UPLOAD_FOLDER` | recommended | absolute path on a persistent volume |
| `TRUST_PROXY=true` | behind a reverse proxy | so client IPs / HTTPS are read from `X-Forwarded-*` |
| `RATELIMIT_STORAGE_URI` | with >1 worker | `redis://...`; the default in-memory limiter is per worker |
| `MAX_RESUME_BYTES`, `USER_STORAGE_QUOTA_BYTES` | optional | default 5 MB per file, 500 MB per account |
| `LOGIN_RATE_LIMIT`, `REGISTER_RATE_LIMIT`, `UPLOAD_RATE_LIMIT`, `ANALYSIS_RATE_LIMIT` | optional | e.g. `10 per minute` |
| `WEB_CONCURRENCY`, `PORT`, `LOG_LEVEL` | optional | gunicorn workers / port / log level |

## Steps
```bash
pip install -r requirements.txt
export APP_ENV=production SECRET_KEY=... DATABASE_URL=... UPLOAD_FOLDER=/var/lib/riq/uploads TRUST_PROXY=true
flask --app app db upgrade                    # run on every release, before starting the new version
gunicorn -c gunicorn.conf.py app:app          # a Procfile with release + web commands is included
```
Health check for the platform / load balancer: `GET /api/health` -> 200 `{"status":"ok","database":"ok"}`, or 503 when the database is unreachable.

## Before each release
```bash
pip install pip-audit && pip-audit -r requirements.txt   # known-vulnerability scan (last run: no known vulnerabilities)
bash scripts/verify.sh                                     # migrations, drift, lint, page audit, all tests
```

## Using Neon (serverless PostgreSQL)
Neon is standard PostgreSQL, so nothing else changes. The app already sets what Neon needs
(`pool_pre_ping`, short connection recycling, no server-side prepared statements for the pooled host).

1. In the Neon console create a project, then copy the connection string (Dashboard -> *Connect*).
   It looks like `postgresql://USER:PASSWORD@ep-xxxx.REGION.aws.neon.tech/neondb?sslmode=require`.
2. Put it in `.env` (or your host's environment) as `DATABASE_URL`. Keep `?sslmode=require` and anything else Neon adds.
3. Create the tables once: `flask --app app db upgrade`.
   Prefer the **direct** (non-pooled) connection string for migrations; either works for the running app.
4. Start the app as usual (`flask --app app run`, or gunicorn in production).

Good to know:
- **Tests erase data.** Never point `TEST_DATABASE_URL` at the database you actually use. In Neon create a second
  *branch* (e.g. `test`) or database and use its string for `TEST_DATABASE_URL`, or keep running tests against local PostgreSQL.
- **First request after idle can be slow** (about a second) because Neon wakes a suspended compute; later requests are normal.
  `/api/health` reports 503 only if the database is genuinely unreachable.
- **Uploaded resumes are files, not database rows.** Neon stores users, jobs and results; the PDF/DOCX files stay in
  `UPLOAD_FOLDER` on the machine running the app. On hosts with an ephemeral disk (many serverless/PaaS platforms) mount a
  persistent volume there, or uploaded files disappear on redeploy while their database records remain.
- Neon is not tested in this project's own test run (it runs on local PostgreSQL 16); only the connection-string handling is covered by a test.

## Operations
- **Logs** go to stdout/stderr. Every line carries a request id (`[a1b2c3d4e5f6]`); the same id is returned in the
  `X-Request-ID` header and in the JSON body of any 5xx error, so a user report can be matched to a log line.
  Passwords, session cookies and typed usernames are never logged (tested).
- **Migrations**: `flask --app app db upgrade` / `downgrade -1`. `flask --app app db check` fails if a model changed without a migration.
- **Backups**: database dump + the `UPLOAD_FOLDER` directory, taken together.
- **Scaling**: stateless app servers (sessions are signed cookies). Use Redis for rate limits when running more than one worker/instance.
