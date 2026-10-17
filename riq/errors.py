"""One consistent error shape for the API: {"error": {"code", "message", "fields"?}}."""
from __future__ import annotations

import logging

from flask import Flask, jsonify, request
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

from .extensions import db

log = logging.getLogger("riq")

_DEFAULT_MESSAGES = {
    400: ("bad_request", "The request could not be understood."),
    401: ("unauthorized", "Please sign in to continue."),
    403: ("forbidden", "You do not have access to this resource."),
    404: ("not_found", "That resource was not found."),
    405: ("method_not_allowed", "That method is not allowed here."),
    413: ("file_too_large", "The upload is too large."),
    429: ("rate_limited", "Too many requests. Please wait a moment and try again."),
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields


def error_response(status: int, code: str, message: str, fields: dict | None = None):
    body: dict = {"code": code, "message": message}
    if fields:
        body["fields"] = fields
    resp = jsonify({"error": body})
    resp.status_code = status
    return resp


def _wants_json() -> bool:
    return request.path.startswith("/api/")


def _page_error(status: int, message: str):
    html = (
        "<!doctype html><meta charset='utf-8'><title>Resume IQ</title>"
        "<body style='font-family:sans-serif;background:#04131b;color:#fff;"
        "display:grid;place-items:center;height:100vh;margin:0'>"
        f"<div style='text-align:center'><h1>{status}</h1><p>{message}</p>"
        "<p><a style='color:#0df0ad' href='/homepage.html'>Back to Resume IQ</a></p></div>"
    )
    return html, status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return error_response(e.status, e.code, e.message, e.fields)

    @app.errorhandler(CSRFError)
    def _csrf(e: CSRFError):
        if _wants_json():
            return error_response(
                400, "csrf_failed", "Your session security token is missing or expired. Refresh the page and try again."
            )
        return _page_error(400, "Security token missing or expired.")

    @app.errorhandler(HTTPException)
    def _http(e: HTTPException):
        status = e.code or 500
        code, default_msg = _DEFAULT_MESSAGES.get(status, ("http_error", e.name))
        if status == 413:
            limit_mb = app.config["MAX_RESUME_BYTES"] / (1024 * 1024)
            default_msg = f"The upload is too large. Resumes can be at most {limit_mb:g} MB."
        if _wants_json():
            return error_response(status, code, default_msg)
        return _page_error(status, default_msg)

    @app.errorhandler(OperationalError)
    def _db_down(e: OperationalError):
        db.session.rollback()
        log.error("database unavailable: %s", e.orig if hasattr(e, "orig") else e)
        if _wants_json():
            return error_response(503, "database_unavailable", "The service is temporarily unavailable. Please try again shortly.")
        return _page_error(503, "The service is temporarily unavailable.")

    @app.errorhandler(SQLAlchemyError)
    def _db_error(e: SQLAlchemyError):
        db.session.rollback()
        log.exception("database error")
        if _wants_json():
            return error_response(500, "database_error", "Something went wrong while saving your data.")
        return _page_error(500, "Something went wrong.")

    @app.errorhandler(Exception)
    def _unhandled(e: Exception):
        db.session.rollback()
        log.exception("unhandled exception on %s %s", request.method, request.path)
        if _wants_json():
            return error_response(500, "server_error", "Something went wrong on our side. Please try again.")
        return _page_error(500, "Something went wrong on our side.")
