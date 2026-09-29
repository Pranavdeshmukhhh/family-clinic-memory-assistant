# Family Clinic Memory Assistant — developer Makefile
#
# Usage:
#   make setup    install all dependencies
#   make run      start the dev server (real API keys required)
#   make demo     start in DEMO_MODE (no API keys needed)
#   make test     run the test suite (always uses DEMO_MODE)
#   make lint     ruff + mypy
#   make clean    remove __pycache__ and .pyc files

.PHONY: setup run demo test lint clean

setup:
	pip install -e ".[dev]"

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

demo:
	DEMO_MODE=true uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	DEMO_MODE=true pytest tests/ -v --tb=short

lint:
	ruff check app/ tests/
	mypy app/ --ignore-missing-imports

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
