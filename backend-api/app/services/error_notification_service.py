"""
app/services/error_notification_service.py
────────────────────────────────────────────
Builds a rich error report and emails it to the support team.

Every report contains:
  WHAT  — exception type, message, full traceback
  WHEN  — UTC timestamp
  WHO   — user ID, email, username (if authenticated)
  WHERE — IP, city, country, ISP, user agent, device type
  WHICH — HTTP method, URL, endpoint, request body (sanitised)
  ENV   — app version, environment, server hostname
"""
from __future__ import annotations

import asyncio
import platform
import traceback
from datetime import datetime, timezone
from typing import Any

import structlog
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.core.config import settings
from app.utils.ip_info import get_ip_location

logger = structlog.get_logger(__name__)

# Fields that must NEVER appear in error reports
_SENSITIVE_FIELDS = {
    "password", "hashed_password", "token",
    "access_token", "refresh_token", "otp",
    "secret_key", "api_key", "authorization",
    "new_password", "current_password",
}


def _sanitise_body(body: dict) -> dict:
    """
    Recursively remove sensitive fields from request body
    before including in error report.
    """
    if not isinstance(body, dict):
        return {}
    return {
        k: "*** REDACTED ***" if k.lower() in _SENSITIVE_FIELDS
        else _sanitise_body(v) if isinstance(v, dict)
        else v
        for k, v in body.items()
    }


async def build_error_report(
    exc: Exception,
    request_info: dict,
    user_info: dict | None = None,
) -> dict:
    """
    Assemble a complete error report dict.

    Args:
        exc:          The unhandled exception.
        request_info: Dict from _extract_request_info() in middleware.
        user_info:    Dict with user id/email/username or None
                      if the request was unauthenticated.
    """
    ip = request_info.get("ip", "unknown")
    location = await get_ip_location(ip)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),

        "error": {
            "type":       type(exc).__name__,
            "message":    str(exc),
            "traceback":  traceback.format_exc(),
        },

        "request": {
            "method":   request_info.get("method", ""),
            "url":      request_info.get("url", ""),
            "endpoint": request_info.get("endpoint", ""),
            "body":     _sanitise_body(
                request_info.get("body", {})
            ),
            "headers":  {
                k: v for k, v in
                request_info.get("headers", {}).items()
                if k.lower() not in {
                    "authorization", "cookie", "x-api-key"
                }
            },
        },

        "user": user_info or {
            "id":       "unauthenticated",
            "email":    "—",
            "username": "—",
        },

        "location": {
            "ip":           ip,
            "city":         location.get("city", "Unknown"),
            "region":       location.get("region", ""),
            "country":      location.get("country", "Unknown"),
            "isp":          location.get("isp", "Unknown"),
            "timezone":     location.get("timezone", ""),
            "user_agent":   request_info.get("user_agent", ""),
        },

        "environment": {
            "app_version": settings.APP_VERSION,
            "app_env":     settings.APP_ENV,
            "hostname":    platform.node(),
            "python":      platform.python_version(),
        },
    }


