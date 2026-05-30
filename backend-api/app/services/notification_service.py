from __future__ import annotations

import asyncio
from functools import lru_cache

import structlog
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from twilio.rest import Client as TwilioClient

from app.core.config import settings

logger = structlog.get_logger(__name__)


# ── Client singletons ──────────────────────────────────────────────────────────
# Instantiated once and reused — no per-request construction overhead.

@lru_cache(maxsize=1)
def _get_twilio() -> TwilioClient:
    return TwilioClient(
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_AUTH_TOKEN,
    )


@lru_cache(maxsize=1)
def _get_sendgrid() -> SendGridAPIClient:
    return SendGridAPIClient(settings.SENDGRID_API_KEY)


# ── SMS ────────────────────────────────────────────────────────────────────────

async def send_sms_otp(phone: str, otp: str) -> None:
    """
    Send a login/verification OTP via Twilio SMS.
    Runs the blocking Twilio SDK call in a thread-pool executor
    so it never blocks the async event loop.
    """
    def _send() -> None:
        _get_twilio().messages.create(
            body=(
                f"Your verification code is: {otp}. "
                f"Valid for 10 minutes. Do not share it with anyone."
            ),
            from_=settings.TWILIO_FROM_NUMBER,
            to=phone,
        )

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send)
        logger.info(
            "sms_sent",
            phone_masked=phone[:4] + "****" + phone[-2:],
        )
    except Exception as exc:
        # Log and continue — caller already returned 202.
        # In production push failed jobs to a retry queue
        # (Celery + Redis / AWS SQS).
        logger.error("sms_send_failed", error=str(exc))


# ── Email ──────────────────────────────────────────────────────────────────────

async def send_email_otp(
    email: str,
    name: str,
    otp: str,
) -> None:
    """Send a login OTP via SendGrid."""
    message = Mail(
        from_email=(settings.EMAIL_FROM, settings.EMAIL_FROM_NAME),
        to_emails=email,
        subject="Your login code",
        html_content=_login_otp_html(name, otp),
    )
    await _send_email(message)


async def send_email_verification(
    email: str,
    name: str,
    otp: str,
) -> None:
    """
    Send an email verification message after registration.
    The verify URL embeds a compound token: base64(email:otp).
    The frontend /verify/email page decodes it and POSTs to the API.
    """
    import base64
    raw = f"{email}:{otp}"
    token = base64.urlsafe_b64encode(raw.encode()).decode()
    verify_url = f"https://yourdomain.com/verify/email?token={token}"

    message = Mail(
        from_email=(settings.EMAIL_FROM, settings.EMAIL_FROM_NAME),
        to_emails=email,
        subject="Verify your email address",
        html_content=_verify_email_html(name, otp, verify_url),
    )
    await _send_email(message)


async def send_password_reset_email(
    email: str,
    name: str,
    token: str,
) -> None:
    """Send a password reset link."""
    reset_url = f"https://yourdomain.com/reset-password?token={token}"
    message = Mail(
        from_email=(settings.EMAIL_FROM, settings.EMAIL_FROM_NAME),
        to_emails=email,
        subject="Reset your password",
        html_content=_password_reset_html(name, reset_url),
    )
    await _send_email(message)


# ── Shared send helper ─────────────────────────────────────────────────────────

async def _send_email(message: Mail) -> None:
    """Run the blocking SendGrid call in a thread-pool executor."""
    def _send() -> None:
        _get_sendgrid().send(message)

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send)
        logger.info(
            "email_sent",
            to=message.to[0].email if message.to else "unknown",
        )
    except Exception as exc:
        logger.error("email_send_failed", error=str(exc))


# ── HTML templates ─────────────────────────────────────────────────────────────
# Keep templates here for simplicity.
# In production move to SendGrid Dynamic Templates
# and reference them by template_id instead.

def _login_otp_html(name: str, otp: str) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#4F46E5">Your login code</h2>
      <p>Hi {name},</p>
      <p>Use the code below to sign in. It expires in <strong>10 minutes</strong>.</p>
      <div style="
        font-size:32px;font-weight:bold;letter-spacing:8px;
        background:#F3F4F6;padding:16px 24px;
        border-radius:8px;text-align:center;color:#111827;
        margin:24px 0
      ">{otp}</div>
      <p style="color:#6B7280;font-size:13px">
        Never share this code with anyone.
        Our team will never ask for it.
      </p>
    </div>
    """


def _verify_email_html(
    name: str,
    otp: str,
    verify_url: str,
) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#4F46E5">Verify your email</h2>
      <p>Hi {name}, welcome! Please verify your email address.</p>
      <a href="{verify_url}" style="
        display:inline-block;background:#4F46E5;color:#fff;
        padding:12px 24px;border-radius:8px;
        text-decoration:none;font-weight:bold;margin:16px 0
      ">Verify email</a>
      <p style="color:#6B7280;font-size:13px">
        Or enter this code manually: <strong>{otp}</strong>
      </p>
      <p style="color:#6B7280;font-size:13px">
        This link expires in 10 minutes.
        If you did not create an account, ignore this email.
      </p>
    </div>
    """


def _password_reset_html(name: str, reset_url: str) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#4F46E5">Reset your password</h2>
      <p>Hi {name},</p>
      <p>Click the button below to reset your password.
         This link expires in <strong>30 minutes</strong>.</p>
      <a href="{reset_url}" style="
        display:inline-block;background:#4F46E5;color:#fff;
        padding:12px 24px;border-radius:8px;
        text-decoration:none;font-weight:bold;margin:16px 0
      ">Reset password</a>
      <p style="color:#6B7280;font-size:13px">
        If you did not request this, ignore this email.
        Your password will not change.
      </p>
    </div>
    """
