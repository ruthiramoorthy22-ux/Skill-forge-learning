"""Provision the administrator account.  Run:  python -m app.create_admin
The password is typed at a hidden prompt. It is never stored in code or files."""
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, SessionLocal, engine
from .models import User
from .security import hash_password


def create_admin(db: Session, email: str, password: str, display_name: str = "Administrator") -> User:
    if len(password) < 12:
        raise ValueError("Admin password must be at least 12 characters.")
    email = email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, display_name=display_name, password_hash=hash_password(password), role="admin")
        db.add(user)
    else:
        user.password_hash = hash_password(password)
        user.role, user.status = "admin", "active"
    db.commit()
    return user


def main() -> None:
    Base.metadata.create_all(engine)
    email = settings.admin_email
    print(f"Provisioning administrator account for {email}")
    pw = getpass.getpass("New admin password (min 12 characters): ")
    if pw != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    try:
        with SessionLocal() as db:
            create_admin(db, email, pw)
    except ValueError as e:
        sys.exit(str(e))
    print("Done. Sign in at /admin/login.")


if __name__ == "__main__":
    main()
