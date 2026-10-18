# Security review (Phase 7)

Each line is backed by a test in `tests/test_phase7_security.py` or `tests/test_phase7_ops.py` unless marked *(design)*.

## Authentication & sessions
- Passwords are hashed with scrypt (werkzeug); 8-128 characters; plaintext never stored or logged.
- Login accepts username or email; failures return one generic message (no account enumeration by login); wrong-account timing is equalised.
- Session cookie: `HttpOnly`, `SameSite=Lax`, `Secure` (production), signed, 7-day lifetime enforced server-side.
- Login rotates the session (no fixation). Changing the password signs out every other session. Disabled accounts lose access immediately.
- Login `?next=` accepts only same-site `/page.html` paths (no open redirect).
- Brute-force limits: login, registration, uploads and analyses are rate limited.

## Authorization
- Every private API route returns 401 to anonymous callers. A test walks the URL map, so a new unprotected endpoint fails CI.
- Every row is scoped to its owner; other accounts get 404 (indistinguishable from "does not exist") for resumes, files, jobs and analyses.
- Protected pages redirect to login on the server (no flash of private content).

## CSRF
- Every state-changing request needs a per-session token (`X-CSRFToken`). A test walks the URL map to prove no write endpoint is exempt. Tokens rotate on login/logout.

## Uploads & file storage
- Whitelist: PDF and DOCX only. Content is verified (PDF header; DOCX must be a valid zip with `word/document.xml`), not just the extension.
- Limits: 5 MB per file (exact boundary tested), request-size cap, per-account quota, zip-bomb guard (DOCX > 100 MB unpacked is refused).
- Files are stored outside the web root under random UUID names, mode `0600` in `0700` folders; the original name is display-only.
  They are only reachable through the authenticated, ownership-checked download route (`Content-Disposition: attachment`).
- Duplicate content is rejected per account (SHA-256). Writes are atomic; a failed database write removes the file.
- Parser dependency (`pypdf`) was upgraded 5.9.0 -> 6.21.1 during this review: `pip-audit` reported 85 known vulnerabilities in 5.9.0 and none in 6.21.1.

## Transport, headers, errors
- `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, HSTS (production). API and pages are `Cache-Control: no-store`.
- No CORS headers: other sites cannot read the API from a browser.
- Errors are JSON with stable codes; internals (stack traces, SQL, hosts) never reach the client. A database outage yields a clean 503.
- Source, `.env`, migrations and uploads are not reachable over HTTP (path-traversal variants tested).

## Secrets & configuration
- No secrets in the repository; `.env` is git-ignored; `.env.example` holds placeholders.
- Production refuses to start without a strong `SECRET_KEY`, a `DATABASE_URL` and secure cookies.
- The demo command (known password) refuses to run in production.

## Known limitations (honest list)
- CSP still allows `'unsafe-inline'` scripts because the pages use inline handlers; all user-supplied text is inserted with `textContent`/escaping instead (tested with hostile file names).
- Registration reveals whether a username/email is taken (needed for usable sign-up; rate limited).
- No email verification, password reset or two-factor authentication yet.
- The in-memory rate limiter is per process; use Redis for multi-worker deployments.
- Scanned PDFs are unsupported (no OCR); legacy `.doc` is unsupported.
- No antivirus scanning of uploads; files are never executed or served inline.
