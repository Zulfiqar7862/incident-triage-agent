.PHONY: install run dev test eval check-llm docker clean quickstart lint typecheck frontend frontend-dev frontend-test

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt
	.venv/bin/pre-commit install || true
	cd frontend && npm ci

run:
	.venv/bin/uvicorn app.main:app --port 8000

dev:
	.venv/bin/uvicorn app.main:app --port 8000 --reload

frontend:
	cd frontend && npm run build

frontend-dev:
	cd frontend && npm run dev

frontend-test:
	cd frontend && npm run lint && npm run typecheck && npm test

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check app tests evals scripts
	.venv/bin/ruff format --check app tests evals scripts

typecheck:
	.venv/bin/mypy -p app

check-llm:
	.venv/bin/python -m scripts.check_llm

eval:
	.venv/bin/python -m evals.run_evals

docker:
	docker compose up --build

clean:
	rm -rf data evals/results .pytest_cache frontend/dist

quickstart:
	bash scripts/quickstart.sh
