.DEFAULT_GOAL := help
UV ?= uv
BINDIR ?= $(shell $(UV) tool dir --bin)
PYTHON_TOOLS := concat transcript ffcut gdiffpath clipmedia mdclip quick screenshot agent-export image-tools
PYTHON_PROJECTS := $(addprefix tools/,$(PYTHON_TOOLS)) packages/clipboard
SCRIPT_TOOLS := import-photos ssh-clipboard nsxiv-open-dir

.PHONY: help install install-screenshot-ocr lint test test-installation check build $(addprefix install-,$(PYTHON_TOOLS) $(SCRIPT_TOOLS))
help:
	@echo "make install | install-<tool> | install-screenshot-ocr | lint | test | test-installation | check | build"
install: $(addprefix install-,$(PYTHON_TOOLS) $(SCRIPT_TOOLS))
$(addprefix install-,$(PYTHON_TOOLS)): install-%:
	UV_TOOL_BIN_DIR="$(BINDIR)" $(UV) tool install --reinstall --editable "$(CURDIR)/tools/$*"
install-screenshot-ocr:
	UV_TOOL_BIN_DIR="$(BINDIR)" $(UV) tool install --reinstall --editable "$(CURDIR)/tools/screenshot[ocr]"

# Refuse collisions, including directories; an already-correct link is a no-op.
define link_script
	@mkdir -p "$(BINDIR)"
	@if [ -L "$(BINDIR)/$(2)" ] && [ "$$(readlink "$(BINDIR)/$(2)")" = "$(CURDIR)/$(1)" ]; then \
		:; \
	else \
		ln -sT "$(CURDIR)/$(1)" "$(BINDIR)/$(2)"; \
	fi
endef
install-import-photos:
	$(call link_script,tools/import-photos/import_photos.py,import-photos)
install-ssh-clipboard:
	$(call link_script,tools/ssh-clipboard/ssh-clipboard,ssh-clipboard)
install-nsxiv-open-dir:
	$(call link_script,tools/nsxiv-open-dir/nsxiv-open-dir,nsxiv-open-dir)

lint:
	$(UV) tool run --from ruff==0.13.3 ruff check .
	bash -n tools/nsxiv-open-dir/nsxiv-open-dir
test:
	@set -eu; for project in $(PYTHON_PROJECTS); do \
		$(UV) run --project "$$project" --locked pytest "$$project/tests" -q; \
	done
	$(UV) run --no-project --with pytest==9.1.1 pytest $(addsuffix /tests,$(addprefix tools/,$(SCRIPT_TOOLS))) -q
test-installation:
	$(UV) run --no-project --with pytest==9.1.1 pytest tests/test_installation.py -q
check: lint test test-installation
build:
	@set -eu; for project in $(PYTHON_PROJECTS); do \
		$(UV) build "$$project" --out-dir "$(CURDIR)/dist"; \
	done
