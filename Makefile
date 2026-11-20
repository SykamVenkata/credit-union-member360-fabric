.PHONY: install data run test lint brief

install:
	pip install -e ".[dev]"

data:
	python data/generators/generate.py

run:
	python scripts/run_local.py

brief: run
	python scripts/brief.py

test:
	pytest -q

lint:
	ruff check src tests scripts data/generators
