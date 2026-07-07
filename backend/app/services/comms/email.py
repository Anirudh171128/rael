"""Email outreach. Provider waterfall: Resend → SendGrid → SMTP → mock.

SMTP reuses the same credentials that already send the login OTPs, so outreach
emails go out for real without any extra API key. Mock logs and returns a
synthetic message id so the Outreach Agent's flow completes offline.
"""
from __future__ import annotations

import asyncio
import hashlib
import smtplib
from email.message import EmailMessage

import httpx

from ...config import settings


def _smtp_send(to: str, subject: str, body: str, from_name: str) -> None:
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{settings.smtp_username or settings.smtp_from}>"
    msg["To"] = to
    server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
    server.starttls()
    server.login(settings.smtp_username, settings.smtp_password)
    server.send_message(msg)
    server.quit()


async def send_email(to: str, subject: str, body: str, *, from_name: str = "Rael") -> dict:
    errors: list[str] = []

    if settings.resend_api_key:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                    json={
                        "from": f"{from_name} <{settings.smtp_from}>",
                        "to": [to],
                        "subject": subject,
                        "text": body,
                    },
                )
            if r.status_code < 300:
                return {"sent": True, "provider": "resend", "message_id": r.json().get("id"), "to": to}
            errors.append(f"resend {r.status_code}: {r.text[:200]}")
        except Exception as exc:
            errors.append(f"resend: {exc}")

    if settings.sendgrid_api_key:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
                    json={
                        "personalizations": [{"to": [{"email": to}]}],
                        "from": {"email": settings.smtp_from, "name": from_name},
                        "subject": subject,
                        "content": [{"type": "text/plain", "value": body}],
                    },
                )
            if r.status_code < 300:
                return {"sent": True, "provider": "sendgrid", "to": to}
            detail = f"sendgrid {r.status_code}: {r.text[:200]}"
            if r.status_code == 401:
                key = settings.sendgrid_api_key
                detail += (
                    f" [key fingerprint: len={len(key)},"
                    f" starts_with_SG={key.startswith('SG.')},"
                    f" ends={key[-4:] if len(key) >= 4 else '?'}]"
                )
            errors.append(detail)
        except Exception as exc:
            errors.append(f"sendgrid: {exc}")

    if settings.smtp_username and settings.smtp_password:
        try:
            await asyncio.to_thread(_smtp_send, to, subject, body, from_name)
            return {"sent": True, "provider": "smtp", "to": to}
        except Exception as exc:  # fall through to mock so the pipeline never stalls
            errors.append(f"smtp: {exc}")
            return {"sent": False, "provider": "smtp", "error": "; ".join(errors), "to": to}

    msg_id = "mock-" + hashlib.md5(f"{to}{subject}".encode()).hexdigest()[:12]
    return {"sent": True, "provider": "mock", "message_id": msg_id, "to": to, "errors": errors}
