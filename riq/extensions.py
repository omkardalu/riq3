from flask import request
from flask_limiter import Limiter
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect


def client_ip() -> str:
    # ProxyFix (when TRUST_PROXY=1) has already rewritten remote_addr
    return request.remote_addr or "unknown"


db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=client_ip)
