# Contributing to Meeting Note Taker

Thanks for your interest in contributing! This guide covers what you need to get started.

## Prerequisites

- **Docker** and **Docker Compose** (for backend services)
- **Node.js 18+** and **npm** (for the React frontend)
- **Python 3.11+** (for the FastAPI backend, if running outside Docker)

## Development Setup

### Backend

```bash
# Start all backend services
docker compose up -d

# Or run FastAPI directly for local development
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server proxies API requests to the backend automatically.

## Code Style

### Python

We use **black** for formatting and **ruff** for linting.

```bash
black .
ruff check --fix .
```

### JavaScript / React

We use **prettier** for formatting.

```bash
npx prettier --write "src/**/*.{js,jsx,ts,tsx}"
```

Please run formatters before committing. If the project includes pre-commit hooks, install them with:

```bash
pre-commit install
```

## Making Changes

1. **Fork** the repository and clone your fork.
2. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-change
   ```
3. Make your changes with clear, focused commits.
4. Ensure tests pass:
   ```bash
   # Backend
   pytest

   # Frontend
   npm test
   ```
5. Push to your fork and open a **Pull Request** against `main`.

## Pull Request Guidelines

- Keep PRs small and focused on a single change.
- Include a brief description of what changed and why.
- Reference any related issues (e.g., "Closes #42").
- Make sure CI checks pass before requesting review.

## Reporting Bugs

Open an issue on [GitHub Issues](../../issues) with:

- Steps to reproduce
- Expected vs. actual behavior
- Environment details (OS, browser, Python/Node version)

## Questions?

If something is unclear, open a discussion or issue and we will be happy to help.
