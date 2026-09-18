---
sidebar_position: 5
title: API Reference
---

# API Reference

Base URL: `http://localhost:8002`

All endpoints require `Authorization: Bearer <token>` header unless noted.

## Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new account |
| POST | `/api/auth/login` | Login, returns JWT token |
| GET | `/api/auth/me` | Get current user info |
| PUT | `/api/auth/change-password` | Change password |
| DELETE | `/api/auth/account` | Delete account and all data |
| PUT | `/api/auth/webhook` | Set webhook notification URL |

## Meetings

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/meetings/upload` | Upload audio file (multipart/form-data) |
| GET | `/api/meetings/list` | List meetings (paginated, filterable) |
| GET | `/api/meetings/search?q=term` | Cross-meeting full-text search |
| GET | `/api/meetings/templates` | List available meeting templates |
| GET | `/api/meetings/{id}` | Get meeting details |
| PATCH | `/api/meetings/{id}` | Update meeting (title, summary, etc.) |
| DELETE | `/api/meetings/{id}` | Delete meeting |
| POST | `/api/meetings/{id}/retry` | Retry failed processing |
| POST | `/api/meetings/{id}/chat` | AI chat (SSE streaming response) |

### Organization

| Method | Endpoint | Description |
|--------|----------|-------------|
| PATCH | `/api/meetings/{id}/favorite` | Toggle favorite |
| PATCH | `/api/meetings/{id}/tags` | Update tags |
| POST | `/api/meetings/bulk-delete` | Delete multiple meetings |

### Sharing

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/meetings/{id}/share` | Generate share link |
| DELETE | `/api/meetings/{id}/share` | Revoke share link |
| GET | `/api/meetings/shared/{token}` | Get shared meeting (no auth) |

### Audio

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/meetings/audio/{filename}` | Stream/download audio file |

## List Meetings Query Params

```
GET /api/meetings/list?page=1&per_page=20&sort=newest&status=completed&q=search&favorite=true&tag=project
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| page | int | 1 | Page number |
| per_page | int | 20 | Items per page (max 100) |
| sort | string | newest | newest, oldest, longest, shortest |
| status | string | — | completed, processing, failed |
| q | string | — | Search title/transcript/summary |
| favorite | bool | — | Filter favorites only |
| tag | string | — | Filter by tag |

## Health Check

```
GET /health
```

Returns service health with dependency checks (no auth required):

```json
{
  "status": "healthy",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "storage": "ok"
  },
  "version": "1.0.0"
}
```
