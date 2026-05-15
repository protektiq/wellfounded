COMPOSE := docker-compose -f infra/local/docker-compose.yml

.PHONY: up down db-migrate db-revision api web test test-e2e lint ingest ingest-all refresh-living-sources benchmark-retrieval eval-run eval-view eval-collect-baseline

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

# Sequential full-catalog ingestion (State Dept and country pages first, then PDFs).
# Order reduces bursty embedding traffic; each line is one subprocess with its own DB session.
ingest-all:
	$(MAKE) ingest ARGS="--source state_dept"
	$(MAKE) ingest ARGS="--source hrw"
	$(MAKE) ingest ARGS="--source amnesty"
	$(MAKE) ingest ARGS="--source freedom_house"
	$(MAKE) ingest ARGS="--source cpj"
	$(MAKE) ingest ARGS="--source uscirf"
	$(MAKE) ingest ARGS="--source unhcr"
	$(MAKE) ingest ARGS="--source euaa_coi"

refresh-living-sources:
	cd apps/api && poetry run python -m scripts.refresh_living_sources

benchmark-retrieval:
	cd apps/api && poetry run python -m scripts.benchmark_retrieval $(ARGS)

api:
	cd apps/api && poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000

web:
	cd apps/web && npm run dev

test:
	cd apps/api && poetry run pytest
	cd apps/web && npm test

test-e2e:
	cd apps/web && npx playwright install chromium && npm run test:e2e
lint:
	cd apps/api && poetry run ruff check .
	cd apps/api && poetry run mypy --strict .

eval-run:
	cd apps/api && poetry run python -m evals.runner --category $(category)

eval-view:
	cd apps/api && poetry run python -m evals.view $(a) $(b)

# Refresh the committed live baseline by running the model against live fixtures.
# Requires: make up && make db-migrate && ANTHROPIC_API_KEY set in environment.
# After running, commit evals/results/baseline-live-claude-opus-4-7.json.
eval-collect-baseline:
	cd apps/api && poetry run python -m evals.runner \
	  --category citation_faithfulness_live \
	  --output ../../evals/results/baseline-live-claude-opus-4-7.json
