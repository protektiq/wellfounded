COMPOSE := docker-compose -f infra/local/docker-compose.yml

.PHONY: up down db-migrate db-revision api web test lint ingest eval-run eval-view

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

db-migrate:
	cd apps/api && poetry run alembic upgrade head

db-revision:
	cd apps/api && poetry run alembic revision -m "$(msg)"

ingest:
	cd apps/api && poetry run python -m scripts.ingest $(ARGS)

api:
	cd apps/api && poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000

web:
	cd apps/web && npm run dev

test:
	cd apps/api && poetry run pytest
	cd apps/web && npm test

lint:
	cd apps/api && poetry run ruff check .
	cd apps/api && poetry run mypy --strict .

eval-run:
	cd apps/api && poetry run python -m evals.runner --category $(category)

eval-view:
	cd apps/api && poetry run python -m evals.view $(a) $(b)
