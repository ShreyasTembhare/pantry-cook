# Pantry Cook

A single-user web app for tracking a home pantry and turning a plain sentence into a structured, quantity-aware meal proposal. Built with FastAPI, LangGraph, Next.js, and shadcn/ui.

The home page is the pantry: items grouped by urgency, with quick-add, inline edit, and delete.

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
make test          # run backend and frontend tests
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

A blank sentence (`{"sentence":""}`) cooks what's expiring: the proposal prefers the three items that expire soonest. An empty pantry still returns `409 empty_pantry`.

The start call returns a proposal and a `proposal_etag`. Confirm with that etag and the pantry quantity drops:

```bash
curl -s -X POST localhost:8787/api/cook/<thread_id>/confirm \
  -H 'content-type: application/json' \
  -d '{"proposal_etag":"<etag from the start response>"}'
```

Revise with `POST /api/cook/<thread_id>/revise` and `{"note":"fewer steps"}`. Abandon with `POST /api/cook/<thread_id>/abandon`. Cooked meals are `GET /api/meals` and `GET /api/meals/<id>`.

`POST /api/meals/<id>/undo` puts the quantities that meal subtracted back into the pantry in one transaction and marks the meal `undone`. Calling it again returns the undone meal and does not add those quantities a second time.

`POST /api/meals/<id>/lines/<line_id>/bought` marks one missing line as bought. It creates the pantry item, or adds onto the item with the same name when the unit is the same dimension (`g`/`kg`, `ml`/`L`, or `count`). The line then leaves the shopping list. A line that already has a measure (`200 g` in the note, or a stored quantity) can be bought with `{}`. A line with no quantity returns `422 quantity_required` until the body includes `quantity` and `unit`. A different dimension returns `422 unit_dimension_mismatch` and the line stays. On the meal page, each shopping line has an “I bought this” button. When the line has no quantity, the page asks for one before adding it to the pantry.

**Print list** on the meal page opens `/meals/<id>/list`, one page of the missing lines. Print uses the browser dialog; the print stylesheet hides the rail, header, and tab bar. Copy puts the same lines on the clipboard as plain text, and Download .txt / Download .md save that list.

The cook graph pauses on a SqliteSaver checkpoint, so stopping the server after a proposal and starting it again still accepts confirm on the same thread id.

### Hardening

On startup the server marks a `running` cook with no user interrupt, older than 10 minutes, as `failed` (`interrupted_by_restart`). A checkpoint the library can no longer read becomes `checkpoint_unreadable` instead of a 500. Once an hour, proposals still `awaiting_user` past `expires_at` (24 hours from the start) are abandoned, and checkpoints for abandoned, committed, or failed sessions older than 7 days are deleted. Set `PANTRY_MAINTENANCE=0` to skip both.

Confirming a proposal that uses an expired item returns `409 expired_unacknowledged` until the body includes `"acknowledge_expired": true`. The proposal footer shows a checkbox such as “I know the yoghurt expired Monday” and keeps Confirm off until it is checked.

Adding a name that already exists returns `409 duplicate_item` with `extra.existing_id`. The pantry offers “Add … to it” when the unit is the same dimension (`POST /api/items/{id}/merge`) or “Rename” when it is not.

A provider timeout becomes `504 llm_timeout` (“The chef took too long.”). A 429 becomes `429 llm_rate_limited` with a `Retry-After` header when the provider sent one; the error card counts that down before Try again is enabled. Logs are structured (`structlog`): JSON when `PANTRY_ENV=production`, a console renderer otherwise. Each request logs `request_id`, method, path, status, and `duration_ms`. Cook nodes log `session_id`, `node`, `attempt`, `duration_ms`, and `llm_model`. `GET /api/health` also reports `checkpointer` and `pending_sessions`.

Backend coverage on `app/domain` and `app/graph` fails under 85%. Playwright: `frontend/e2e/persistence.spec.ts` (reload the awaiting proposal, then confirm) and `mobile.spec.ts` (390×844 add, revise, confirm).

### Look

The app opens on the pantry list. Neutrals are a warm sand scale, headings are Fraunces, and UI text is Geist, with tabular numerals on quantities. Expiry is the only semantic colour: amber for use soon, tomato for expired. There is no gradient, no hero, and no feature grid.

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
