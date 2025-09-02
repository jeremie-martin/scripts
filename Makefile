# Makefile for managing uv-based tools

# Default target
.DEFAULT_GOAL := help

# Ensure uv is available
UV := uv

## retool: Reinstall project tools from current repo
retool:
	@echo "🔄 Reinstalling scripts with uv..."
	$(UV) tool uninstall scripts || true
	$(UV) tool install --no-cache .

## sync: Sync project dependencies (including extras)
sync:
	@echo "📦 Syncing dependencies..."
	$(UV) sync --all-extras

## clean: Remove local venv and uv tool installation
clean:
	@echo "🧹 Cleaning environment..."
	rm -rf .venv
	$(UV) tool uninstall scripts || true

## help: Show available make targets
help:
	@grep -E '^##' Makefile | sed -e 's/## //'

