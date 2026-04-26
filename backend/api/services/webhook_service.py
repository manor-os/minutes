"""
Webhook notification service -- sends meeting completion notifications.
Supports Slack, Discord, and generic webhook URLs.
"""
import httpx
from loguru import logger


async def send_webhook_notification(webhook_url: str, meeting: dict):
    """Send a webhook notification about a completed meeting."""
    if not webhook_url:
        return

    title = meeting.get("title", "Untitled Meeting")
    summary = meeting.get("summary", "")[:500]
    key_points_count = len(meeting.get("key_points", []) or [])
    action_items_count = len(meeting.get("action_items", []) or [])
    duration = meeting.get("duration", 0) or 0

    # Detect webhook type and format accordingly
    if "hooks.slack.com" in webhook_url or "discord.com/api/webhooks" in webhook_url:
        payload = _format_slack_discord(webhook_url, title, summary, key_points_count, action_items_count, duration)
    else:
        # Generic webhook
        payload = {
            "event": "meeting.completed",
            "meeting": {
                "title": title,
                "summary": summary,
                "key_points_count": key_points_count,
                "action_items_count": action_items_count,
                "duration": duration,
            }
        }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=payload)
            if response.status_code < 300:
                logger.info(f"Webhook sent to {webhook_url[:40]}...")
            else:
                logger.warning(f"Webhook returned {response.status_code}: {response.text[:200]}")
    except Exception as e:
        logger.error(f"Webhook failed: {e}")


def send_webhook_notification_sync(webhook_url: str, meeting: dict):
    """Synchronous version for use in Celery tasks."""
    if not webhook_url:
        return

    title = meeting.get("title", "Untitled Meeting")
    summary = (meeting.get("summary", "") or "")[:500]
    key_points_count = len(meeting.get("key_points", []) or [])
    action_items_count = len(meeting.get("action_items", []) or [])
    duration = meeting.get("duration", 0) or 0

    if "hooks.slack.com" in webhook_url or "discord.com/api/webhooks" in webhook_url:
        payload = _format_slack_discord(webhook_url, title, summary, key_points_count, action_items_count, duration)
    else:
        payload = {
            "event": "meeting.completed",
            "meeting": {
                "title": title,
                "summary": summary,
                "key_points_count": key_points_count,
                "action_items_count": action_items_count,
                "duration": duration,
            }
        }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(webhook_url, json=payload)
            if resp.status_code < 300:
                logger.info(f"Webhook sent to {webhook_url[:40]}...")
            else:
                logger.warning(f"Webhook returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Webhook failed: {e}")


def _format_slack_discord(url: str, title: str, summary: str, key_points: int, actions: int, duration: int):
    """Format for Slack incoming webhooks (also works with Discord)."""
    mins = duration // 60 if duration else 0

    text = f"*{title}* is ready!\n"
    if summary:
        text += f">{summary[:300]}\n"
    text += f"\U0001f4cc {key_points} key points \u00b7 \u2705 {actions} action items \u00b7 \u23f1 {mins}m"

    if "discord.com" in url:
        return {"content": text}
    return {"text": text}
