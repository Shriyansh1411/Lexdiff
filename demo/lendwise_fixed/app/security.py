"""Authentication helpers for the Lendwise demo (a fictional non-bank lender)."""
import base64
import hashlib
import hmac
import struct
import time
from functools import wraps

from flask import jsonify, request

SECRET_KEY = "lendwise-dev-secret"  # PLANTED:V11:secret
TOTP_SECRET = base64.b32encode(b"lendwise-demo-totp").decode()
MFA_HEADER = "X-MFA-Code"


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()  # PLANTED:V10:crypto


def issue_token(subject: str) -> str:
    return hmac.new(SECRET_KEY.encode(), subject.encode(), hashlib.sha256).hexdigest()


def totp(secret_b32: str, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    """RFC 6238 time-based one-time password."""
    counter = int((time.time() if at is None else at) // step)
    digest = hmac.new(base64.b32decode(secret_b32), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def current_totp() -> str:
    return totp(TOTP_SECRET)


def verify_totp(code: str) -> bool:
    now = time.time()
    return any(hmac.compare_digest(code or "", totp(TOTP_SECRET, now + drift * 30)) for drift in (-1, 0, 1))


def require_mfa(view):
    """Reject the request unless a valid second factor is presented."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not verify_totp(request.headers.get(MFA_HEADER, "")):
            resp = jsonify(error="second factor required")
            resp.status_code = 401
            resp.headers["X-MFA-Required"] = "true"
            return resp
        return view(*args, **kwargs)
    return wrapper


def mask_ssn(ssn: str) -> str:
    return "***-**-" + ssn[-4:]
