# Pantry Cook

A single-user kitchen app. Chat is the home page: tell Pip what is in the fridge, ask for a meal, or change a recipe. Pantry, cook, and meals stay first-class screens beside that conversation.

## Stack

Python 3.12, FastAPI, SQLAlchemy, Alembic, LangGraph, Postgres, Next.js 16, Tailwind 4, and shadcn/ui. One Postgres database holds the pantry tables and the LangGraph cook checkpoints. Schema comes from Alembic.

## Prerequisites

- Docker
- Python 3.12+
- Node.js 22+
- [uv](https://docs.astral.sh/uv/)
- [pnpm](https://pnpm.io/)

## Setup

```bash
cp .env.example .env
docker compose up -d
make install
make migrate
make dev-backend
make dev-frontend
```

The API listens on port 8787 and the app on port 3939. `make dev-backend` applies migrations before it starts. OpenAPI schemas are at [http://localhost:8787/docs](http://localhost:8787/docs).

If port 5432 is already in use, point `PANTRY_DATABASE_URL` at the Postgres you want to use.

## Environment

Copy `.env.example` to `.env` in the repo root. Names match `Settings` in `backend/app/config.py`.

| Variable | Purpose |
| --- | --- |
| `PANTRY_DATABASE_URL` | SQLAlchemy URL. Default `postgresql+psycopg://pantry:pantry@localhost:5432/pantry`. |
| `PANTRY_LLM_PROVIDER` | `fake` stays offline. Any other value uses a hosted model when a provider key is set. |
| `PANTRY_LLM_MODEL` | Model id, default `openai:gpt-4o-mini`. |
| `PANTRY_LLM_BASE_URL` | Optional OpenAI-compatible base URL. |
| `PANTRY_LLM_TIMEOUT` | Seconds before a model call gives up. Default 30. |
| `PANTRY_LLM_MAX_TOKENS` | Optional output cap. `0` leaves the provider default. |
| `PANTRY_LLM_MAX_RETRIES` | Provider retries. Default 2. |
| `PANTRY_CHAT_MODEL` | Optional faster model for home chat, for example `openai:openai/gpt-oss-20b`. Empty uses `PANTRY_LLM_MODEL`. |
| `PANTRY_CHAT_REASONING_EFFORT` | Optional `low`, `medium`, or `high` for reasoning models used in chat. Empty keeps the default. |
| `PANTRY_CHAT_PLANNER_TIMEOUT` | Seconds the chat planner waits for the model before using the rules reply. Default 40. |
| `OPENAI_API_KEY` | Read by the provider client. Leave empty for offline mode. |
| `ANTHROPIC_API_KEY` | Optional. Commented in `.env.example`. |
| `GOOGLE_API_KEY` | Optional. Commented in `.env.example`. |
| `PANTRY_ENV` | `production` writes JSON logs. Anything else uses a console renderer. |
| `PANTRY_MAINTENANCE` | `1` reconciles cook sessions on startup and sweeps abandoned proposals. `0`, `false`, `off`, or `no` skips that. |
| `PANTRY_CORS_ORIGINS` | JSON list of allowed browser origins. Default is the Next.js dev origins. |
| `NEXT_PUBLIC_API_URL` | API origin the frontend calls. Default `http://localhost:8787`. |

`PANTRY_LLM_PROVIDER=fake` keeps cook proposals, sentence parsing, and chat offline.

### How chat uses the model

Chat is hybrid. Known commands such as "2 leeks", "remove the leeks", "what's in the pantry", and "something warm" are read by rules and never leave the machine. Anything the rules cannot read goes to the chat model with a bounded snapshot: each pantry item's quantity, unit, and expiry (with an `expired` flag), the last few cooked meals, the open meal, any open confirmation, and the last few messages. The model returns a short reply and at most one action. The app checks that action and runs it through the same pantry, cook, and meal services as every other route.

Removing an item, cooking a proposal, and undoing a meal always wait for a yes or no. While one is open, other changes are held until it is answered, and cook changes replace it. If the model times out, answers badly, or asks for something that cannot run, nothing is written and Pip replies with a short rules message.

Reasoning models can be slow on shared endpoints. Keep `PANTRY_LLM_MODEL` for cook proposals and set `PANTRY_CHAT_MODEL` to something quick for chat.

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

## Tests

```bash
make test
```

Backend coverage on `app/domain` and `app/graph` fails under 85%.
