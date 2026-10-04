.PHONY: dev dev-backend dev-frontend test test-backend lint lint-backend lint-frontend typecheck format install migrate

# ── Development ──────────────────────────────────────────────

dev: dev-backend dev-frontend

migrate:
	cd backend && uv run alembic upgrade head

dev-backend:
	cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8787 --reload

dev-frontend:
	cd frontend && pnpm dev

# ── Testing ──────────────────────────────────────────────────

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest -q --cov=app/domain --cov=app/graph --cov-report=term-missing --cov-fail-under=85

test-frontend:
	cd frontend && pnpm test

# ── Linting ──────────────────────────────────────────────────

lint: lint-backend lint-frontend

lint-backend:
	cd backend && uv run ruff check app tests
	cd backend && uv run ruff format --check app tests

lint-frontend:
	cd frontend && pnpm lint

typecheck:
	cd frontend && pnpm typecheck

# ── Formatting ───────────────────────────────────────────────

format:
	cd backend && uv run ruff format app tests
	cd backend && uv run ruff check --fix app tests

# ── Installation ────────────────────────────────────────────────

install:
	cd backend && uv sync --all-extras
	cd frontend && pnpm install
