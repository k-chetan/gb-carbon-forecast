.PHONY: setup lint format test run-app logger-once report refresh verify

verify:
	uv run pytest -q
	uv run python scripts/independent_recompute.py
	@echo "re-run the live chaos drill with:"
	@echo "  gh workflow run vintage-logger.yml -f simulate_failure=true"
	@echo "  gh workflow run watchdog.yml -f max_capture_age_hours=0"

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
	PYTHONPATH=src uv run python scripts/report_figures.py
	mkdir -p build
	typst compile report/report.typ build/report.pdf
	@echo "-> build/report.pdf"

refresh:
	@echo "re-scoring prospective legs and rebuilding the report"
	git fetch origin vintage-log:vintage-log || true
	rm -rf .vintage-ro && git worktree prune && git worktree add .vintage-ro vintage-log
	PYTHONPATH=src uv run python -m gbcarbon.scoring --vintages .vintage-ro/vintages --results results
	PYTHONPATH=src uv run python scripts/score_operator_legs.py \
		--run-a $(RUN_A) --run-b $(RUN_B) --own-vintages .vintage-ro/vintages
	git worktree remove --force .vintage-ro
	$(MAKE) report
