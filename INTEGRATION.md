# Meeting Note Taker API - Integration Guide for Manor AI

This document describes how to integrate the Meeting Note Taker API with Manor AI service using API key authentication.

## Overview

The Meeting Note Taker API supports two authentication methods:
1. **JWT Token** - For user-facing applications (web app, browser extension)
2. **API Key** - For service-to-service integration (Manor AI service)

## API Key Setup

### 1. Generate API Key

Set the `MEETING_NOTE_TAKER_API_KEY` environment variable in your `.env` file:

```env
MEETING_NOTE_TAKER_API_KEY=your-secure-api-key-here
```

**Important**: Use a strong, randomly generated API key in production!

### 2. Restart Services

After setting the API key, restart the backend service:

```bash
docker-compose restart backend
```

## API Endpoints

### Base URL

```
http://localhost:8001
```

### Authentication

All integration endpoints require the `X-API-Key` header:

```http
X-API-Key: your-secure-api-key-here
```

## Integration Endpoints

### 1. Health Check

Check if the API is accessible and your API key is valid.

**Endpoint**: `GET /api/integration/health`

**Headers**:
```http
X-API-Key: your-secure-api-key-here
```

**Response**:
```json
{
  "status": "healthy",
  "service": "meeting-note-taker",
  "authenticated": true,
  "auth_method": "api_key"
}
```

**Example**:
```bash
curl -X GET "http://localhost:8001/api/integration/health" \
  -H "X-API-Key: your-secure-api-key-here"
```

### 2. List Meetings

Get a list of meetings with optional filtering.

**Endpoint**: `GET /api/integration/meetings`

**Headers**:
```http
X-API-Key: your-secure-api-key-here
```

**Query Parameters**:
- `limit` (optional, default: 20) - Number of meetings to return
- `offset` (optional, default: 0) - Pagination offset
- `status` (optional) - Filter by status: `processing`, `completed`, `failed`
- `entity_id` (optional) - Filter by entity_id (for future use)

**Response**:
```json
{
  "success": true,
  "meetings": [
    {
      "id": "uuid",
      "title": "Meeting Title",
      "platform": "google_meet",
      "status": "completed",
      "duration": 3600,
      "transcript": "...",
      "summary": "...",
      "created_at": "2026-01-10T12:00:00Z",
      ...
    }
  ],
  "total": 100,
  "limit": 20,
  "offset": 0
}
```

**Example**:
```bash
curl -X GET "http://localhost:8001/api/integration/meetings?limit=10&status=completed" \
  -H "X-API-Key: your-secure-api-key-here"
```

### 3. Get Meeting Details

Get detailed information about a specific meeting.

**Endpoint**: `GET /api/integration/meetings/{meeting_id}`

**Headers**:
```http
X-API-Key: your-secure-api-key-here
```

**Response**:
```json
{
  "success": true,
  "meeting": {
    "id": "uuid",
    "title": "Meeting Title",
    "platform": "google_meet",
    "status": "completed",
    "duration": 3600,
    "transcript": "Full transcript...",
    "summary": "Meeting summary...",
    "key_points": ["Point 1", "Point 2"],
    "action_items": [...],
    "token_cost": {
      "transcription": {...},
      "summarization": {...},
      "total_cost": 0.0038
    },
    "created_at": "2026-01-10T12:00:00Z",
    ...
  }
}
```

**Example**:
```bash
curl -X GET "http://localhost:8001/api/integration/meetings/abc-123-def" \
  -H "X-API-Key: your-secure-api-key-here"
```

### 4. Get Statistics

Get statistics about meetings.

**Endpoint**: `GET /api/integration/stats`

**Headers**:
```http
X-API-Key: your-secure-api-key-here
```

**Response**:
```json
{
  "success": true,
  "stats": {
    "total_meetings": 150,
    "completed": 120,
    "processing": 5,
    "failed": 25
  }
}
```

**Example**:
```bash
curl -X GET "http://localhost:8001/api/integration/stats" \
  -H "X-API-Key: your-secure-api-key-here"
```

## Standard Meeting Endpoints (Also Support API Key)

All standard meeting endpoints also support API key authentication:

- `POST /api/meetings/upload` - Upload meeting audio
- `GET /api/meetings/list` - List meetings
- `GET /api/meetings/{meeting_id}` - Get meeting
- `PATCH /api/meetings/{meeting_id}` - Update meeting
- `DELETE /api/meetings/{meeting_id}` - Delete meeting
- `GET /api/meetings/{meeting_id}/transcript` - Get transcript
- `GET /api/meetings/{meeting_id}/summary` - Get summary

These endpoints accept either:
- `Authorization: Bearer <jwt_token>` (for user authentication)
- `X-API-Key: <api_key>` (for service authentication)

## Python Integration Example

```python
import requests

API_BASE_URL = "http://localhost:8001"
API_KEY = "your-secure-api-key-here"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# Health check
response = requests.get(f"{API_BASE_URL}/api/integration/health", headers=headers)
print(response.json())

# List meetings
response = requests.get(
    f"{API_BASE_URL}/api/integration/meetings",
    headers=headers,
    params={"limit": 10, "status": "completed"}
)
meetings = response.json()["meetings"]
print(f"Found {len(meetings)} meetings")

# Get specific meeting
meeting_id = meetings[0]["id"]
response = requests.get(
    f"{API_BASE_URL}/api/integration/meetings/{meeting_id}",
    headers=headers
)
meeting = response.json()["meeting"]
print(f"Meeting: {meeting['title']}")
print(f"Summary: {meeting['summary']}")
```

## Error Responses

All endpoints return standard HTTP status codes:

- `200 OK` - Success
- `400 Bad Request` - Invalid parameters
- `401 Unauthorized` - Invalid or missing API key
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

Error response format:
```json
{
  "detail": "Error message description"
}
```

## Security Best Practices

1. **Keep API Key Secret**: Never commit API keys to version control
2. **Use Environment Variables**: Store API keys in `.env` files or secure secret management
3. **Rotate Keys Regularly**: Change API keys periodically
4. **Use HTTPS**: In production, always use HTTPS to protect API keys in transit
5. **Limit Access**: Only grant API key access to trusted services

## Troubleshooting

### Invalid API Key Error

If you receive a `401 Unauthorized` error:

1. Check that `MEETING_NOTE_TAKER_API_KEY` is set in your `.env` file
2. Verify the API key matches in both the backend service and your client
3. Restart the backend service after setting the API key
4. Check the backend logs for authentication errors

### Connection Errors

If you cannot connect to the API:

1. Verify the backend service is running: `docker-compose ps`
2. Check the service logs: `docker-compose logs backend`
3. Verify the port is correct (default: 8001)
4. Check firewall/network settings

## Support

For issues or questions, check the backend logs:
```bash
docker-compose logs backend
```

