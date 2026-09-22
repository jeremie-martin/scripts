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
agent-export SESSION_ID
agent-export SESSION_ID --format markdown -o conversation.md
```

## Export behavior

`agent-export` accepts either a `.jsonl` path or a session ID. For an ID it searches
`~/.claude` and `~/.codex` and detects the log format. The default is a faithful,
chronological conversation, with all user and assistant prose retained. It
includes slash-command prompts, questions and choices, submitted answers,
proposed plans and approvals, readable summaries, and attachment references.
It does not rank or summarize away progress updates. Operational tool calls,
code-edit results, model reasoning, and injected setup context are omitted.

Explicit Claude continuation links are followed in both directions by default;
copied records are deduplicated by message UUID. Codex's response, event, and
completed-item representations are matched by occurrence within a turn, so
ordinary repeated replies survive. Codex forks are exported as the selected
branch's recorded history; separate forks and subagents are not automatically
merged. In-log rollbacks are marked, with the earlier exchanges retained.

```bash
agent-export 01a01dad-fd6f-7d53-9ac5-b07470d7150e
agent-export ~/.claude/projects/example/session.jsonl
agent-export SESSION_ID --format markdown -o conversation.md
agent-export SESSION_ID --format json -o conversation.json
agent-export SESSION_ID --single-session
agent-export SESSION_ID --strict
```

Text is the default format. JSON adds the source file, JSONL line number, and
timestamp for each entry. `SUMMARY` and `NOTICE` labels distinguish generated
recaps and session events from things the user actually said. Output goes to
stdout unless `-o` is supplied; an existing output file is replaced. Diagnostics
go to stderr so redirected transcripts stay clean.

Images, audio, and documents retain references or explicit embedded-attachment
placeholders; their binary contents are not included. Some Codex compactions
contain only encrypted summaries: the export marks that limitation and preserves
the readable history. Unknown conversation blocks and malformed JSON lines
produce warnings, as do missing linked Claude sessions. `--strict` refuses to
produce an export when such warnings occur. Questions embedded inside executable
tool scripts cannot currently be reconstructed; detected calls produce a warning.
This is a readable transcript, not a lossless backup of every internal log event;
keep the original JSONL files when archival completeness matters.

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
