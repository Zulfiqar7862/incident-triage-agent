.PHONY: install run dev test eval check-llm docker clean

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt

run:
	.venv/bin/uvicorn app.main:app --port 8000

# --reload restarts the process on code changes, which marks in-flight runs as
# interrupted. Handy for demoing crash recovery; annoying otherwise.
dev:
	.venv/bin/uvicorn app.main:app --port 8000 --reload

test:
	.venv/bin/pytest -q

# Live two-step tool-calling check against your configured model (uses your API key).
check-llm:
	.venv/bin/python -m scripts.check_llm

eval:
	.venv/bin/python -m evals.run_evals

docker:
	docker compose up --build

clean:
	rm -rf data evals/results .pytest_cache
