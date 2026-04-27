---
sidebar_position: 3
title: Cloud API Mode
---

# Cloud API Mode

Use OpenAI Whisper for transcription and OpenRouter/OpenAI for summarization. Better accuracy, requires API keys.

## Start

```bash
docker compose up -d
```

## Configure API Keys

API keys are set **per-user in Settings**, not in server config.

1. Open http://localhost:9002
2. Register / login
3. Click your profile → **Settings**
4. Enter your API keys:
   - **STT API Key** — OpenAI key (`sk-...`) for Whisper transcription
   - **LLM API Key** — OpenRouter (`sk-or-...`) or OpenAI key for summarization

## Supported Providers

### Speech-to-Text
| Provider | Key Format | Model |
|----------|-----------|-------|
| OpenAI | `sk-...` | whisper-1 |

### Summarization
| Provider | Key Format | Models |
|----------|-----------|--------|
| OpenRouter | `sk-or-...` | Claude, GPT-4, Llama, etc. |
| OpenAI | `sk-...` | GPT-4o, GPT-4o-mini |

Minutes auto-detects the provider from the key format:
- `sk-or-...` → OpenRouter (`openrouter.ai/api`)
- `sk-...` → OpenAI (`api.openai.com`)

## Cost Estimate

| Component | Cost |
|-----------|------|
| Whisper | ~$0.006/min of audio |
| Summarization (GPT-4o-mini) | ~$0.001 per meeting |
| **Total** | ~$0.01 per 10-min meeting |
