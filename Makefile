.PHONY: dev test lint typecheck audit coverage docker-build docker-run smoke-test clean

# Development
dev:
	cd backend && uvicorn app:create_app --factory --reload --port 8000

# Testing
test:
	pytest tests/ -v

coverage:
	pytest tests/ --cov=backend --cov-report=term-missing --cov-report=html:htmlcov

# Code quality
lint:
	ruff check backend/ tests/
	ruff format --check backend/ tests/

typecheck:
	mypy backend/ --ignore-missing-imports

audit:
	pip-audit -r backend/requirements.txt

# Docker
docker-build:
	docker-compose -f infra/docker-compose.yml build

docker-run:
	docker-compose -f infra/docker-compose.yml up

docker-down:
	docker-compose -f infra/docker-compose.yml down

# Smoke test (requires running server)
smoke-test:
	@echo "Running smoke tests..."
	@curl -sf http://localhost:8000/api/health | python -m json.tool > /dev/null && echo "✓ Health check passed" || echo "✗ Health check failed"
	@curl -sf "http://localhost:8000/api/tickers?query=AAPL" | python -m json.tool > /dev/null && echo "✓ Ticker search passed" || echo "✗ Ticker search failed"
	@curl -sf -X POST http://localhost:8000/api/predict -H "Content-Type: application/json" -d '{"symbol":"AAPL","asset_type":"stock","engine":"stat","horizon":7}' | python -m json.tool > /dev/null && echo "✓ Stat prediction passed" || echo "✗ Stat prediction failed"
	@echo "Smoke tests complete."

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
