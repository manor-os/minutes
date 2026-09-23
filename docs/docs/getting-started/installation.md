---
sidebar_position: 1
title: Installation
---

# Installation

## One-Command Setup

```bash
npx create-manor-minutes
```

The installer will:
1. Check that Docker and Git are installed
2. Ask you to choose a mode (Local, Cloud API, or Custom)
3. Clone the repository
4. Generate a `.env` file with a secure JWT secret
5. Start all services with Docker Compose

Open **http://localhost:9002** when it's done.

## Manual Docker Setup

```bash
git clone https://github.com/manor-os/minutes.git
cd minutes

# Cloud API mode (configure keys in Settings after login)
docker compose up -d

# Or fully local mode (no API keys needed)
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

## Prerequisites

- **Docker Desktop** (includes Docker Compose)
- **Git**
- **6GB+ RAM** for local mode (Ollama + faster-whisper)
- **2GB RAM** for cloud API mode

## Services Started

| Service | Port | Description |
|---------|------|-------------|
| Frontend | [localhost:9002](http://localhost:9002) | React PWA |
| Backend API | [localhost:8002](http://localhost:8002) | FastAPI |
| PostgreSQL | 5432 | Database |
| Redis | 6382 | Task queue |
| MinIO | [localhost:9011](http://localhost:9011) | Audio storage (admin: minioadmin/minioadmin) |
| Ollama | 11434 | Local LLM (local mode only) |

## First Steps

1. Open http://localhost:9002
2. Register an account
3. Go to **Settings** and configure your API keys (cloud mode) or verify local models are running
4. Start recording!
