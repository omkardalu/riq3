from flask import Flask


def register_blueprints(app: Flask) -> None:
    from .auth import bp as auth_bp
    from .health import bp as health_bp
    from .jobs import bp as jobs_bp
    from .profile import bp as profile_bp
    from .resumes import bp as resumes_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(resumes_bp)
    app.register_blueprint(jobs_bp)
