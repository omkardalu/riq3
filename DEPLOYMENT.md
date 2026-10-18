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

## Operations
- **Logs** go to stdout/stderr. Every line carries a request id (`[a1b2c3d4e5f6]`); the same id is returned in the
  `X-Request-ID` header and in the JSON body of any 5xx error, so a user report can be matched to a log line.
  Passwords, session cookies and typed usernames are never logged (tested).
- **Migrations**: `flask --app app db upgrade` / `downgrade -1`. `flask --app app db check` fails if a model changed without a migration.
- **Backups**: database dump + the `UPLOAD_FOLDER` directory, taken together.
- **Scaling**: stateless app servers (sessions are signed cookies). Use Redis for rate limits when running more than one worker/instance.
