.PHONY: test lint build clean

test:
	uv run pytest

lint:
	uv run ruff check
	uv run ruff format --check
	uv run mypy

build:
	./build.sh

clean:
	rm -rf dist .pytest_cache .ruff_cache
