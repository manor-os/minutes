---
sidebar_position: 6
title: Webhooks
---

# Webhook Notifications

Get notified when a meeting is processed via Slack, Discord, or any webhook URL.

## Setup

1. Go to **Settings** → **Notifications**
2. Enter your webhook URL
3. Save

## Supported Formats

| Service | URL Pattern | Format |
|---------|-------------|--------|
| Slack | `hooks.slack.com/services/...` | Slack Block Kit |
| Discord | `discord.com/api/webhooks/...` | Discord message |
| Generic | Any HTTPS URL | JSON payload |

## Payload (Generic)

```json
{
  "event": "meeting.completed",
  "meeting": {
    "title": "Team Standup",
    "summary": "...",
    "key_points_count": 5,
    "action_items_count": 3,
    "duration": 600
  }
}
```

## Slack/Discord Message

```
*Team Standup* is ready!
> Brief summary of the meeting...
📌 5 key points · ✅ 3 action items · ⏱ 10m
```
