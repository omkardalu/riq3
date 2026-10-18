#!/usr/bin/env bash
# One command to prove the project is healthy:  ./scripts/verify.sh
# Needs: PostgreSQL reachable via DATABASE_URL / TEST_DATABASE_URL (see .env.example), dev requirements installed.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 1/5 apply migrations to the development database"
flask --app app db upgrade

echo "==> 2/5 models and migrations agree (no schema drift)"
flask --app app db check

echo "==> 3/5 lint"
python -m pyflakes riq app.py

echo "==> 4/5 static page audit (links, titles, accessibility basics)"
python tests/static_audit.py

echo "==> 5/5 full test suite (every phase)"
python -m pytest -q "$@"

echo
echo "ALL CHECKS PASSED"
