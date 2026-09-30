# Family Clinic Memory Assistant — developer Makefile
#
# Usage:
#   make setup    install all dependencies
#   make run      start the dev server (real API keys required)
#   make demo     start in DEMO_MODE (zero API keys needed)
#   make seed     seed 3 realistic demo patient histories into Hindsight
#   make test     run the 119-test suite (always uses DEMO_MODE)
#   make lint     ruff + mypy
#   make clean    remove __pycache__ and .pyc files

.PHONY: setup run demo seed test lint clean

setup:
	pip install -r requirements.txt
	pip install pytest pytest-asyncio ruff mypy

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

demo:
	DEMO_MODE=true uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

seed:
	python scripts/seed_demo.py

test:
	DEMO_MODE=true pytest test_core.py tests/ -v --tb=short

lint:
	ruff check app/ tests/
	mypy app/ --ignore-missing-imports

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

