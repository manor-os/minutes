---
sidebar_position: 7
title: Contributing
---

# Contributing

See [CONTRIBUTING.md](https://github.com/manor-os/minutes/blob/main/CONTRIBUTING.md) for full guidelines.

## Quick Dev Setup

```bash
git clone https://github.com/manor-os/minutes.git
cd minutes
docker compose up -d

# Frontend hot-reload at localhost:9002
# Backend auto-reload at localhost:8002
```

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React 18 + Vite |
| Backend | FastAPI (Python 3.11) |
| Database | PostgreSQL 15 |
| Queue | Celery + Redis |
| Storage | MinIO |
| STT | OpenAI Whisper / faster-whisper |
| LLM | OpenRouter / OpenAI / Ollama |
