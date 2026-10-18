"""Production server settings:  gunicorn -c gunicorn.conf.py app:app"""
import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", min(4, multiprocessing.cpu_count() * 2 + 1)))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 60                    # PDF parsing of a 5 MB resume finishes far below this
graceful_timeout = 30
keepalive = 5
accesslog = "-"                 # logs go to stdout/stderr (12-factor); the platform collects them
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
limit_request_line = 4094
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")
