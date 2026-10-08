from flask import Flask
import os

from app.errors import register_error_handlers
from app.logs import configure_logger, register_request_logging
from app.routes import docs, health, users


def create_app():
    app = Flask(__name__)
    app.json.sort_keys = False  # Disable sorting of JSON keys
    configure_logger(app.logger, os.environ.get("LOG_LEVEL", "INFO"))

    register_request_logging(app)
    register_error_handlers(app)
    for module in (health, users, docs):
        app.register_blueprint(module.bp)

    return app
