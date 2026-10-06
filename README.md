# Pantry Cook

A single-user kitchen app. Chat is the home page: tell Pip what is in the fridge, ask for a meal, or change a recipe. Pantry, cook, and meals stay first-class screens beside that conversation.

## Stack

Python 3.12, FastAPI, SQLAlchemy, Alembic, LangGraph, LangChain (OpenAI-compatible clients), Postgres, Next.js 16, Tailwind 4, and shadcn/ui. One Postgres database holds pantry tables and LangGraph cook checkpoints. Schema changes ship through Alembic.

There is **no vector database or RAG**. The LLM sees a **fresh JSON snapshot** of pantry, meals, and recent chat built from SQL queries each time it is called.

## Prerequisites

- PostgreSQL 16+ (running before you start the app)
- Python 3.12+
- Node.js 22+
- [uv](https://docs.astral.sh/uv/)
- [pnpm](https://pnpm.io/)
- **Git Bash** on Windows (for `./dev.sh`), or run the Makefile targets manually

## Quick start

1. **Postgres** — create role and database once (adjust to match `.env`):

```sql
CREATE USER pantry WITH PASSWORD 'pantry';
CREATE DATABASE pantry OWNER pantry;
GRANT ALL PRIVILEGES ON DATABASE pantry TO pantry;
```

2. **Env and dependencies**

```bash
cp .env.example .env
make install
```

Set `OPENAI_API_KEY` and `PANTRY_LLM_PROVIDER=real` when you want a hosted chef. Leave `fake` (default) for offline development and tests.

3. **Run everything**

```bash
./dev.sh
```

On Windows PowerShell from the repo root: `.\dev.ps1` (wraps Git Bash).

`dev.sh` waits for Postgres, runs migrations, starts the API on **8787** and the app on **3939**, then prints URLs. **Postgres must already be running** (Windows service, local cluster, or remote host). Ctrl+C stops the API and frontend only.

Or run separately: `make migrate`, `make dev-backend`, and `make dev-frontend` in another terminal.

| URL | Purpose |
| --- | --- |
| http://localhost:3939 | Web app |
| http://127.0.0.1:8787/docs | **Swagger UI** — try API routes |
| http://127.0.0.1:8787/redoc | ReDoc |
| http://127.0.0.1:8787/api/health | Health check |

Point `PANTRY_DATABASE_URL` at your instance. Default in `.env.example` is `127.0.0.1:5432`. If you use a **separate local data directory** on another port (for example **5433**), match that port in `.env`.

## Environment

Copy `.env.example` to `.env` in the repo root. Names match `Settings` in `backend/app/config.py`.

| Variable | Purpose |
| --- | --- |
| `PANTRY_DATABASE_URL` | SQLAlchemy URL, e.g. `postgresql+psycopg://pantry:pantry@127.0.0.1:5432/pantry`. |
| `PANTRY_LLM_PROVIDER` | `fake` stays offline. Any other value uses a hosted model when a provider key is set. |
| `PANTRY_LLM_MODEL` | Model id, default `openai:gpt-4o-mini`. |
| `PANTRY_LLM_BASE_URL` | OpenAI-compatible base URL (e.g. NVIDIA Integrate). |
| `PANTRY_LLM_TIMEOUT` | Seconds before a model call gives up. Default 30. |
| `PANTRY_LLM_MAX_TOKENS` | Optional output cap. `0` leaves the provider default. |
| `PANTRY_LLM_MAX_RETRIES` | Provider retries. Default 2. |
| `PANTRY_LLM_TEMPERATURE` | Sampling temperature for hosted models. Default 0. |
| `PANTRY_LLM_TOP_P` | Optional nucleus sampling. |
| `PANTRY_LLM_THINKING` | `1` sends `chat_template_kwargs.enable_thinking` (NVIDIA and similar hosts). |
| `PANTRY_CHAT_MODEL` | Optional model for home chat. Empty uses `PANTRY_LLM_MODEL`. |
| `PANTRY_CHAT_REASONING_EFFORT` | Optional `low`, `medium`, or `high` for reasoning models. Empty keeps the default. |
| `PANTRY_CHAT_PLANNER_TIMEOUT` | Seconds the chat planner waits for the model before using the rules reply. Default 40. |
| `OPENAI_API_KEY` | Read by the provider client (`nvapi-…` for NVIDIA). Leave empty for offline mode. |
| `PANTRY_ENV` | `production` writes JSON logs. Anything else uses a console renderer. |
| `PANTRY_MAINTENANCE` | `1` reconciles cook sessions on startup and sweeps abandoned proposals. `0`, `false`, `off`, or `no` skips that. |
| `PANTRY_CORS_ORIGINS` | JSON list of allowed browser origins. Default is the Next.js dev origins. |
| `NEXT_PUBLIC_API_URL` | API origin the frontend calls. Default `http://localhost:8787`. |

`PANTRY_LLM_PROVIDER=fake` keeps cook proposals, sentence parsing, and chat offline.

### How chat uses the model

Chat is hybrid. Known commands such as "2 leeks", "remove the leeks", "what's in the pantry", and "something warm" are read by rules and never leave the machine. Anything the rules cannot read goes to the chat model with a bounded `CONTEXT_JSON` snapshot: pantry items (quantity, unit, expiry), recent meals, the open cook session, any open confirmation, and recent messages. The model returns a short reply and at most one action. The app validates that plan and runs it through the same pantry, cook, and meal services as every other route.

Removing an item, cooking a proposal, and undoing a meal always wait for a yes or no. While one is open, other changes are held until it is answered. If the model times out, answers badly, or asks for something that cannot run, nothing is written and Pip falls back to a rules reply.

### How cook uses the model

Cook runs a **LangGraph** workflow: load pantry → parse constraints (LLM) → propose meal (LLM) → **validate in code** → await confirm/revise → commit to DB. Checkpoints live in Postgres so sessions can resume.

## Backend layout

| Path | Role |
| --- | --- |
| `backend/app/api/` | FastAPI routes (HTTP only) |
| `backend/app/services/` | Use cases: pantry, cook, meals, chat |
| `backend/app/domain/` | Business rules, planner, units, commit logic |
| `backend/app/schemas/` | Pydantic request/response and LLM shapes |
| `backend/app/db/` | SQLAlchemy models and repositories |
| `backend/app/graph/` | LangGraph cook graph, LLM helpers, prompts |
| `backend/alembic/` | Database migrations |
| `backend/tests/` | pytest (unit, API, graph) |

## API

Meals are created only when a cook proposal is confirmed. The app has one home chat thread. There is no meal create or delete route, and no extra chat threads.

| Area | Routes |
| --- | --- |
| Items | `GET` and `POST /api/items`, `GET`, `PATCH`, and `DELETE /api/items/{id}`, `POST /api/items/{id}/merge` |
| Sentence add | `POST /api/items/sentence/preview`, `POST /api/items/sentence` |
| Cook | `POST /api/cook/start`, `GET /api/cook`, `GET /api/cook/{id}`, `POST .../revise`, `POST .../confirm`, `POST .../abandon`, `GET .../stream` |
| Meals | `GET /api/meals`, `GET /api/meals/{id}`, `POST .../undo`, `POST .../lines/{line_id}/bought` |
| Chat | `GET /api/chat`, `POST /api/chat/messages`, `POST /api/chat/pending/{id}/confirm`, `POST .../cancel` |
| Health | `GET /api/health` |

Request and response schemas are on `/docs`. Errors use `application/problem+json`.

### Trying routes in Swagger

Open `/docs`, expand a route, click **Try it out**, edit the JSON body, and **Execute**. Start with `GET /api/health`, then `GET /api/items`, `POST /api/chat/messages` with `{"text":"What's in the pantry?"}`, and `POST /api/cook/start` with a sentence (may take a while when using a real model).

## Tests

```bash
make test
```

Backend tests expect Postgres reachable at `PANTRY_DATABASE_URL` and set `PANTRY_LLM_PROVIDER=fake` automatically. Coverage on `app/domain` and `app/graph` fails under 85% when below threshold.

Frontend: `cd frontend && pnpm test` (Vitest). E2E: `pnpm test:e2e` (Playwright).
