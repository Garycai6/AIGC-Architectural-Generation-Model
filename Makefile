.PHONY: setup test lint run-frontend run-backend

setup:
	uv sync --extra dev
	cd frontend && npm install

test:
	uv run pytest -v

lint:
	uv run ruff check .
	uv run ruff format --check .

run-backend:
	uv run archgen-api

run-frontend:
	cd frontend && npm run dev
