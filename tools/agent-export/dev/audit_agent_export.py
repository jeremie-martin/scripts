"""Inventory recently modified logs without printing conversation content.

Run from the repository: uv run --project tools/agent-export python tools/agent-export/dev/audit_agent_export.py --days 7
Files are selected by modification time; their entire history is inspected.
The output is aggregate JSON plus file/line locations of completeness warnings.
This is a structural audit, not a proof of semantic completeness.
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from collections import Counter
from pathlib import Path

from scripts_agent_export import DIALOGUE_TOOLS, ExportWarning, SessionError, messages_from


def audit(roots: list[Path], days: float) -> dict:
    cutoff = time.time() - days * 86400
    totals: Counter[str] = Counter()
    shapes: Counter[str] = Counter()
    tool_names: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    problems = []
    started = time.monotonic()
    for root in roots:
        for path in sorted(root.expanduser().rglob("*.jsonl")):
            if path.stat().st_mtime < cutoff:
                continue
            totals["files"] += 1
            totals["bytes"] += path.stat().st_size
            expected_dialogue_lines = set()
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
                    payload = record.get("payload") or {}
                    shapes[f"record/{kind}/{payload.get('type', '')}/{record.get('subtype', '')}"] += 1
                    if kind == "session_meta":
                        provider = "codex"
                        if isinstance(payload.get("source"), dict):
                            totals["codex_subagent_metadata_records"] += 1
                    if kind in {"user", "assistant"}:
                        provider = "claude"
                        content = record.get("message", {}).get("content")
                        shapes[f"claude/{kind}/content/{type(content).__name__}/meta/{bool(record.get('isMeta'))}"] += 1
                        if isinstance(content, str) and content.startswith("<command-name>"):
                            expected_dialogue_lines.add(number)
                        if isinstance(content, list):
                            for block in content:
                                if not isinstance(block, dict):
                                    continue
                                shapes[f"claude/{kind}/block/{block.get('type')}"] += 1
                                if block.get("type") == "tool_use":
                                    name = block.get("name", "")
                                    tool_names[f"claude/{name}"] += 1
                                    if name in DIALOGUE_TOOLS:
                                        expected_dialogue_lines.add(number)
                    if kind == "response_item":
                        provider = "codex"
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
                    exported_lines = set()
                    for message in messages_from(path):
                        roles[f"{provider}/{message.role}"] += 1
                        exported_lines.add(message.line)
                    missing = sorted(expected_dialogue_lines - exported_lines)
                    if missing:
                        problems.append({"file": str(path), "missing_dialogue_lines": missing})
                except (SessionError, OSError) as exc:
                    problems.append({"file": str(path), "error": str(exc)})
            for warning in dict.fromkeys(str(w.message) for w in caught):
                problems.append({"file": str(path), "warning": warning})
    return {
        "days": days,
        "selection": "file modification time; entire selected files inspected",
        "seconds": round(time.monotonic() - started, 3),
        "totals": dict(totals),
        "shapes": dict(sorted(shapes.items())),
        "tools": dict(sorted(tool_names.items())),
        "exported_roles": dict(roles),
        "problems": problems,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=float, default=7)
    parser.add_argument("roots", nargs="*", type=Path, default=[Path.home() / ".claude/projects", Path.home() / ".codex/sessions"])
    args = parser.parse_args()
    print(json.dumps(audit(args.roots, args.days), ensure_ascii=False, indent=2))
