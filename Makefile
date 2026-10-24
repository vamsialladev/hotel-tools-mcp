.PHONY: check lint test eval sync keys demo

check: lint test eval sync

lint:
	ruff check .
	ruff format --check .

test:
	python -m pytest --cov --cov-fail-under=85

eval:
	python -m eval.run_eval --runs 3 --min-pass 1.0 --no-report

sync:
	python scripts/sync_policy.py --check

keys:
	python scripts/make_keys.py

demo:
	python scripts/demo_roles.py
