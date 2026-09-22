# Design and review notes

These are independent personal utilities packaged together. Their useful common
boundary is small: command discovery, clipboard transport, and predictable CLI
input/output. A common application framework or conversion of every parser would
add coupling without removing the underlying failure modes.

## Contracts

- Package metadata is the command registry. The umbrella command dispatches those
  entry points in the current environment and restores argv after invocation.
- Clipboard transport owns Linux backend selection, MIME capabilities, selection
  handling, and process errors. Markdown rendering and media detection produce
  payloads; they do not implement their own Linux transport.
- Configuration layers contain only explicitly supplied values. Defaults are
  applied once; later scalar values override earlier values, while patterns add.
  Invalid configuration fails before files are gathered.
- Concatenation constructs content without printing filenames as a side effect.
  CLI code owns output. Transcript progress goes to stderr so stdout can be piped.
- External programs are checked when needed. Failed discovery is distinguishable
  from finding no files. A requested ignore policy cannot silently disappear.
- A deployment dry run stops before remote mutations or installation. Tests use
  local process spies, never a real deployment target.

## Why these changes

The previous duplication had already diverged: three clipboard implementations
selected different backends, two passed unsupported MIME flags to xsel, and
screenshots reported success after copying failed. Config merging inferred intent
by comparing values with defaults, making explicit overrides impossible. Content
generation printed filenames, forcing callers to replace global stdout temporarily.
These are ownership and data-model problems; sharing the transport and representing
configuration presence explicitly removes their causes.

## Remaining review areas

This is not a claim that every utility is now fully verified.

- Photo import still combines discovery, date grouping, conflict decisions, and
  writes. Its existing policy chooses originals by oldest mtime and sidecars by
  newest mtime; equal timestamps do not establish equal contents. A future change
  should introduce a reviewable import plan shared by preview and execution,
  with fixtures for reused camera numbers across folders before changing policy.
- Concat still has two discovery engines. Quoted glob interpretation and ignore
  behavior need a single explicit specification before replacing either engine.
- Transcript retry handling is broad and can wait a long time on permanent
  failures. Network error classification needs integration coverage.
- Desktop capture, OCR, macOS/Windows clipboard operations, and real YouTube
  downloads have not been exercised by the offline tests. Screenshot dependencies
  remain an optional install; GUI support also depends on system packages.
- Node scaffolding references TypeScript tooling without installing it. Dependency
  installation and template maintenance need a deliberate project policy.
- The existing agent-export work was left intact; its current tests were included
  in verification, but its log-format coverage was not independently audited.
