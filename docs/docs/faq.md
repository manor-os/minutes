---
sidebar_position: 8
title: FAQ
---

# FAQ

### Do I need API keys?

No — **Local mode** runs everything on your machine with no API keys. If you want better accuracy, you can use OpenAI/OpenRouter keys (set per-user in Settings).

### How much does it cost?

- **Local mode**: Free (your hardware)
- **Cloud API**: ~$0.01 per 10-minute meeting (Whisper + GPT-4o-mini)

### Is my data private?

Yes. Minutes is self-hosted — your audio and transcripts stay on your server. No data is sent to third parties unless you configure cloud API keys.

### Can I use my own LLM?

Yes. In local mode, change the Ollama model in `docker-compose.local.yml`. For cloud, any OpenAI-compatible API works via the key settings.

### How accurate is the transcription?

- **Cloud (Whisper API)**: Very accurate, supports 90+ languages
- **Local (faster-whisper base)**: Good for clear audio, less accurate for noisy environments. Use `medium` or `large-v3` model for better results.

### Can multiple people use the same instance?

Yes. Each user registers their own account with their own API keys and meeting library. Meetings are isolated per user.

### How do I upgrade?

```bash
./minutes update
```

### Where are audio files stored?

In MinIO (S3-compatible storage). Access the MinIO console at http://localhost:9011 (default: minioadmin/minioadmin).
