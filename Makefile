.PHONY: install run dev test eval clean

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

run:
	.venv/bin/uvicorn app.main:app --port 8000

# --reload restarts the process on code changes, which marks in-flight runs as
# interrupted. Handy for demoing crash recovery; annoying otherwise.
dev:
	.venv/bin/uvicorn app.main:app --port 8000 --reload

test:
	.venv/bin/pytest -q

eval:
	.venv/bin/python -m evals.run_evals

clean:
	rm -rf data evals/results .pytest_cache
