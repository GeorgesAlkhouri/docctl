SHELL := /bin/zsh
UV ?= uv

.PHONY: sync test help

help:
	@echo "Targets:"
	@echo "  make sync  - install/update dependencies via uv"
	@echo "  make test  - run unit, integration and acceptance tests"

sync:
	$(UV) lock
	$(UV) sync

test:
	$(UV) run pytest tests/unit tests/integration tests/acceptance -q
