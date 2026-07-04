.PHONY: test lint typecheck check

test:
	uv run pytest tests/ -v --cov=renpho --cov-report=term-missing

lint:
	uv run ruff check renpho tests

typecheck:
	uv run mypy

check: lint typecheck test
