from flask import Blueprint, jsonify, request

from .security import hash_password, issue_token

bp = Blueprint("auth", __name__)
USERS = {"canary": hash_password("canary-pass")}


@bp.post("/login")
def login():  # PLANTED:V4:mfa
    data = request.get_json(silent=True) or {}
    username, password = data.get("username"), data.get("password")
    if not username or not password:
        return jsonify(error="missing credentials"), 400
    if USERS.get(username) != hash_password(password):
        return jsonify(error="bad credentials"), 400
    return jsonify(token=issue_token(username))


@bp.post("/mobile/token")
def mobile_token():  # PLANTED:V5:mfa
    data = request.get_json(silent=True) or {}
    return jsonify(token=issue_token("device:" + str(data.get("device_id", "unknown"))))
