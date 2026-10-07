install:
	uv pip install -e ".[dev]"

run:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest --cov=app --cov-report=term-missing

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
