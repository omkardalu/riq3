# Regression map: every phase has tests that run on every change

Run all of it with `./scripts/verify.sh` (or `pytest`).

| Phase | Exit criterion (from `phases.md`) | Proven by |
|---|---|---|
| 0 Stabilize | every page loads, every link works, no stray markup | `tests/static_audit.py`, `test_phase0_static.py`, `js/phase2.test.mjs` (all pages load, no script errors) |
| 1 Backend foundation | app starts, PostgreSQL connected, migrations + CRUD | `test_phase1_backend.py`, `test_phase7_ops.py` (migration roundtrip, no schema drift) |
| 2 Auth & profiles | register/login/logout, profile + password, private data | `test_phase2_auth.py`, `js/phase2.test.mjs` |
| 3 Upload & job setup | upload, refresh, still saved; limits and errors | `test_phase3_uploads.py`, `js/phase3.test.mjs` |
| 4 Analysis engine | extract, match, explainable deterministic score | `test_phase4_analysis.py`, `js/phase4.test.mjs`, `SCORING.md` |
| 5 Results & history | persisted results, search/sort/filter, history | `js/phase5.test.mjs` |
| 6 UX consistency | shared nav/footer/FAQ, accessibility, honest copy | `static_audit.py` (a11y rules), `js/phase6.test.mjs` |
| 7 Security & submission | e2e journey, failure modes, review, clean setup | `test_phase7_security.py`, `test_phase7_ops.py`, `js/phase7.test.mjs`, `SECURITY.md`, `DEMO.md`, `DEPLOYMENT.md` |
