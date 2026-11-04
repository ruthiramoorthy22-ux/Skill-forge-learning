"""Razorpay integration. Orders are created on the server and payments are verified on the server by checking Razorpay's
signature. A success message from the browser is never trusted. Keys come only from environment variables."""
import hashlib
import hmac

import httpx

from .config import settings


class PaymentsUnavailable(Exception):
    pass


def configured() -> bool:
    return bool(settings.razorpay_key_id and settings.razorpay_key_secret)


def create_order(amount_paise: int, receipt: str, notes: dict) -> dict:
    if not configured():
        raise PaymentsUnavailable("Payments are not configured yet.")
    try:
        r = httpx.post("https://api.razorpay.com/v1/orders", auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
                       json={"amount": amount_paise, "currency": "INR", "receipt": receipt[:40], "notes": notes}, timeout=20)
    except httpx.HTTPError:
        raise PaymentsUnavailable("The payment service could not be reached.")
    if r.status_code >= 400:
        raise PaymentsUnavailable("The payment service rejected the request.")
    return r.json()


def _hmac(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    if not settings.razorpay_key_secret:
        return False
    return hmac.compare_digest(_hmac(settings.razorpay_key_secret, f"{order_id}|{payment_id}".encode()), signature or "")


def verify_webhook(body: bytes, signature: str) -> bool:
    if not settings.razorpay_webhook_secret:
        return False
    return hmac.compare_digest(_hmac(settings.razorpay_webhook_secret, body), signature or "")


def _get(path: str) -> dict:
    try:
        r = httpx.get(f"https://api.razorpay.com/v1{path}", auth=(settings.razorpay_key_id, settings.razorpay_key_secret), timeout=20)
    except httpx.HTTPError:
        raise PaymentsUnavailable("The payment service could not be reached.")
    if r.status_code >= 400:
        raise PaymentsUnavailable("The payment service rejected the request.")
    return r.json()


def ensure_captured(order_id: str, payment_id: str, amount_minor: int) -> dict:
    """After the signature check, asks Razorpay for the payment itself: it must belong to this order, be for the exact
    amount we asked for, and be captured (an 'authorized' payment is captured now). Returns Razorpay's payment record.
    Raises PaymentsUnavailable when the money is not really received."""
    if not configured():
        raise PaymentsUnavailable("Payments are not configured yet.")
    p = _get(f"/payments/{payment_id}")
    if p.get("order_id") != order_id or p.get("amount") != amount_minor or p.get("currency") != "INR":
        raise PaymentsUnavailable("This payment does not match the order.")
    if p.get("status") == "authorized":
        try:
            r = httpx.post(f"https://api.razorpay.com/v1/payments/{payment_id}/capture",
                           auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
                           json={"amount": amount_minor, "currency": "INR"}, timeout=20)
        except httpx.HTTPError:
            raise PaymentsUnavailable("The payment service could not be reached.")
        if r.status_code >= 400:
            raise PaymentsUnavailable("The payment could not be captured.")
        p = r.json()
    if p.get("status") != "captured":
        raise PaymentsUnavailable("The payment is not completed yet.")
    return p


def upi_uri(vpa: str, payee: str, amount_inr: int, note: str, ref: str) -> str:
    """The upi://pay link that opens Google Pay, PhonePe, Paytm and every other UPI app."""
    from urllib.parse import quote
    return (f"upi://pay?pa={quote(vpa, safe='@')}&pn={quote(payee)}&am={amount_inr:.2f}&cu=INR&tn={quote(note[:50])}&tr={quote(ref[:35])}")
