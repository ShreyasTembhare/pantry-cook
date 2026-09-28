# Pantry Cook

A single-user web app for tracking a home pantry and turning a plain sentence into a structured, quantity-aware meal proposal. Built with FastAPI, LangGraph, Next.js, and shadcn/ui.

## Tech Stack

**Backend** — Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, LangChain, LangGraph, SQLite

**Frontend** — Next.js 15 (App Router), TypeScript, Tailwind CSS v4, shadcn/ui, Lucide icons

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 22+
- [uv](https://docs.astral.sh/uv/) for Python dependency management
- [pnpm](https://pnpm.io/) for frontend dependency management

### Install

```bash
# Backend
cd backend && uv sync --all-extras

# Frontend
cd frontend && pnpm install
```

### Run

```bash
# Backend (port 8787)
cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8787 --reload

# Frontend (port 3939)
cd frontend && pnpm dev
```

Or use the Makefile:

```bash
make install       # install all dependencies
make dev-backend   # start backend on :8787
make dev-frontend  # start frontend on :3939
make test          # run all tests
make lint          # lint both projects
```

### Environment

Copy `.env.example` to `.env` and adjust as needed. The app runs in offline/demo mode by default (`PANTRY_LLM_PROVIDER=fake`). No API key is required.

### Cook a meal

With the backend on port 8787 and a couple of pantry items:

```bash
curl -s -X POST localhost:8787/api/items \
  -H 'content-type: application/json' \
  -d '{"name":"Leeks","quantity":"300","unit":"g"}'

curl -s -X POST localhost:8787/api/cook/start \
  -H 'content-type: application/json' \
  -d '{"sentence":"something warm with the leeks"}'
```

The start call returns a proposal and a `proposal_etag`. Confirm with that etag and the pantry quantity drops:

```bash
curl -s -X POST localhost:8787/api/cook/<thread_id>/confirm \
  -H 'content-type: application/json' \
  -d '{"proposal_etag":"<etag from the start response>"}'
```

Revise with `POST /api/cook/<thread_id>/revise` and `{"note":"fewer steps"}`. Abandon with `POST /api/cook/<thread_id>/abandon`. Cooked meals are `GET /api/meals` and `GET /api/meals/<id>`.

The cook graph pauses on a SqliteSaver checkpoint, so stopping the server after a proposal and starting it again still accepts confirm on the same thread id.

## Project Structure

```
pantry-cook/
├── backend/           # FastAPI + SQLAlchemy + LangGraph
│   ├── app/
│   │   ├── api/       # route handlers
│   │   ├── db/        # engine, ORM models, repositories
│   │   ├── domain/    # units, errors, business logic
│   │   ├── schemas/   # Pydantic request/response models
│   │   └── graph/     # LangGraph cook flow
│   └── tests/
├── frontend/          # Next.js + Tailwind + shadcn/ui
│   ├── app/           # App Router pages
│   ├── components/    # UI components
│   └── lib/           # utilities
├── Makefile
└── .env.example
```
