UV ?= uv
PYTHON ?= python
.PHONY: sync help test test-qualification lint format-check typecheck check build audit graph verify-evidence

help:
	$(UV) run dv-platform --help
sync:
	$(UV) sync --all-groups --extra ai --frozen
test:
	$(UV) run $(PYTHON) -m unittest discover -s tests -v
test-qualification:
	$(UV) run $(PYTHON) -m unittest discover -s qualification/tests -v
lint:
	$(UV) run ruff check src enterprise/src tests scripts
format-check:
	$(UV) run ruff format --check src enterprise/src tests scripts
typecheck:
	$(UV) run mypy
check: lint format-check typecheck
	$(UV) run $(PYTHON) -m scripts.checks.repository_contracts
	$(UV) run $(PYTHON) -m scripts.checks.maintainability --check
	$(UV) run $(PYTHON) -m scripts.checks.compatibility --check
	$(UV) run $(PYTHON) -m scripts.checks.secrets
build:
	$(UV) build --wheel --out-dir .dv-platform/build/free
	$(UV) build --wheel --project enterprise --out-dir .dv-platform/build/enterprise
audit:
	$(UV) run pip-audit --skip-editable
graph:
	$(UV) run dv-platform context-optimize update-graph
verify-evidence:
	$(UV) run $(PYTHON) -m scripts.checks.repository_contracts --require-local-evidence
