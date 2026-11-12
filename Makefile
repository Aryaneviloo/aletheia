.PHONY: sync infra infra-gpu migrate test

sync:
	uv sync --all-packages --group dev

infra:
	docker compose up -d postgres redis qdrant ollama

infra-gpu:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d ollama

migrate:
	uv run --directory libs/aletheia_core alembic upgrade head

test:
	uv run pytest
