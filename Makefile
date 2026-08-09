.PHONY: setup test lint run-frontend run-backend data-synth data-clean data-validate

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

data-synth:
	uv run python -m data.synth --out data/datasets/synth_demo --per-style 50 --seed 42

data-clean:
	uv run python -m data.clean --dir data/datasets/synth_demo

data-validate:
	uv run python -m data.validate --dir data/datasets/synth_demo
