# Self-hosting Minutes Community

Use the [README quick start](../README.md#self-host) for a local Docker installation. Compose v2.24+ is needed for the optional `.env` declaration in the base file. The stack includes the web app, API, worker, scheduler, PostgreSQL, Redis, and MinIO.

## Credentials and first use

Copy `.env.community.example` to `.env` and replace the JWT secret and admin password. Generate a JWT secret with `openssl rand -hex 32`. Choose your own admin email. On first startup, the app creates that account; changing `ADMIN_PASSWORD` later does not reset an existing account's password.

In API mode, configure transcription and language-model providers in **Settings**. A common setup is an OpenAI transcription key and an OpenRouter language-model key. Custom compatible endpoints are configurable. Use a model supported by your provider. Server fallback credentials can be supplied through `OPENAI_API_KEY` and `OPENROUTER_API_KEY`; these are shared deployment configuration, not free API access.

Do not put secrets in `VITE_*` variables: these are compiled into the browser bundle.

## Local AI

Add `docker-compose.local.yml` after the base and Community files, as shown in the README. Run `ollama pull qwen2.5:1.5b` in the Ollama container before requesting notes. The Compose overlay selects that model even though the Python fallback default has a different size.

The faster-whisper `base` model downloads on first transcription. Images and models need internet for initial setup. Inference can then run locally once required models are present. External API credentials, outbound webhooks, or enabled integrations can still send data outside your deployment; choose your settings accordingly.

The first job is slower while models initialize. CPU speed and available Docker memory affect processing time. The local Compose file gives Ollama a 6 GB memory limit and the worker a 4 GB limit; these are per-service ceilings, not a guarantee that the whole stack runs within 6 GB. Larger models can improve results at a cost in memory and latency.

## Ports and lifecycle

| Service | Default host port |
|---|---|
| Web app | 9002 |
| API | 8002 |
| PostgreSQL | 5432 |
| Redis | 6382 |
| MinIO API / console | 9012 / 9013 |
| Ollama, with local overlay | 11434 |

Run commands from the repository root and keep the same `-f` list used to start the stack. For API mode:

```bash
docker compose -f docker-compose.yml -f docker-compose.community.yml ps
docker compose -f docker-compose.yml -f docker-compose.community.yml logs --tail=100 backend celery-worker
docker compose -f docker-compose.yml -f docker-compose.community.yml down
```

For local mode, also include `-f docker-compose.local.yml`. `down` leaves named volumes in place; `down -v` deletes them. Database backups do not include recordings in MinIO. Back up both, and test restoration before updating an installation with important meetings.

## Before exposing a deployment

The supplied Compose stack is a development starting point. It publishes infrastructure ports and has default database/storage credentials. For a shared deployment, restrict those ports, configure unique credentials consistently, put the app/API behind HTTPS, configure allowed origins, and maintain backups. The default Compose file is not claimed to be production-hardened.

Set `VITE_API_URL` to an API address reachable from the user's browser and rebuild the frontend. A phone cannot reach your laptop's API using `localhost`. Recording on another device needs HTTPS; a plain HTTP LAN address is generally not a secure context.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Microphone unavailable | Browser permission and HTTPS/localhost; another device needs a reachable HTTPS URL. |
| Remote participants missing | Share a supported tab and enable audio. System capture varies by browser/OS. |
| Live words delayed | Live text arrives in chunks; check the websocket and transcription service. |
| Recording succeeds but notes fail | Worker, provider credentials/model, or whether the Ollama model was pulled. |
| First local recording is slow | Allow the Whisper download/model initialization to finish and check memory. |
| Port already in use | Stop the conflicting service or change the host port and frontend API URL. |
| Hosted feature missing | Check the README edition table; hosted Minutes can be ahead of public main. |

Inspect logs locally and remove credentials and personal content before sharing diagnostics.

## Speaker labels

The source includes an optional pyannote diarization path. The dependency is commented out in `backend/requirements.txt` and requires a compatible installation, model access, and `HF_TOKEN`. The default Compose setup does not guarantee speaker separation. Labels such as “Speaker 1” do not verify identities.
