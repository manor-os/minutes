---
sidebar_position: 1
title: Docker Deployment
---

# Docker Deployment

## Compose Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base stack (Postgres, Redis, MinIO, Backend, Celery, Frontend) |
| `docker-compose.local.yml` | Adds Ollama for fully local mode |
| `docker-compose.community.yml` | Sets `EDITION=community` |

## Production Checklist

- [ ] Change `JWT_SECRET` to a strong random value
- [ ] Change MinIO credentials from defaults
- [ ] Set up HTTPS (reverse proxy with nginx/Caddy)
- [ ] Set `DEBUG=False` (already default)
- [ ] Configure backups for PostgreSQL and MinIO

## Reverse Proxy (nginx)

```nginx
server {
    listen 80;
    server_name meetings.yourdomain.com;

    location /api/ {
        proxy_pass http://localhost:8002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 500M;
    }

    location / {
        proxy_pass http://localhost:9002;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Updating

```bash
./minutes update  # or: git pull && docker compose up -d --build
```
