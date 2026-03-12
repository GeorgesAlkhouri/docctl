SHELL := /bin/zsh
UV ?= uv

.PHONY: sync test test-cov lint lint-preview typecheck typecheck-changed security-lint import-lint format format-check build-dist check-dist release-dry-run check-markdown-links help

help:
	@echo "Targets:"
	@echo "  make sync  - install/update dependencies via uv"
	@echo "  make lint  - run ruff lint checks"
	@echo "  make lint-preview - run optional preview-only Ruff checks (non-blocking)"
	@echo "  make typecheck - run mypy on src"
	@echo "  make typecheck-changed - run mypy on changed src modules"
	@echo "  make security-lint - run bandit security checks on src"
	@echo "  make import-lint - run import-linter architecture contracts"
	@echo "  make format - apply ruff formatter"
	@echo "  make format-check - verify ruff formatting"
	@echo "  make test  - run unit, integration and acceptance tests"
	@echo "  make test-cov - run tests and write coverage report to coverage.xml"
	@echo "  make build-dist - build sdist and wheel into dist/"
	@echo "  make check-dist - verify built distributions with twine"
	@echo "  make release-dry-run - preview the next semantic-release version"
	@echo "  make check-markdown-links - validate markdown links with lychee"

sync:
	$(UV) lock
	$(UV) sync

lint:
	$(UV) run ruff check src tests

lint-preview:
	-$(UV) run ruff check src tests --preview --select PLR0904,PLR0914,PLR0917,PLR1702

typecheck:
	$(UV) run mypy src

typecheck-changed:
	@./scripts/typecheck-changed.sh

security-lint:
	$(UV) run bandit -q -r src

import-lint:
	$(UV) run lint-imports

format:
	$(UV) run ruff check src tests --fix
	$(UV) run ruff format src tests

format-check:
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests

test:
	$(UV) run pytest tests/unit tests/integration tests/acceptance -q

test-cov:
	$(UV) run pytest tests/unit tests/integration tests/acceptance -q --cov=src/docctl --cov-report=term --cov-report=xml:coverage.xml

build-dist:
	$(UV) build

check-dist:
	$(UV) run twine check dist/*

release-dry-run:
	$(UV) run semantic-release --strict --noop version --print

check-markdown-links:
	@./scripts/check-markdown-links.sh
