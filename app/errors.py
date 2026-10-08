from flask import current_app
from werkzeug.exceptions import HTTPException
import psycopg2


def register_error_handlers(app):
    """Every error, including 404/405/500, is returned as JSON {"error": ...}."""

    @app.errorhandler(HTTPException)
    def http_error(e):
        # e.g. an unknown URL (404) or a wrong method (405)
        return {"error": e.name}, e.code

    @app.errorhandler(psycopg2.errors.UniqueViolation)
    def unique_violation(e):
        return {"error": "Email already exists"}, 409

    @app.errorhandler(Exception)
    def unexpected_error(e):
        current_app.logger.exception("Unhandled error")
        return {"error": "Internal server error"}, 500
