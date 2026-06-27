# Makefile for managing uv-based tools

# Default target
.DEFAULT_GOAL := help

# Ensure uv is available
UV := uv

.PHONY: retool retool-ocr sync clean ship help

## retool: Install tools (editable) — edits to existing commands go live, no reinstall
retool:
	@echo "🔄 Installing scripts (editable) with uv..."
	$(UV) tool install --force --editable '.[screenshot]'

## retool-ocr: Like retool, but also pulls the heavy OCR extra (torch/transformers)
retool-ocr:
	@echo "🔄 Installing scripts (editable, with OCR) with uv..."
	$(UV) tool install --force --editable '.[screenshot,ocr]'

## sync: Sync project dependencies (including extras)
sync:
	@echo "📦 Syncing dependencies..."
	$(UV) sync --all-extras

## clean: Remove local venv and uv tool installation
clean:
	@echo "🧹 Cleaning environment..."
	rm -rf .venv
	$(UV) tool uninstall scripts || true

## ship: Rsync this repo to HOST (default dir ~/.scripts) and refresh tools
ship:
	@if [ -z "$(HOST)" ]; then \
		echo "Usage: make ship HOST=user@host [DIR=~/.scripts]"; exit 2; \
	fi
	dev/ship.sh "$(HOST)" $(if $(DIR),--dir $(DIR))

## help: Show available make targets
help:
	@grep -E '^##' Makefile | sed -e 's/## //'
