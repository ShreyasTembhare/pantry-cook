.PHONY: dev dev-backend dev-frontend test test-backend lint lint-backend lint-frontend typecheck format install

dev: dev-backend dev-frontend

dev-backend:
	cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8787 --reload

dev-frontend:
	cd frontend && pnpm dev

test: test-backend

test-backend:
	cd backend && uv run pytest -q

lint: lint-backend lint-frontend

lint-backend:
	cd backend && uv run ruff check app tests
	cd backend && uv run ruff format --check app tests

lint-frontend:
	cd frontend && pnpm lint

typecheck:
	cd frontend && pnpm typecheck

format:
	cd backend && uv run ruff format app tests
	cd backend && uv run ruff check --fix app tests

install:
	cd backend && uv sync --all-extras
	cd frontend && pnpm install
