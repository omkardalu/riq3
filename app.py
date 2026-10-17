"""Entry point.

    flask --app app run            # development
    gunicorn app:app               # production
"""
from riq import create_app

app = create_app()
