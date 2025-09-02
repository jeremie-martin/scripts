# Makefile for managing uv-based tools

# Default target
.DEFAULT_GOAL := help

# Ensure uv is available
UV := uv

.PHONY: retool sync clean ensure-path ship help

## retool: Reinstall project tools from current repo (and ensure PATH in rc files)
retool:
	@echo "🔄 Reinstalling scripts with uv..."
	$(UV) tool uninstall scripts || true
	$(UV) tool install --no-cache .
	@$(MAKE) ensure-path

## sync: Sync project dependencies (including extras)
sync:
	@echo "📦 Syncing dependencies..."
	$(UV) sync --all-extras

## clean: Remove local venv and uv tool installation
clean:
	@echo "🧹 Cleaning environment..."
	rm -rf .venv
	$(UV) tool uninstall scripts || true

## ensure-path: Add ~/.local/bin to PATH in ~/.bashrc and ~/.zshrc (idempotent)
ensure-path:
	@printf "🧭 Ensuring %s is on PATH in bashrc/zshrc…\n" "$$HOME/.local/bin"
	@/bin/sh -lc 'set -eu; \
	  mkdir -p "$$HOME/.local/bin"; \
	  for rc in "$$HOME/.bashrc" "$$HOME/.zshrc"; do \
	    [ -f "$$rc" ] || : > "$$rc"; \
	    sed -i -e "/^# >>> scripts PATH (managed) >>>$$/,/^# <<< scripts PATH (managed) <<<$$/d" "$$rc"; \
	    printf "%s\n" \
	      "# >>> scripts PATH (managed) >>>" \
	      "if [ -d \"$$HOME/.local/bin\" ]; then" \
	      "  case \":$$PATH:\" in *\":$$HOME/.local/bin:\"*) :;; *) export PATH=\"$$HOME/.local/bin:$$PATH\";; esac" \
	      "fi" \
	      "# <<< scripts PATH (managed) <<<" \
	      >> "$$rc"; \
	  done'
	@echo "✅ PATH block ensured in ~/.bashrc and ~/.zshrc"

## ship: Rsync this repo to HOST (default dir ~/.scripts) and refresh tools
ship:
	@if [ -z "$(HOST)" ]; then \
		echo "Usage: make ship HOST=user@host [DIR=~/.scripts]"; exit 2; \
	fi
	dev/ship.sh "$(HOST)" $(if $(DIR),--dir $(DIR))

## help: Show available make targets
help:
	@grep -E '^##' Makefile | sed -e 's/## //'
