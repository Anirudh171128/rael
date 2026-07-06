"""WhatsApp Business Cloud API — the rep-facing notification channel.

The rep lives in WhatsApp; every notification carries up to 3 reply buttons
(approve / ignore / view) per the blueprint. Mock mode broadcasts the message to
the dashboard's WebSocket instead of Meta, so the approval surface is visible
offline. Live mode POSTs to the Graph API.
"""
from __future__ import annotations

import httpx

from ...config import settings
from ...websocket import manager


class WhatsAppTemplates:
    """The 8 notification shapes from the blueprint, as builders."""

    @staticmethod
    def hot_signal(contact: str, company: str, detail: str) -> dict:
        return {
            "kind": "hot_signal",
            "emoji": "🔥",
            "title": "HOT SIGNAL",
            "body": f"{contact} from {company} {detail}. This is a buying signal.",
            "buttons": ["Call now", "Send follow-up", "Ignore"],
        }

    @staticmethod
    def warm_reply(contact: str, company: str, quote: str) -> dict:
        return {
            "kind": "warm_reply",
            "emoji": "💬",
            "title": "WARM REPLY — needs you",
            "body": f'{contact} ({company}) replied: "{quote}". I\'ve drafted a response.',
            "buttons": ["Send it", "Edit first", "See thread"],
        }

    @staticmethod
    def meeting_booked(contact: str, company: str, when: str) -> dict:
        return {
            "kind": "meeting_booked",
            "emoji": "✅",
            "title": "MEETING BOOKED",
            "body": f"{contact} ({company}) confirmed for {when}. I'll send your brief 30 mins before.",
            "buttons": ["View", "Reschedule"],
        }

    @staticmethod
    def pre_call_brief(contact: str, company: str) -> dict:
        return {
            "kind": "brief",
            "emoji": "📋",
            "title": "YOUR CALL IN 30 MINS",
            "body": f"Brief ready for {contact} ({company}).",
            "buttons": ["Open brief"],
        }

    @staticmethod
    def morning_brief(lines: list[str]) -> dict:
        return {
            "kind": "morning_brief",
            "emoji": "📋",
            "title": "MORNING BRIEF",
            "body": "Good morning. Here's your day:\n" + "\n".join(f"• {l}" for l in lines),
            "buttons": ["Open dashboard"],
        }

    @staticmethod
    def end_of_day(lines: list[str]) -> dict:
        return {
            "kind": "end_of_day",
            "emoji": "🌙",
            "title": "END OF DAY",
            "body": "Today's summary:\n" + "\n".join(f"• {l}" for l in lines),
            "buttons": ["Full report"],
        }


async def send_whatsapp(message: dict) -> dict:
    """Deliver a notification. Always mirrors to the dashboard so the rep sees the
    approval surface; also POSTs to Meta when credentials are present."""
    await manager.broadcast({"channel": "whatsapp", **message})

    if not (settings.whatsapp_token and settings.whatsapp_phone_id and settings.whatsapp_rep_number):
        return {"sent": True, "provider": "mock", "mirrored_to_dashboard": True}

    url = f"https://graph.facebook.com/v21.0/{settings.whatsapp_phone_id}/messages"
    buttons = [
        {"type": "reply", "reply": {"id": f"btn_{i}", "title": b[:20]}}
        for i, b in enumerate(message.get("buttons", [])[:3])
    ]
    payload: dict = {
        "messaging_product": "whatsapp",
        "to": settings.whatsapp_rep_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": f"{message['emoji']} {message['title']}\n\n{message['body']}"},
            "action": {"buttons": buttons},
        },
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            url, json=payload, headers={"Authorization": f"Bearer {settings.whatsapp_token}"}
        )
    return {"sent": r.status_code < 300, "provider": "meta", "status": r.status_code}
