"""Settings the admin can change while the app runs. One certificate price applies to every course."""
from sqlalchemy.orm import Session

from .config import settings
from .models import AppSetting

PRICE_KEY = "certificate_price_inr"
RELEASE_KEY = "certificate_release"  # auto: issued right after payment | admin: the admin must unlock it
MAX_PRICE = 100_000


def _get(db: Session, key: str):
    row = db.get(AppSetting, key)
    return row.value if row else None


def _set(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


def get_price(db: Session) -> int:
    v = _get(db, PRICE_KEY)
    try:
        return int(v) if v is not None else settings.certificate_price_inr
    except ValueError:
        return settings.certificate_price_inr


def set_price(db: Session, rupees: int) -> None:
    _set(db, PRICE_KEY, str(int(rupees)))


def get_release_mode(db: Session) -> str:
    return "admin" if _get(db, RELEASE_KEY) == "admin" else "auto"


def set_release_mode(db: Session, mode: str) -> None:
    _set(db, RELEASE_KEY, "admin" if mode == "admin" else "auto")


PROJECT_KEY = "project_required"  # 1: a student needs an approved project before the certificate (default: on)


def get_project_required(db: Session) -> bool:
    return _get(db, PROJECT_KEY) != "0"  # on unless the admin switches it off


def set_project_required(db: Session, on: bool) -> None:
    _set(db, PROJECT_KEY, "1" if on else "0")


# --------------------------------------------------------------------------- payment methods (the admin chooses what students can use)
import re  # noqa: E402

RZP_ENABLED_KEY = "pay_razorpay_enabled"   # Razorpay Standard Checkout (UPI, GPay, PhonePe, cards, net banking)
UPI_ENABLED_KEY = "pay_upi_enabled"        # direct UPI to the admin's UPI id, confirmed by the admin
UPI_ID_KEY = "upi_id"
UPI_NAME_KEY = "upi_payee_name"
RZP_METHODS_KEY = "razorpay_methods"       # comma list of the Razorpay methods that are shown
RZP_ALL_METHODS = ("upi", "card", "netbanking", "wallet")
UPI_RE = re.compile(r"^[A-Za-z0-9._\-]{2,64}@[A-Za-z][A-Za-z0-9]{1,31}$")


def razorpay_enabled(db: Session) -> bool:
    return _get(db, RZP_ENABLED_KEY) != "0"  # on by default


def upi_enabled(db: Session) -> bool:
    return _get(db, UPI_ENABLED_KEY) == "1" and bool(get_upi_id(db))  # off by default, and needs a UPI id


def get_upi_id(db: Session) -> str:
    return _get(db, UPI_ID_KEY) or ""


def get_upi_name(db: Session) -> str:
    return _get(db, UPI_NAME_KEY) or settings.brand_name


def razorpay_methods(db: Session) -> list:
    v = _get(db, RZP_METHODS_KEY)
    if v is None:
        return list(RZP_ALL_METHODS)
    return [m for m in v.split(",") if m in RZP_ALL_METHODS]


def set_payment_settings(db: Session, *, razorpay_enabled=None, upi_enabled=None, upi_id=None, upi_payee_name=None,
                         razorpay_methods=None) -> None:
    if razorpay_enabled is not None:
        _set(db, RZP_ENABLED_KEY, "1" if razorpay_enabled else "0")
    if upi_enabled is not None:
        _set(db, UPI_ENABLED_KEY, "1" if upi_enabled else "0")
    if upi_id is not None:
        _set(db, UPI_ID_KEY, upi_id.strip())
    if upi_payee_name is not None:
        _set(db, UPI_NAME_KEY, upi_payee_name.strip()[:80])
    if razorpay_methods is not None:
        _set(db, RZP_METHODS_KEY, ",".join(m for m in RZP_ALL_METHODS if m in razorpay_methods))
