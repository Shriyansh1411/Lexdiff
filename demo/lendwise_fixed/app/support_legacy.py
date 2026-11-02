import logging

from flask import Blueprint, jsonify

from .security import issue_token, require_mfa

logger = logging.getLogger("lendwise")
bp = Blueprint("support", __name__)


@bp.get("/impersonate/<int:customer_id>")
@require_mfa
def impersonate(customer_id):
    logger.info("support impersonation of customer %s", customer_id)
    return jsonify(impersonating=customer_id, token=issue_token(f"customer:{customer_id}"))
