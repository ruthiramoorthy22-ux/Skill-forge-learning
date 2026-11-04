from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import settings

_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: Optional[str], password: str) -> bool:
    """Always does one hash verification, so unknown emails take similar time."""
    try:
        return _ph.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(hours=settings.session_hours)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return None if "scope" in payload else payload.get("sub")  # scoped tokens (download links) are never sessions


def create_link_token(certificate_id: str) -> str:
    """Five-minute link for ONE certificate, so the Android app can open a download without custom headers."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    return jwt.encode({"sub": certificate_id, "scope": "certificate", "exp": exp}, settings.jwt_secret, algorithm="HS256")


def check_link_token(token: str, certificate_id: str) -> bool:
    try:
        p = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return False
    return p.get("scope") == "certificate" and p.get("sub") == certificate_id
