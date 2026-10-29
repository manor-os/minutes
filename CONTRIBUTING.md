# Contributing to Minutes

Start with the [Community setup](docs/SELF_HOSTING.md). This repository is the public Community edition; the hosted service can have features that have not been released here.

## Development

Use Docker Compose for PostgreSQL, Redis, MinIO, the API, and workers. Follow the README to prepare `.env`, then:

```bash
docker compose -f docker-compose.yml -f docker-compose.community.yml up -d --build
```

The backend source is bind-mounted into the containers. The API runs with reload enabled; restart Celery after changing worker code:

```bash
docker compose -f docker-compose.yml -f docker-compose.community.yml restart celery-worker
```

For frontend development, use Node.js 22.12+ and npm:

```bash
cd phone-recorder
npm ci
VITE_EDITION=community VITE_API_URL=http://localhost:8002 npm run dev
```

Open **http://localhost:3001**. The frontend calls the configured API URL directly; Vite does not configure an API proxy. The Docker frontend remains available on port 9002.

To work on Python outside Docker, use Python 3.11, install `backend/requirements.txt` in a virtual environment, and configure local service URLs. The hostnames in Compose resolve inside containers and cannot be copied unchanged into a host process. The API module is `api.main:app`, run from `backend/`.

## Validation

Run checks relevant to your changes and report what you actually ran in the pull request.

Frontend production build:

```bash
cd phone-recorder
VITE_EDITION=community npm run build
```

There are browser regression scripts rather than an `npm test` command. They need a built frontend and a Chrome/Chromium executable. The meeting-detail script includes cloud UI fixtures, so use the cloud fixture build for the full existing suite:

```bash
VITE_EDITION=cloud VITE_API_URL=http://127.0.0.1:9002 npm run build
CHROMIUM_PATH=/path/to/chrome npm run test:e2e
CHROMIUM_PATH=/path/to/chrome npm run test:ai-config
```

These tests simulate API/device responses; they do not prove a real provider call or physical mobile-device compatibility. Restore a Community build before inspecting Community behavior.

For focused Python checks from the repository root, in a Python 3.11 virtual environment:

```bash
python -m pip install -r backend/requirements.txt pytest
python -m pytest backend/tests/test_llm_parsing.py backend/tests/test_transcript_cleaning.py
```

Read the requirements of additional tests. Some existing tests target hosted modules or Compose files excluded from the public export. Report a full-suite collection failure for a missing cloud file rather than treating it as a passing Community suite.

## Pull requests

1. Fork the repository and branch from `main`.
2. Keep the change focused and follow the surrounding code style.
3. Explain the resulting behavior, relevant validation, and limitations.
4. Include before/after screenshots for UI changes, using fictional data.
5. Open a pull request against `main`.

Do not include credentials, private recordings, customer transcripts, or personal account data in code, screenshots, logs, or fixtures.

## Bugs and ideas

Use [Issues](https://github.com/manor-os/minutes/issues) for reproducible bugs and feature proposals. Include the edition, commit, browser, operating system, AI mode, and smallest useful reproduction. Remove secrets and personal data from diagnostics.
