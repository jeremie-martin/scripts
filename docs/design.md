# Design boundaries

This repository is a collection, not an application. A tool owns its source,
dependencies, documentation, and tests. A native installer owns environments and
entry points. The Makefile is optional shorthand, not another package manager.

The former aggregate package coupled unrelated tools through dependency resolution,
extras, deployment, and command discovery. Independent projects remove those
couplings: installing or removing one tool does not affect another. A new shell
script needs no Python wrapper. Large applications remain separate repositories.

## Shared code

The clipboard library owns backend selection, MIME support, selection handling,
and process errors. Consumers explicitly declare it as a dependency; renderers
produce payloads rather than implementing transports. Editable relative-path
sources support checkout development, while ordinary wheel requirements support
distribution without the checkout. The SSH clipboard executable remains independent
because it transmits its own source to a remote Python interpreter.

## Behavioral contracts

- Preserve established commands and input/output formats.
- Apply configuration defaults once, retaining the distinction between missing
  and explicitly supplied values.
- Content generation does not print filenames as a side effect. Progress belongs
  on stderr when stdout is useful as a pipeline.
- Discover external programs only when needed and report failures explicitly.
- Keep destructive operations and real desktop/network effects out of tests.
- Test tools in their own environments and test both native editable and wheel
  installations. There is no root package to mask missing dependencies.
- OCR is an explicit screenshot extra. ffcut owns yt-dlp and invokes it through
  its own interpreter rather than an unrelated executable on PATH.

## Remaining review areas

Structural independence does not imply every algorithm has been redesigned.
Photo import still combines discovery, date grouping, conflict policy, and writes;
equal timestamps do not establish equal contents. Concat retains two discovery
engines whose glob and ignore semantics need a deliberate unified specification.
Transcript retries remain broad. Quick's Node template needs a dependency policy.
Agent export's existing work is preserved, not a claim of exhaustive log-format
coverage. Desktop capture, OCR, platform-specific clipboard operations, and real
YouTube downloads still require manual integration testing.
