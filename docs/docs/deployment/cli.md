---
sidebar_position: 2
title: CLI Reference
---

# Minutes CLI

The `./minutes` script in the project root provides management commands.

## Commands

| Command | Description |
|---------|-------------|
| `./minutes start` | Start all services |
| `./minutes stop` | Stop all services |
| `./minutes restart` | Restart services |
| `./minutes status` | Show container status |
| `./minutes logs` | Tail all logs |
| `./minutes logs backend` | Tail specific service logs |
| `./minutes health` | Check Backend, Frontend, DB, Redis, MinIO |
| `./minutes update` | `git pull` + rebuild + restart |
| `./minutes backup` | Dump PostgreSQL + copy .env to `backups/` |
| `./minutes migrate` | Run database migrations |
| `./minutes shell` | Bash into backend container |
| `./minutes db` | Open psql console |
| `./minutes config` | Edit `.env` in your editor |

## Auto-Detection

The CLI auto-detects which Docker Compose overlays to use based on your `.env`:

- `STT_MODE=local` → includes `docker-compose.local.yml`
- `EDITION=cloud` → includes `docker-compose.cloud.yml`
