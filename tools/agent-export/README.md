# agent-export

Export visible Claude and Codex conversations from local session logs.

## Install and update

From the repository root:

```sh
uv tool install --editable tools/agent-export
```

Source edits are live. After changing dependencies or entry points, repeat the command
with `--reinstall`. Use `uv tool uninstall scripts-agent-export` to uninstall.
For an installation independent of this checkout, use wheels as described in
the root README. Shared-library consumers must include the clipboard wheel.

## Use

```sh
agent-export SESSION_ID        # saves ./DATE-TITLE.md, e.g. 2026-09-22-review-prompt-add-improvements.md
agent-export                   # choose a recent session with fzf (this directory's sessions first)
agent-export SESSION_ID > x.md # piped or redirected output is markdown on stdout
```

The session ID is the one Claude and Codex print when a session closes; a `.jsonl`
path works too. In a terminal, the transcript is saved in the current directory under
the session's start date and title, and the command reports its size in tokens.
Re-exporting a session replaces its own file; a different session with the same
title gets its ID appended instead of overwriting.

```sh
agent-export SESSION_ID -o notes/         # into a directory, with the default name
agent-export SESSION_ID -o session.json   # format follows the extension (.md, .txt, .json)
agent-export SESSION_ID -o -              # stdout, even in a terminal
agent-export SESSION_ID --no-activity     # omit the per-turn tool activity lines
agent-export SESSION_ID --single-session  # do not join Claude continuations
agent-export SESSION_ID --strict          # refuse to export if anything may be missing
```

The picker needs `fzf`; its preview uses `bat` when available. It lists interactive
sessions that have at least one prompt, hiding `codex exec` runs and subagents.

## What a transcript contains

The export is meant as context for another agent, so it keeps what was said and
compresses what was done:

- A header with the title, project directory and git branch, date range, every model
  and reasoning effort used, the session ID, and the source log path.
- The conversation in turns: one `## User` or `## Agent` section per speaker change,
  including slash commands, questions and choices, submitted answers, proposed plans
  and approvals, readable summaries, and attachment references.
- One line at the end of each agent turn summarizing its tool use, such as
  `Tool activity: 28 commands; edited src/server.py, README.md; 2 web lookups.`
  This typically adds 1–3% to the transcript.
- A quoted note where the model or effort changed, or where a turn was interrupted,
  rolled back, or compacted.

Model reasoning, tool calls and their output, and injected setup context are omitted.
The `text` format has the same structure without markdown; `json` is one object per
visible message with its source file, JSONL line, and timestamp.

Explicit Claude continuation links are followed in both directions by default;
copied records are deduplicated by message UUID. Codex's response, event, and
completed-item representations are matched by occurrence within a turn, so
ordinary repeated replies survive. Codex forks are exported as the selected
branch's recorded history; separate forks and subagents are not automatically
merged. In-log rollbacks are marked, with the earlier exchanges retained.

Images, audio, and documents retain references or explicit embedded-attachment
placeholders; their binary contents are not included. Some Codex compactions
contain only encrypted summaries: the export marks that limitation and preserves
the readable history. Unknown conversation blocks, malformed JSON lines, and missing
linked Claude sessions produce warnings on stderr. A partial Codex write that is
followed by the complete record loses nothing and is skipped silently. Questions
embedded inside executable tool scripts cannot currently be reconstructed; detected
calls produce a warning. This is a readable transcript, not a lossless backup; keep
the original JSONL files when archival completeness matters.

To audit format coverage against recent local logs without printing their text:

```bash
uv run --project tools/agent-export python tools/agent-export/dev/audit_agent_export.py --days 7
uv run --project tools/agent-export pytest tools/agent-export/tests
```

The audit selects files by modification time and inspects their full history,
including subagent logs as format samples. It reports structural counts, export
warnings, and any command or recognized dialogue-tool calls absent from the export.


## Develop

```sh
uv run --project tools/agent-export --locked pytest tools/agent-export/tests
uv build tools/agent-export
```

The project lockfile controls the development environment. `uv tool install`
resolves the declared package requirements separately; it does not consume that lockfile.
