from flask import Flask


def register_blueprints(app: Flask) -> None:
    from .health import bp as health_bp

    app.register_blueprint(health_bp)
