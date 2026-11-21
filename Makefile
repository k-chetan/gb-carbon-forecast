.PHONY: setup lint format test run-app logger-once report refresh

setup:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest -q

run-app:
	uv run streamlit run app.py

logger-once:
	PYTHONPATH=src uv run python -m gbcarbon.vintage --out ./vintages-local

report:
	@echo "report build arrives with the evaluation milestone (typst)"

refresh:
	@echo "pre-submission refresh arrives with the report milestone"
