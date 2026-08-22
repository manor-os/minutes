---
sidebar_position: 2
title: Storage (MinIO)
---

# Audio Storage

Minutes uses **MinIO** (S3-compatible object storage) to store audio recordings.

## Default Setup

MinIO starts automatically with Docker Compose. Default credentials:

- **Console**: http://localhost:9011
- **Username**: `minioadmin`
- **Password**: `minioadmin`

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_BACKEND` | `minio` | `minio` or `local` (filesystem) |
| `MINIO_ENDPOINT` | `minio:9000` | MinIO API endpoint (internal) |
| `MINIO_ACCESS_KEY` | `minioadmin` | Access key |
| `MINIO_SECRET_KEY` | `minioadmin` | Secret key |
| `MINIO_BUCKET` | `minutes-audio` | Bucket name |
| `MINIO_SECURE` | `false` | Use HTTPS |

## Production Recommendations

- Change default MinIO credentials
- Enable MinIO HTTPS in production
- Set up MinIO backup/replication for durability
- Or use any S3-compatible service (AWS S3, DigitalOcean Spaces, etc.) by pointing `MINIO_ENDPOINT` to the S3 endpoint
