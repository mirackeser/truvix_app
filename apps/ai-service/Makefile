.PHONY: run test lint typecheck docker-build docker-run clean

run:
	uvicorn truvix_ai.app:create_app --factory --reload --port 8001

test:
	pytest

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy src/

docker-build:
	docker build -t truvix-ai-service .

docker-run:
	docker run -p 8001:8001 --env-file .env truvix-ai-service

clean:
	rm -rf .venv
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type d -name ".pytest_cache" -exec rm -r {} +
	find . -type d -name ".mypy_cache" -exec rm -r {} +
	find . -type d -name ".ruff_cache" -exec rm -r {} +
