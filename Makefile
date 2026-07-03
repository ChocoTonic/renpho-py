.PHONY: test

test:
	uv run pytest tests/ -v --cov=renpho --cov-report=term-missing
