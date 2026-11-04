import smtplib
from email.message import EmailMessage
from typing import List, Tuple

from .config import settings


class MailUnavailable(Exception):
    pass


def configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def send_mail(to: str, subject: str, body: str, attachments: List[Tuple[str, bytes, str]] = ()) -> None:
    if not configured():
        raise MailUnavailable("Email is not configured.")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, to, subject
    msg.set_content(body)
    for filename, data, mime in attachments:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    except (smtplib.SMTPException, OSError):
        raise MailUnavailable("The email could not be sent.")
