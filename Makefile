SHELL := /bin/zsh
UV ?= uv

.PHONY: sync test check-markdown-links help

help:
	@echo "Targets:"
	@echo "  make sync  - install/update dependencies via uv"
	@echo "  make test  - run unit, integration and acceptance tests"
	@echo "  make check-markdown-links - validate markdown links with lychee"

sync:
	$(UV) lock
	$(UV) sync

test:
	$(UV) run pytest tests/unit tests/integration tests/acceptance -q

check-markdown-links:
	@./scripts/check-markdown-links.sh
