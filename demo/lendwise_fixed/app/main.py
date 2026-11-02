import logging

from flask import Blueprint, Flask, jsonify, request

from . import auth_routes, db, incidents, logging_mw, support_legacy
from .security import require_mfa

logger = logging.getLogger("lendwise")
bp = Blueprint("main", __name__)


@bp.get("/health")
def health():  # DECOY:D2:mfa
    return jsonify(status="ok")


@bp.post("/applications")
@require_mfa
def create_application():
    data = request.get_json(force=True)
    ssn = data["ssn"]
    ssn_last4 = ssn[-4:]
    logger.info("application received ssn_last4=%s", ssn_last4)  # DECOY:D1:log
    conn = db.connect()
    cur = conn.execute("INSERT INTO customers (name, email) VALUES (?, ?)", (data["name"], data["email"]))
    app_id = conn.execute(
        "INSERT INTO applications (customer_id, ssn, account_number, amount) VALUES (?, ?, ?, ?)",
        (cur.lastrowid, ssn, data["account_number"], data["amount"]),
    ).lastrowid
    conn.commit()
    conn.close()
    return jsonify(id=app_id, status="received"), 201


@bp.get("/profile")
@require_mfa
def profile():
    customer_id = request.headers.get("X-Customer-Id", "1")
    conn = db.connect()
    row = conn.execute("SELECT id, name, email FROM customers WHERE id = ?", (customer_id,)).fetchone()
    conn.close()
    if row is None:
        return jsonify(error="not found"), 404
    return jsonify(dict(row))


@bp.post("/incidents")
@require_mfa
def report_incident():
    """Staff report a data event; returns the FTC notification deadline when one applies."""
    return jsonify(incidents.handle_notification_event(request.get_json(force=True)))


def create_app() -> Flask:
    app = Flask(__name__)
    logging_mw.init_logging()
    logging_mw.register(app)
    app.register_blueprint(bp)
    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(support_legacy.bp, url_prefix="/support")
    return app
