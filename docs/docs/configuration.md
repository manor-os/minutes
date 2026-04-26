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
| `VITE_GOOGLE_CLIENT_ID` | (empty) | Google OAuth client ID |
| `FRONTEND_PORT` | `9002` | Frontend port mapping |

### Local Mode Only

| Variable | Default | Description |
|----------|---------|-------------|
| `STT_MODE` | `cloud` | `local` for faster-whisper |
| `LLM_MODE` | `cloud` | `local` for Ollama |
| `WHISPER_MODEL_SIZE` | `base` | faster-whisper model: base, small, medium, large-v3 |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Ollama model name |
