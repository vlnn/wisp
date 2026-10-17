.PHONY: test lint build check clean

test:
	uv run pytest

lint:
	uv run ruff check
	uv run ruff format --check
	uv run mypy

build:
	uv run --python 3.13 python -m hoard.build

check: build
	uv run --python 3.13 python -m hoard.build --check
	/usr/bin/env python3 scripts/smoke.py dist/wisp.alfredworkflow

clean:
	rm -rf dist .pytest_cache .ruff_cache
