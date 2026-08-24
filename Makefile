.PHONY: help sync cli-help init analyze-dry analyze index-docs plan plan-ai generate run coverage status status-ci ci test lint format-check typecheck python-coverage quality package-check audit clean-package-check

UV ?= uv
PYTHON ?= python

REPO_ROOT ?= .
WORK_DIR ?=
OUTPUT_DIR ?=
CONFIG ?=

TARGET ?= cocotb
MODULE ?=
RUN_TIMEOUT ?=

DOCS ?= docs
RTL_FILELIST ?=
INCLUDE_PATH ?=
TOP ?=
DEFINE ?=
PARAMETER ?=
PARAMETER_SWEEP ?=

JSON ?= 0
AI ?= 0
AI_REFRESH ?= 0
NO_REQUIRE_TOOLS ?= 0

DV := $(UV) run dv-platform

GLOBAL_FLAGS := --repo-root $(REPO_ROOT)
GLOBAL_FLAGS += $(if $(CONFIG),--config $(CONFIG))
GLOBAL_FLAGS += $(if $(WORK_DIR),--work-dir $(WORK_DIR))
GLOBAL_FLAGS += $(if $(OUTPUT_DIR),--output-dir $(OUTPUT_DIR))

JSON_FLAG :=
ifeq ($(JSON),1)
JSON_FLAG := --json
endif

CI_FLAGS := --ci $(JSON_FLAG)
CLI_FLAGS := $(GLOBAL_FLAGS) $(JSON_FLAG)

INIT_FLAGS := $(if $(DOCS),--documentation-path $(DOCS))
INIT_FLAGS += $(if $(RTL_FILELIST),--rtl-filelist $(RTL_FILELIST))
INIT_FLAGS += $(if $(INCLUDE_PATH),--include-path $(INCLUDE_PATH))
INIT_FLAGS += $(if $(TOP),--top-module $(TOP))
INIT_FLAGS += $(foreach item,$(DEFINE),--define $(item))
INIT_FLAGS += $(foreach item,$(PARAMETER),--parameter $(item))
INIT_FLAGS += $(foreach item,$(PARAMETER_SWEEP),--parameter-sweep $(item))

PLAN_FLAGS := --target $(TARGET)
ifeq ($(AI),1)
PLAN_FLAGS += --ai
endif
ifeq ($(AI_REFRESH),1)
PLAN_FLAGS += --ai-refresh
endif
PLAN_FLAGS += $(if $(MODULE),--module $(MODULE))

RUN_SCOPE := --all
ifneq ($(strip $(MODULE)),)
RUN_SCOPE := --module $(MODULE)
endif

RUN_FLAGS := --target $(TARGET) $(RUN_SCOPE)
RUN_FLAGS += $(if $(RUN_TIMEOUT),--timeout-seconds $(RUN_TIMEOUT))

STATUS_FLAGS := --policy report
ifeq ($(NO_REQUIRE_TOOLS),1)
STATUS_FLAGS += --no-require-tools
endif

help:
	@printf '%s\n' 'Common targets:'
	@printf '  %-18s %s\n' 'make sync' 'Install locked dependencies with uv.'
	@printf '  %-18s %s\n' 'make init' 'Create dv-platform.toml for an RTL repo.'
	@printf '  %-18s %s\n' 'make analyze-dry' 'Show discovered RTL inputs and tool command.'
	@printf '  %-18s %s\n' 'make analyze' 'Extract RTL facts.'
	@printf '  %-18s %s\n' 'make index-docs' 'Build the local documentation index.'
	@printf '  %-18s %s\n' 'make plan' 'Generate verification plans.'
	@printf '  %-18s %s\n' 'make generate' 'Generate verification collateral.'
	@printf '  %-18s %s\n' 'make run' 'Run generated checks for TARGET and MODULE, or all modules.'
	@printf '  %-18s %s\n' 'make coverage' 'Import coverage from persisted runs.'
	@printf '  %-18s %s\n' 'make status-ci' 'Apply the CI status gate.'
	@printf '  %-18s %s\n' 'make ci' 'Run the standard CI verification flow.'
	@printf '%s\n' ''
	@printf '%s\n' 'Useful overrides:'
	@printf '%s\n' '  REPO_ROOT=/path/to/rtl TARGET=formal MODULE=fifo JSON=1'
	@printf '%s\n' '  RTL_FILELIST=rtl/files.f INCLUDE_PATH=rtl/include TOP=top'

sync:
	$(UV) sync --all-groups --frozen

cli-help:
	$(DV) --help

init:
	$(DV) $(CLI_FLAGS) init $(INIT_FLAGS)

analyze-dry:
	$(DV) $(CLI_FLAGS) analyze-rtl --dry-run

analyze:
	$(DV) $(CLI_FLAGS) analyze-rtl

index-docs:
	$(DV) $(CLI_FLAGS) index-docs

plan:
	$(DV) $(CLI_FLAGS) plan $(PLAN_FLAGS)

plan-ai:
	$(MAKE) plan AI=1

generate:
	$(DV) $(CLI_FLAGS) generate --target $(TARGET)

run:
	$(DV) $(CLI_FLAGS) run $(RUN_FLAGS)

coverage:
	$(DV) $(CLI_FLAGS) coverage --from-runs

status:
	$(DV) $(CLI_FLAGS) status $(STATUS_FLAGS)

status-ci:
	$(DV) $(GLOBAL_FLAGS) --ci $(JSON_FLAG) status --policy ci $(if $(filter 1,$(NO_REQUIRE_TOOLS)),--no-require-tools)

ci: sync
	$(DV) $(GLOBAL_FLAGS) $(CI_FLAGS) analyze-rtl
	$(DV) $(GLOBAL_FLAGS) $(CI_FLAGS) index-docs
	$(DV) $(GLOBAL_FLAGS) $(CI_FLAGS) plan --target $(TARGET)
	$(DV) $(GLOBAL_FLAGS) $(CI_FLAGS) generate --target $(TARGET)
	$(DV) $(GLOBAL_FLAGS) $(CI_FLAGS) run --target $(TARGET) --all
	$(DV) $(GLOBAL_FLAGS) $(CI_FLAGS) coverage --from-runs
	$(DV) $(GLOBAL_FLAGS) $(CI_FLAGS) status --policy ci $(if $(filter 1,$(NO_REQUIRE_TOOLS)),--no-require-tools)

test:
	$(UV) run $(PYTHON) -m unittest discover -s tests

lint:
	$(UV) run ruff check src enterprise/src tests scripts

format-check:
	$(UV) run ruff format --check src enterprise/src tests scripts

typecheck:
	$(UV) run mypy

python-coverage:
	$(UV) run coverage run -m unittest discover -s tests
	$(UV) run coverage report
	$(UV) run coverage json -o .dv-platform/python-coverage.json
	$(UV) run $(PYTHON) scripts/checks/branch_coverage.py .dv-platform/python-coverage.json

quality: lint format-check typecheck python-coverage package-check audit

package-check: clean-package-check
	$(UV) build --out-dir .dv-platform/package-check

audit:
	$(UV) run pip-audit --skip-editable

clean-package-check:
	rm -rf .dv-platform/package-check
