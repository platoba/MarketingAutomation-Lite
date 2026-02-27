.PHONY: dev test lint fmt up down logs migrate

dev:
	uvicorn app.main:app --reload --port 8000

test:
	pytest -v --cov=app --cov-report=term-missing

lint:
	ruff check app/ tests/

fmt:
	ruff format app/ tests/

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	alembic upgrade head

worker:
	celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4

beat:
	celery -A app.tasks.celery_app beat --loglevel=info
