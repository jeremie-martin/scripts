"""Inventory recently modified logs without printing conversation content.

Run from the repository: uv run --project tools/agent-export python tools/agent-export/dev/audit_agent_export.py --days 7
Files are selected by modification time; their entire history is inspected.
Both export modes and joined interactive conversations are checked. The output
is aggregate JSON plus file/line locations of completeness warnings; no message
text is printed. A nonzero exit status means a coverage problem was found.
This is a structural audit, not a proof of semantic completeness.
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from scripts_agent_export import (
    CODEX_TOOL_CALLS,
    CODEX_TOOL_RESULTS,
    DIALOGUE_TOOLS,
    TOOL_ROLES,
    ExportWarning,
    Message,
    SessionError,
    conversation_entries,
    detect_session_format,
    entries_from,
)


def _check_exports(path: Path, *, joined: bool = False) -> tuple[list[Message], Counter[int], Counter[str]]:
    """Check that tool details add information without changing the conversation."""
    session_format = detect_session_format(path)
    reader = conversation_entries if joined else entries_from
    plain = [e for e in reader(path, session_format=session_format) if isinstance(e, Message)]
    detailed = []
    tool_lines: Counter[int] = Counter()
    tool_roles: Counter[str] = Counter()
    for entry in reader(path, session_format=session_format, include_tools=True):
        if not isinstance(entry, Message):
            continue
        if entry.role in TOOL_ROLES:
            tool_roles[entry.role] += 1
            tool_lines[entry.line] += 1
        else:
            detailed.append(entry)
    # Message equality intentionally ignores locations; this check includes them.
    if [asdict(m) for m in plain] != [asdict(m) for m in detailed]:
        raise SessionError("Conversation differs between default and --include-tools exports")
    return plain, tool_lines, tool_roles


def audit(roots: list[Path], days: float) -> dict:
    cutoff = time.time() - days * 86400
    totals: Counter[str] = Counter()
    shapes: Counter[str] = Counter()
    tool_names: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    detailed_roles: Counter[str] = Counter()
    problems = []
    main_paths = []
    started = time.monotonic()
    for root in roots:
        for path in sorted(root.expanduser().rglob("*.jsonl")):
            if path.stat().st_mtime < cutoff:
                continue
            totals["files"] += 1
            totals["bytes"] += path.stat().st_size
            expected_dialogue_lines = set()
            expected_tool_lines: Counter[int] = Counter()
            seen_uuids = set()
            interactive = "subagents" not in path.parts
            provider = "unknown"
            with path.open(encoding="utf-8", errors="replace") as handle:
                for number, line in enumerate(handle, 1):
                    totals["lines"] += 1
                    try:
                        record = json.loads(line)
                    except ValueError:
                        totals["malformed_lines"] += 1
                        continue
                    if not isinstance(record, dict):
                        continue
                    kind = record.get("type")
                    if record.get("sessionId"):
                        provider = "claude"
                    payload = record.get("payload")
                    payload = payload if isinstance(payload, dict) else {}
                    shapes[f"record/{kind}/{payload.get('type', '')}/{record.get('subtype', '')}"] += 1
                    if kind == "session_meta":
                        provider = "codex"
                        if isinstance(payload.get("source"), dict):
                            totals["codex_subagent_metadata_records"] += 1
                            interactive = False
                        if payload.get("source") == "exec" or payload.get("thread_source") == "subagent":
                            interactive = False
                    uuid = record.get("uuid")
                    attachment = record.get("attachment") or {}
                    if kind == "attachment" and isinstance(attachment, dict):
                        shapes[f"claude/attachment/{attachment.get('type')}"] += 1
                        if attachment.get("type") == "queued_command":
                            uuid = attachment.get("source_uuid") or uuid
                            if attachment.get("origin", {}).get("kind") == "human" and uuid not in seen_uuids:
                                expected_dialogue_lines.add(number)
                    duplicate = uuid is not None and uuid in seen_uuids
                    if uuid is not None:
                        seen_uuids.add(uuid)
                    if kind in {"user", "assistant"}:
                        provider = "claude"
                        content = record.get("message", {}).get("content")
                        human = record.get("origin", {}).get("kind") == "human"
                        visible = not duplicate and (not record.get("isMeta") or human)
                        shapes[f"claude/{kind}/content/{type(content).__name__}/meta/{bool(record.get('isMeta'))}"] += 1
                        if visible and isinstance(content, str) and content.startswith("<command-name>"):
                            expected_dialogue_lines.add(number)
                        if visible and (human or kind == "assistant") and isinstance(content, str) and content.strip():
                            expected_dialogue_lines.add(number)
                        if isinstance(content, list):
                            for block in content:
                                if not isinstance(block, dict):
                                    continue
                                shapes[f"claude/{kind}/block/{block.get('type')}"] += 1
                                if visible and (human or kind == "assistant") and block.get("type") == "text" and block.get("text"):
                                    expected_dialogue_lines.add(number)
                                if block.get("type") == "tool_use":
                                    name = block.get("name", "")
                                    tool_names[f"claude/{name}"] += 1
                                    if visible and name in DIALOGUE_TOOLS:
                                        expected_dialogue_lines.add(number)
                                if visible and block.get("type") in {"tool_use", "tool_result"}:
                                    expected_tool_lines[number] += 1
                    if kind == "response_item":
                        provider = "codex"
                        if payload.get("type") in CODEX_TOOL_CALLS | CODEX_TOOL_RESULTS:
                            expected_tool_lines[number] += 1
                        if payload.get("type") in {"function_call", "custom_tool_call"}:
                            name = payload.get("name", "")
                            tool_names[f"codex/{name}"] += 1
                            if name.split(".")[-1] in DIALOGUE_TOOLS:
                                expected_dialogue_lines.add(number)
                        for block in payload.get("content") or []:
                            if isinstance(block, dict):
                                shapes[f"codex/{payload.get('role')}/block/{block.get('type')}"] += 1
                    if kind == "event_msg" and payload.get("type") == "item_completed":
                        shapes[f"codex/item/{payload.get('item', {}).get('type')}"] += 1
            totals[f"{provider}_files"] += 1
            if "subagents" in path.parts:
                totals["claude_subagent_files"] += 1
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ExportWarning)
                try:
                    messages, tool_lines, tool_roles = _check_exports(path)
                    detailed_roles.update({f"{provider}/{role}": count for role, count in tool_roles.items()})
                    exported_lines = set()
                    for message in messages:
                        roles[f"{provider}/{message.role}"] += 1
                        exported_lines.add(message.line)
                    missing = sorted(expected_dialogue_lines - exported_lines)
                    if missing:
                        problems.append({"file": str(path), "missing_dialogue_lines": missing})
                    if missing_tools := expected_tool_lines - tool_lines:
                        problems.append({"file": str(path), "missing_tool_lines": dict(missing_tools)})
                    if interactive:
                        main_paths.append(path)
                except (SessionError, OSError) as exc:
                    problems.append({"file": str(path), "error": str(exc)})
            for warning in dict.fromkeys(str(w.message) for w in caught):
                problems.append({"file": str(path), "warning": warning})
    joined_sources = set()
    for path in main_paths:
        if str(path) in joined_sources:
            continue
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ExportWarning)
            try:
                messages, _, _ = _check_exports(path, joined=True)
                joined_sources.update(message.source for message in messages if message.source)
                totals["joined_conversations_checked"] += 1
            except (SessionError, OSError) as exc:
                problems.append({"file": str(path), "mode": "joined", "error": str(exc)})
        for warning in dict.fromkeys(str(w.message) for w in caught):
            problems.append({"file": str(path), "mode": "joined", "warning": warning})
    totals["joined_source_files"] = len(joined_sources)
    return {
        "days": days,
        "selection": "file modification time; entire selected files inspected",
        "seconds": round(time.monotonic() - started, 3),
        "totals": dict(totals),
        "shapes": dict(sorted(shapes.items())),
        "tools": dict(sorted(tool_names.items())),
        "exported_roles": dict(roles),
        "detailed_tool_roles": dict(detailed_roles),
        "problems": problems,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=float, default=7)
    parser.add_argument("roots", nargs="*", type=Path, default=[Path.home() / ".claude/projects", Path.home() / ".codex/sessions"])
    args = parser.parse_args()
    report = audit(args.roots, args.days)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report["problems"] else 0)
