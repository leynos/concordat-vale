MDLINT ?= markdownlint-cli2
NIXIE ?= $(shell which nixie)
TOOLS = ruff ty $(MDLINT) $(MDTABLEFIX) $(NIXIE) uv
VENV_TOOLS = pytest
# Every uv call goes through the vendored helper, which cleans the environment,
# uses the global uv cache, runs offline first and goes online at most once. See
# https://github.com/leynos/shared-actions/tree/main/uv_gate for the contract.
UV_GATE ?= python3 scripts/uv_gate.py
# Commit of the stilyagi v0.1.0 tag; a pin must be a full commit.
STILYAGI_SOURCE ?= git+https://github.com/leynos/stilyagi.git@dff60b0c46c5b2c1b322dd039e7fc0f488e1db7b
PYTHON ?= python3
VALE ?= vale
VALE_CONFIG ?= .vale.ini
VALE_TARGETS ?= README.md docs/**/*.md
VALE_ARCHIVE ?= dist/concordat-dev.zip
ACRONYM_SCRIPT ?= scripts/update_acronym_allowlist.py

ACT_WORKFLOW_TESTS ?= 0

# `make fmt` and `make check-fmt` call mdtablefix directly. `--git` selects the
# Markdown files Git tracks and `--include-untracked` adds the untracked files
# Git does not ignore, so a new document is formatted before it is staged.
# Both modes need mdtablefix 0.6.1 or later.
MDTABLEFIX ?= mdtablefix
MDTABLEFIX_SELECT = --git --include-untracked
MDTABLEFIX_RULES = --wrap --renumber --breaks --ellipsis --fences

.PHONY: help all clean build prepare build-release lint fmt check-fmt \
        markdownlint nixie test typecheck vale-archive vale-sync vale \
        $(TOOLS) $(VENV_TOOLS)

.DEFAULT_GOAL := all

all: build check-fmt test typecheck

prepare: uv ## Install the locked development environment, offline first
	$(UV_GATE) prepare --group dev

build: prepare ## Build virtual-env and install deps

build-release: ## Build artefacts (sdist & wheel)
	python -m build --sdist --wheel

clean: ## Remove build artifacts
	rm -rf build dist *.egg-info \
	  .mypy_cache .pytest_cache .coverage coverage.* \
	  lcov.info htmlcov .venv
	find . -type d -name '__pycache__' -print0 | xargs -0 -r rm -rf

define ensure_tool
	@command -v $(1) >/dev/null 2>&1 || { \
	  printf "Error: '%s' is required, but not installed\n" "$(1)" >&2; \
	  exit 1; \
	}
endef

define ensure_tool_venv
	$(UV_GATE) run --group dev -- which $(1) >/dev/null 2>&1 || { \
	  printf "Error: '%s' is required in the virtualenv, but is not installed\n" "$(1)" >&2; \
	  exit 1; \
	}
endef

ifneq ($(strip $(TOOLS)),)
$(TOOLS): ## Verify required CLI tools
	$(call ensure_tool,$@)
endif


ifneq ($(strip $(VENV_TOOLS)),)
.PHONY: $(VENV_TOOLS)
$(VENV_TOOLS): ## Verify required CLI tools in venv
	$(call ensure_tool_venv,$@)
endif

fmt: ruff $(MDTABLEFIX) $(MDLINT) ## Format sources
	ruff format
	ruff check --select I --fix
	$(MDTABLEFIX) --in-place $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)
	$(MDLINT) --fix "**/*.md"

check-fmt: ruff $(MDTABLEFIX) ## Verify formatting
	ruff format --check
	$(MDTABLEFIX) --check $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)

lint: ruff ## Run linters
	ruff check

typecheck: build ty ## Run typechecking
	ty --version
	ty check

markdownlint: $(MDLINT) ## Lint Markdown files
	$(MDLINT) '**/*.md'

nixie: $(NIXIE) ## Validate Mermaid diagrams
	$(NIXIE) --no-sandbox

vale-archive: build ## Build the dev Concordat archive for local linting
	$(UV_GATE) tool --from $(STILYAGI_SOURCE) -- stilyagi zip \
	  --archive-version dev --force

vale-sync: vale-archive ## Sync Concordat into .vale/styles
	$(VALE) sync --config $(VALE_CONFIG)

vale: vale-sync ## Lint docs with Vale after syncing and patching acronyms
	$(UV_GATE) run --group dev -- python $(ACRONYM_SCRIPT)
	$(VALE) --config $(VALE_CONFIG) --minAlertLevel suggestion $(VALE_TARGETS)

test: build uv $(VENV_TOOLS) ## Run tests
	$(UV_GATE) run --group dev -- pytest -v -n auto

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'
