---
sidebar_position: 4
title: Configuration
---

# Configuration

## User Settings (in-app)

Most configuration is done per-user in **Settings** (click your profile → Settings):

| Setting | Description |
|---------|-------------|
| STT API Key | OpenAI key for Whisper transcription |
| LLM API Key | OpenRouter or OpenAI key for summarization |
| Transcription Language | Default language for transcription |
| Webhook URL | Slack/Discord notification URL |

## Environment Variables

Server-level configuration via `.env` or Docker Compose:

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | `change-me-in-production` | Secret for JWT token signing |
| `DATABASE_URL` | `postgresql://...` | PostgreSQL connection string |
| `STORAGE_BACKEND` | `minio` | `minio` or `local` |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `VITE_API_URL` | `http://localhost:8002` | Backend API URL for frontend |
| `FRONTEND_PORT` | `9002` | Frontend port mapping |

### Cloud Edition Only

| Variable | Default | Description |
|----------|---------|-------------|
| `EDITION` | `community` | Set to `cloud` to enable cloud-only features |
| `MANOR_OAUTH_CLIENT_ID` | `minutes-cloud` | Manor OAuth client ID |
| `MANOR_OAUTH_CLIENT_SECRET` | (empty) | Manor OAuth client secret, backend only |
| `MANOR_OAUTH_AUTHORIZE_URL` | `https://app.manorai.xyz/oauth/authorize` | Manor authorization endpoint |
| `MANOR_OAUTH_TOKEN_URL` | `https://app.manorai.xyz/api/v1/oauth/token` | Manor token exchange endpoint |
| `MANOR_OAUTH_REDIRECT_URI` | `https://minutes.manorai.xyz/auth/manor-callback` | Callback URL registered in Manor |
| `VITE_GOOGLE_CLIENT_ID` | (empty) | Google OAuth client ID for the cloud login page |
| `VITE_GOOGLE_REDIRECT_URI` | current origin + `/googleCallback` | Google OAuth redirect URI |
| `MANOR_GOOGLE_OAUTH_URL` | `https://app.manorai.xyz/api/v1/auth/oauth/google` | Manor API endpoint used to exchange Google auth codes |
| `MANOR_GOOGLE_PROFILE_URL` | `https://app.manorai.xyz/api/v1/auth/me` | Manor API endpoint used to read the logged-in user's profile |

### Local Mode Only

| Variable | Default | Description |
|----------|---------|-------------|
| `STT_MODE` | `cloud` | `local` for faster-whisper |
| `LLM_MODE` | `cloud` | `local` for Ollama |
| `WHISPER_MODEL_SIZE` | `base` | faster-whisper model: base, small, medium, large-v3 |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Ollama model name |
