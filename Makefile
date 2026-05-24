.PHONY: setup install test test-fast lint check demo run dry-run clean

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

setup: $(VENV)/bin/activate
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt
	@echo "Setup complete. Run: make demo"

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

install: setup

test:
	PYTHONPATH=. $(PY) -m pytest tests/ -v

test-fast:
	PYTHONPATH=. $(PY) -m pytest tests/test_router.py tests/test_context.py tests/test_terminal.py tests/test_metrics.py tests/test_pipeline.py -v

lint:
	$(PY) -m compileall -q src tests

check: lint test-fast
	PYTHONPATH=. $(PY) scripts/check_setup.py

demo:
	./scripts/demo.sh

run:
	PYTHONPATH=. $(PY) -m src.main

dry-run:
	PYTHONPATH=. $(PY) -m src.main --dry-run

clean:
	rm -rf .pytest_cache __pycache__ src/**/__pycache__ tests/**/__pycache__
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
