from flask import Blueprint

from app.openapi import DOCS_HTML, build_spec
from app.routes.users import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.validation import PHONE_MAX_LENGTH, STATUSES

bp = Blueprint("docs", __name__)


@bp.route("/openapi.json")
def openapi_spec():
    return build_spec(DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, PHONE_MAX_LENGTH, STATUSES)


@bp.route("/docs")
def docs():
    return DOCS_HTML