def _render_html_report(report: dict) -> str:
    """Render the error report as a readable HTML email."""
    err      = report["error"]
    req      = report["request"]
    user     = report["user"]
    loc      = report["location"]
    env      = report["environment"]
    ts       = report["timestamp"]

    # Colour-coded severity header
    header_color = "#DC2626"   # red for errors

    tb_html = err["traceback"].replace(
        "\n", "<br>"
    ).replace(" ", "&nbsp;")

    body_html = str(req["body"]).replace(
        "\n", "<br>"
    ).replace(" ", "&nbsp;")

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
      body {{
        font-family: Arial, sans-serif;
        font-size: 14px;
        color: #111827;
        margin: 0; padding: 0;
      }}
      .header {{
        background: {header_color};
        color: white;
        padding: 20px 24px;
      }}
      .header h1 {{
        margin: 0;
        font-size: 20px;
      }}
      .header p {{
        margin: 4px 0 0;
        font-size: 13px;
        opacity: 0.85;
      }}
      .section {{
        margin: 0;
        padding: 16px 24px;
        border-bottom: 1px solid #E5E7EB;
      }}
      .section h2 {{
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #6B7280;
        margin: 0 0 10px;
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
      }}
      td {{
        padding: 5px 0;
        vertical-align: top;
      }}
      td:first-child {{
        color: #6B7280;
        width: 160px;
        font-size: 13px;
      }}
      .traceback {{
        background: #1F2937;
        color: #F9FAFB;
        padding: 14px;
        border-radius: 6px;
        font-family: monospace;
        font-size: 12px;
        overflow-x: auto;
        white-space: pre-wrap;
        word-break: break-all;
        margin-top: 8px;
      }}
      .badge {{
        display: inline-block;
        padding: 2px 8px;
        border-radius: 9999px;
        font-size: 12px;
        font-weight: bold;
        background: #FEE2E2;
        color: #991B1B;
      }}
    </style>
    </head>
    <body>

    <div class="header">
      <h1>🚨 Unhandled Exception — {env["app_env"].upper()}</h1>
      <p>{ts} &nbsp;|&nbsp; {env["app_version"]} &nbsp;|&nbsp;
         {env["hostname"]}</p>
    </div>

    <div class="section">
      <h2>Error</h2>
      <table>
        <tr>
          <td>Type</td>
          <td><span class="badge">{err["type"]}</span></td>
        </tr>
        <tr>
          <td>Message</td>
          <td>{err["message"]}</td>
        </tr>
      </table>
      <div class="traceback">{tb_html}</div>
    </div>

    <div class="section">
      <h2>Request</h2>
      <table>
        <tr><td>Method</td><td>{req["method"]}</td></tr>
        <tr><td>URL</td><td>{req["url"]}</td></tr>
        <tr><td>Endpoint</td><td>{req["endpoint"]}</td></tr>
        <tr>
          <td>Body</td>
          <td><code>{body_html}</code></td>
        </tr>
      </table>
    </div>

    <div class="section">
      <h2>Who</h2>
      <table>
        <tr><td>User ID</td><td>{user["id"]}</td></tr>
        <tr><td>Email</td><td>{user["email"]}</td></tr>
        <tr><td>Username</td><td>{user["username"]}</td></tr>
      </table>
    </div>

    <div class="section">
      <h2>Where</h2>
      <table>
        <tr><td>IP Address</td><td>{loc["ip"]}</td></tr>
        <tr>
          <td>Location</td>
          <td>
            {loc["city"]}, {loc["region"]},
            {loc["country"]}
          </td>
        </tr>
        <tr><td>ISP</td><td>{loc["isp"]}</td></tr>
        <tr><td>Timezone</td><td>{loc["timezone"]}</td></tr>
        <tr>
          <td>User Agent</td>
          <td style="font-size:12px">{loc["user_agent"]}</td>
        </tr>
      </table>
    </div>

    <div class="section">
      <h2>Environment</h2>
      <table>
        <tr>
          <td>App Version</td>
          <td>{env["app_version"]}</td>
        </tr>
        <tr>
          <td>Environment</td>
          <td>{env["app_env"]}</td>
        </tr>
        <tr>
          <td>Hostname</td>
          <td>{env["hostname"]}</td>
        </tr>
        <tr>
          <td>Python</td>
          <td>{env["python"]}</td>
        </tr>
      </table>
    </div>

    </body>
    </html>
    """


async def send_support_alert(report: dict) -> None:
    """
    Email the rendered error report to the support team.
    Runs in a thread-pool executor so it never blocks the
    event loop — even if SendGrid is slow.
    Failures are logged but never re-raised.
    """
    if not settings.ERROR_NOTIFICATIONS_ENABLED:
        return

    if not settings.SENDGRID_API_KEY:
        logger.warning(
            "support_alert_skipped",
            reason="SENDGRID_API_KEY not configured",
        )
        return

    err = report["error"]
    env = report["environment"]
    ts  = report["timestamp"]
    subject = (
        f"[{env['app_env'].upper()}] "
        f"{err['type']}: {err['message'][:80]} "
        f"— {ts}"
    )

    message = Mail(
        from_email=(
            settings.EMAIL_FROM,
            settings.EMAIL_FROM_NAME,
        ),
        to_emails=(
            settings.SUPPORT_EMAIL,
            settings.SUPPORT_EMAIL_NAME,
        ),
        subject=subject,
        html_content=_render_html_report(report),
    )

    def _send() -> None:
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        sg.send(message)

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send)
        logger.info(
            "support_alert_sent",
            error_type=err["type"],
            to=settings.SUPPORT_EMAIL,
        )
    except Exception as exc:
        # Log but never propagate — error reporting
        # must never cause a second error
        logger.error(
            "support_alert_failed",
            error=str(exc),
        )
