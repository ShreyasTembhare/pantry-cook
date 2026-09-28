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

Copy `.env.example` to `.env` and adjust as needed. The app runs in offline/demo mode by default (`LLM_PROVIDER=fake`).

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
