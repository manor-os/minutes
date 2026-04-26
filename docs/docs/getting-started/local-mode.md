---
sidebar_position: 2
title: Local Mode
---

# Local Mode (No API Keys)

Run Minutes completely offline — no data leaves your machine.

## Start

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

## What Runs Locally

| Component | Model | Purpose |
|-----------|-------|---------|
| **faster-whisper** | `base` (default) | Speech-to-text transcription |
| **Ollama** | `qwen2.5:3b` | Summarization, key points, action items, AI chat |

## Requirements

- **6GB+ RAM** — Ollama needs ~4GB, faster-whisper needs ~1GB
- **CPU** — Works on CPU, GPU accelerates Ollama significantly

## First Run

Ollama needs to download the model on first use (~2GB). This happens automatically when the first meeting is processed.

To pre-download:

```bash
docker compose exec ollama ollama pull qwen2.5:3b
```

## Changing Models

### Larger Whisper Model (better accuracy)

Edit `docker-compose.local.yml`:

```yaml
backend:
  environment:
    - WHISPER_MODEL_SIZE=medium  # base, small, medium, large-v3
```

### Different Ollama Model

```yaml
backend:
  environment:
    - OLLAMA_MODEL=llama3.1:8b  # any Ollama model
```

## Limitations

- Slower than cloud APIs (especially on CPU)
- `base` Whisper model is less accurate than OpenAI's hosted Whisper
- Ollama 3B models produce simpler summaries than GPT-4
- No speaker diarization via pyannote (requires separate setup)
