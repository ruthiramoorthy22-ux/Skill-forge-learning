from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import decode_token

COOKIE = "__session"


def read_token(request: Request):
    """Web uses an HttpOnly cookie; the Android app sends a Bearer token."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = read_token(request)
    user_id = decode_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="You are not signed in.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    # Role is read from the database on every request, never from the token or the client.
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user
