import os
import secrets
from pathlib import Path


class Settings:
    def __init__(self):
        self.env = os.getenv("APP_ENV", "development")
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./skillforge.db")
        self.admin_email = os.getenv("ADMIN_EMAIL", "skillforgelearning22@gmail.com").strip().lower()
        self.session_hours = int(os.getenv("SESSION_HOURS", "8"))
        self.cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost,capacitor://localhost").split(",") if o.strip()]
        self.razorpay_key_id = os.getenv("RAZORPAY_KEY_ID", "").strip()
        self.razorpay_key_secret = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
        self.razorpay_webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()
        self.brand_name = os.getenv("BRAND_NAME", "SkillForge AI").strip() or "SkillForge AI"  # shown in the Razorpay checkout
        self.certificate_price_inr = int(os.getenv("CERTIFICATE_PRICE_INR", "55"))
        self.final_unlock_rule = os.getenv("FINAL_UNLOCK_RULE", "attempted")  # attempted | passed
        self.smtp_host = os.getenv("SMTP_HOST", "").strip()
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "").strip()
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from = os.getenv("SMTP_FROM", "").strip()
        self.online_timeout_seconds = int(os.getenv("ONLINE_TIMEOUT_SECONDS", "150"))
        self.jwt_secret = self._secret()

    @property
    def razorpay_mode(self) -> str:
        """test or live, read from the key id (rzp_test_... / rzp_live_...). Empty when no key is set."""
        k = self.razorpay_key_id
        return "live" if k.startswith("rzp_live_") else "test" if k.startswith("rzp_test_") else ""

    def _secret(self) -> str:
        value = os.getenv("JWT_SECRET")
        if value:
            return value
        if self.env == "production":
            raise RuntimeError("JWT_SECRET must be set when APP_ENV=production")
        path = Path(".dev_jwt_secret")  # development only; gitignored
        if path.exists():
            return path.read_text().strip()
        value = secrets.token_urlsafe(48)
        path.write_text(value)
        return value


settings = Settings()
