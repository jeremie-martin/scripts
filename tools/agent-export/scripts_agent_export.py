"""Export Claude and Codex conversations, optionally including recorded tool details.

Both log formats become a shared stream of messages, activity, and model changes.
Model reasoning, injected context, and bookkeeping records remain omitted.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import unicodedata
import warnings
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from itertools import islice
from pathlib import Path
from typing import Annotated, Literal

import typer


class SessionFormat(StrEnum):
    """The session log formats understood by the exporter."""

    CLAUDE = "claude"
    CODEX = "codex"


Role = Literal["USER", "AGENT", "SUMMARY", "NOTICE", "TOOL_CALL", "TOOL_RESULT"]
Record = dict[str, object]


@dataclass(frozen=True, slots=True)
class Message:
    """A visible conversation message."""

    role: Role
    text: str
    source: str = field(default="", compare=False)
    line: int | None = field(default=None, compare=False)
    timestamp: str | None = field(default=None, compare=False)


@dataclass(frozen=True, slots=True)
class ToolUse:
    """One tool invocation, reduced to what a per-turn activity line needs."""

    kind: Literal["command", "edit", "web", "agent", "other"]
    name: str
    files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelChange:
    """The model and reasoning effort in effect from this point of the log."""

    model: str
    effort: str | None = None


Entry = Message | ToolUse | ModelChange


class SessionError(ValueError):
    """A user-facing problem with a session source or its format."""


class ExportWarning(UserWarning):
    """A limitation that may affect the completeness of an export."""


DEFAULT_SESSION_ROOTS = (Path.home() / ".claude", Path.home() / ".codex")

# Codex stores injected setup context as a user-role response item. Claude
# stores command/task plumbing as user records too. These prefixes are not
# conversation and must never leak into an export.
INTERNAL_PREFIXES = (
    "<apps_instructions>",
    "<collaboration_mode>",
    "<developer>",
    "<environment_context>",
    "<local-command-caveat>",
    "<multi_agent_mode>",
    "<permissions instructions>",
    "<plugins_instructions>",
    "<skills_instructions>",
    "<system>",
    "<task-notification>",
)


def _rewrite_key(line: str) -> tuple[str, str] | None:
    """Identify a Codex record by ordinal and item ID, even when the line is truncated."""

    ordinal = re.search(r'"ordinal":(\d+)', line)
    item = re.search(r'"payload":\{[^{}]*?"id":"([^"]+)"', line)
    return (ordinal[1], item[1]) if ordinal and item else None


def _records(path: Path) -> Iterator[Record]:
    """Yield valid JSON objects from a JSONL file, ignoring broken lines.

    Codex sometimes leaves a partial write behind and then writes the same record
    in full. Such a fragment loses nothing, so it is skipped without a warning.
    """

    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SessionError(f"Could not read session file {path}: {exc}") from exc

    fragments: dict[tuple[str, str], str] = {}
    complete: set[tuple[str, str]] = set()
    with handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                message = f"{path}:{number}: invalid JSON record skipped"
                key = _rewrite_key(line)
                if key is None:
                    warnings.warn(message, ExportWarning, stacklevel=2)
                elif key not in complete:
                    fragments[key] = message
                continue
            if isinstance(record, dict):
                if "ordinal" in record:
                    key = (str(record["ordinal"]), str(_mapping(record.get("payload")).get("id")))
                    complete.add(key)
                    fragments.pop(key, None)
                record["_line"] = number
                yield record
            else:
                warnings.warn(f"{path}:{number}: non-object record skipped", ExportWarning, stacklevel=2)
    for message in fragments.values():
        warnings.warn(message, ExportWarning, stacklevel=2)


def _mapping(value: object) -> Record:
    return value if isinstance(value, dict) else {}


def _text_parts(content: object, expected_type: str) -> list[str]:
    """Extract only text blocks of one known, visible content type."""

    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []

    return [
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == expected_type and isinstance(block.get("text"), str)
    ]


def _message(role: Role, texts: Iterable[str]) -> Message | None:
    text = "\n\n".join(part.strip() for part in texts if part.strip())
    return Message(role, text) if text else None


def _is_internal(text: str) -> bool:
    return text.lstrip().startswith(INTERNAL_PREFIXES)


QUESTION_TOOLS = {"AskUserQuestion", "request_user_input", "request_user_input_async"}
DIALOGUE_TOOLS = QUESTION_TOOLS | {"ExitPlanMode", "SendUserFile"}
SUMMARY_PREFIX = "This session is being continued from a previous conversation"


def _decoded(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def _display(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def _located(message: Message, record: Record, path: Path) -> Message:
    return replace(message, source=str(path), line=record.get("_line"), timestamp=record.get("timestamp"))


def _visible_parts(content: object, *, user: bool = False, human: bool = False) -> Iterator[str]:
    """Keep text and attachment references, never embedded binary data."""
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
    if not isinstance(blocks, list):
        return
    for block in blocks:
        if not isinstance(block, dict):
            warnings.warn("Unsupported message block", ExportWarning, stacklevel=2)
            yield "[Unsupported message block; see source log]"
            continue
        kind = block.get("type")
        if kind in {"thinking", "redacted_thinking", "reasoning", "tool_use", "tool_result"}:
            continue
        if kind in {"text", "Text", "input_text", "output_text"}:
            text = block.get("text", "")
            if not isinstance(text, str):
                continue
            if user and not human and _is_internal(text):
                # A setup block may share a message with an actual prompt.
                # Strip only complete leading setup wrappers, not the whole message.
                while _is_internal(text):
                    prefix = next(p for p in INTERNAL_PREFIXES if text.lstrip().startswith(p))
                    end = "</" + prefix[1:]
                    if end not in text:
                        text = ""
                        break
                    text = text.split(end, 1)[1].lstrip()
            if text.strip():
                yield text
        elif kind in {
            "image",
            "input_image",
            "output_image",
            "local_image",
            "document",
            "file",
            "input_file",
            "audio",
            "input_audio",
            "output_audio",
        }:
            source = _mapping(block.get("source"))
            reference = (
                block.get("path")
                or block.get("filename")
                or block.get("file_id")
                or block.get("image_url")
                or block.get("url")
                or source.get("url")
            )
            if isinstance(reference, dict):
                reference = reference.get("url")
            if not isinstance(reference, str) or reference.startswith("data:"):
                reference = "embedded attachment; see source log"
            yield f"[{kind}: {reference}]"
        else:
            warnings.warn(f"Unsupported conversation block: {kind}", ExportWarning, stacklevel=2)
            if isinstance(block.get("text"), str):
                yield block["text"]
            yield f"[Unsupported {kind} block; see source log]"


def _questions(data: Record) -> str:
    parts = []
    for question in data.get("questions", []):
        if not isinstance(question, dict):
            parts.append(_display(question))
            continue
        parts.append(str(question.get("question") or question.get("title") or question.get("header") or "Question"))
        for option in question.get("options", []):
            if isinstance(option, dict):
                label = str(option.get("label", ""))
                description = option.get("description")
                parts.append(f"- {label}" + (f": {description}" if description else ""))
            else:
                parts.append(f"- {option}")
    return "\n".join(parts) or _display(data)


def _dialogue_call(name: str, data: Record) -> Message:
    if name in QUESTION_TOOLS:
        return Message("AGENT", _questions(data))
    if name == "SendUserFile":
        files = "\n".join(f"[file: {path}]" for path in data.get("files", []))
        return Message("AGENT", "\n\n".join(part for part in [str(data.get("caption", "")), files] if part))
    return Message("AGENT", "Proposed plan:\n\n" + str(data.get("plan") or "[Plan approval requested; plan text absent from this call]"))


def _dialogue_result(name: str, arguments: Record, result: object) -> Message | None:
    if name == "SendUserFile":
        return None
    decoded = _decoded(result)
    data = _mapping(decoded)
    answers = data.get("answers")
    if isinstance(answers, dict):
        labels = {
            q.get("id"): q.get("question") or q.get("title") or q.get("id")
            for q in arguments.get("questions", [])
            if isinstance(q, dict) and q.get("id")
        }
        parts = []
        for key, value in answers.items():
            if isinstance(value, dict) and "answers" in value:
                value = value["answers"]
            answer = "; ".join(map(str, value)) if isinstance(value, list) else _display(value)
            parts.append(f"{labels.get(key, key)}\n{answer}")
        return Message("USER", "\n\n".join(parts)) if parts else Message("NOTICE", "No answers were submitted.")
    if name == "request_user_input_async" and data == {"accepted": True}:
        return None  # Delivery acknowledgement, not the user's answer.
    text = "\n\n".join(_text_parts(decoded, "text")) if isinstance(decoded, list) else _display(decoded)
    if name == "ExitPlanMode":
        # Claude's structured result contains the approved plan, not an answer field.
        if data.get("plan") and data.get("isAgent") is False:
            return Message("USER", "Approved the plan.")
        if text.startswith("User has approved your plan"):
            return Message("USER", "Approved the plan.")
    # Preserve refusals, cancellations, free text, and unfamiliar result shapes.
    return Message("NOTICE", f"{name} result:\n{text}")


COMMAND_TOOLS = {"Bash", "PowerShell", "exec_command", "shell", "local_shell_call"}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch"}
WEB_TOOLS = {"WebFetch", "WebSearch", "web__run", "web_search", "web_search_call"}
AGENT_TOOLS = {"Agent", "Task", "spawn_agent"}
# Reading, waiting, and bookkeeping calls say little about what a turn did.
QUIET_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "LS",
    "TodoWrite",
    "ToolSearch",
    "TaskOutput",
    "TaskStop",
    "Monitor",
    "SendMessage",
    "ScheduleWakeup",
    "view_image",
    "write_stdin",
    "wait",
    "sleep",
    "clock__curr_time",
    "update_plan",
    "get_goal",
    "update_goal",
    "list_agents",
    "send_message",
    "followup_task",
    "wait_agent",
    "multi_agent_v1__send_input",
    "multi_agent_v1__wait_agent",
    "exec",
    "combinations",
    "permutations",
}


def _patch_files(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"\*\*\* (?:Add|Update|Delete) File: ([^\n\"\\]+)", text)))


def _tool_use(name: str, files: tuple[str, ...] = ()) -> ToolUse | None:
    if name in QUIET_TOOLS or name in DIALOGUE_TOOLS:
        return None
    if name in COMMAND_TOOLS:
        return ToolUse("command", name)
    if name in EDIT_TOOLS:
        return ToolUse("edit", name, files)
    if name in WEB_TOOLS:
        return ToolUse("web", name)
    if name in AGENT_TOOLS:
        return ToolUse("agent", name)
    return ToolUse("other", name)


def _claude_tool_use(block: Record) -> ToolUse | None:
    arguments = _mapping(block.get("input"))
    path = arguments.get("file_path") or arguments.get("notebook_path")
    return _tool_use(str(block.get("name", "")), (path,) if isinstance(path, str) else ())


def _codex_tool_uses(payload: Record) -> Iterator[ToolUse]:
    kind = payload.get("type")
    if kind == "local_shell_call":
        yield ToolUse("command", "local_shell_call")
    elif kind == "web_search_call":
        yield ToolUse("web", "web_search_call")
    elif kind in {"function_call", "custom_tool_call"}:
        name = str(payload.get("name", "")).split(".")[-1]
        code = str(payload.get("input") or payload.get("arguments") or "")
        # Codex's exec tool runs a script that may call several tools.
        names = re.findall(r"\btools\.(\w+)\s*\(", code) if name == "exec" else [name]
        files = _patch_files(code)
        for called in names:
            use = _tool_use(called, files if called == "apply_patch" else ())
            if use:
                if use.files:
                    files = ()  # One exec's patches are reported once.
                yield use


CODEX_TOOL_CALLS = {"function_call", "custom_tool_call", "local_shell_call", "web_search_call"}
CODEX_TOOL_RESULTS = {"function_call_output", "custom_tool_call_output", "local_shell_call_output"}
TOOL_ROLES = {"TOOL_CALL", "TOOL_RESULT"}


def _tool_payload(value: object) -> object:
    """Retain tool data while replacing structured binary attachments with references."""
    if isinstance(value, list):
        return [_tool_payload(item) for item in value]
    if isinstance(value, dict):
        if isinstance(value.get("type"), str) and value["type"] in {
            "image", "input_image", "output_image", "document", "file", "input_file",
            "audio", "input_audio", "output_audio",
        }:
            return "\n".join(_visible_parts([value]))
        return {key: _tool_payload(item) for key, item in value.items()}
    return value


def _tool_message(payload: Record, *, result: bool = False) -> Message:
    return Message("TOOL_RESULT" if result else "TOOL_CALL", json.dumps(_tool_payload(payload), ensure_ascii=False, indent=2))


def _claude_record(record: Record, calls: dict[str, tuple[str, Record]], *, include_tools: bool = False) -> Iterator[Entry]:
    kind = record.get("type")
    if kind == "system" and record.get("subtype") == "away_summary":
        yield Message("SUMMARY", str(record.get("content", "")))
        return
    if kind not in {"user", "assistant"}:
        if kind not in {"system", "attachment"} and isinstance(record.get("message"), dict):
            warnings.warn(f"Unknown Claude conversation record: {kind}", ExportWarning, stacklevel=2)
            text = "\n\n".join(_visible_parts(_mapping(record["message"]).get("content")))
            yield Message("NOTICE", f"Unrecognized {kind} message:\n{text}")
        return
    content = _mapping(record.get("message")).get("content")
    human = _mapping(record.get("origin")).get("kind") == "human"
    if record.get("isMeta") and not human:
        return
    model = _mapping(record.get("message")).get("model")
    if kind == "assistant" and isinstance(model, str) and model != "<synthetic>":
        effort = record.get("effort")
        yield ModelChange(model, effort if isinstance(effort, str) else None)
    if kind == "user" and _mapping(record.get("origin")).get("kind") == "task-notification":
        return
    if isinstance(content, str) and content.lstrip().startswith("<command-name>"):
        command = re.search(r"<command-name>(.*?)</command-name>", content, re.S)
        args = re.search(r"<command-args>(.*?)</command-args>", content, re.S)
        if command:
            yield Message("USER", command[1].strip() + ("\n\n" + args[1].strip() if args and args[1].strip() else ""))
        else:
            yield Message("USER", content)
        return
    if isinstance(content, str) and content.lstrip().startswith("<local-command-"):
        text = re.sub(r"</?local-command-[^>]+>", "", content).strip()
        if text:
            yield Message("NOTICE", text)
        return
    role: Role = "USER" if kind == "user" else "AGENT"
    if (record.get("isCompactSummary") or (isinstance(content, str) and content.startswith(SUMMARY_PREFIX))) and not human:
        role = "SUMMARY"
    # Preserve block order, including questions interspersed with prose.
    blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            if include_tools:
                yield _tool_message(block)
            name = str(block.get("name", ""))
            args = _mapping(block.get("input"))
            if name in DIALOGUE_TOOLS:
                calls[str(block.get("id"))] = (name, args)
                yield _dialogue_call(name, args)
            elif use := _claude_tool_use(block):
                yield use
        elif isinstance(block, dict) and block.get("type") == "tool_result":
            if include_tools:
                yield _tool_message(block, result=True)
            call = calls.get(str(block.get("tool_use_id")))
            result = record.get("toolUseResult")
            if call:
                visible = _dialogue_result(*call, result if isinstance(result, dict) else block.get("content"))
                if visible:
                    yield visible
            elif isinstance(result, dict) and "answers" in result:
                visible = _dialogue_result("AskUserQuestion", result, result)
                if visible:
                    yield visible
            elif isinstance(result, dict) and result.get("plan") and result.get("isAgent") is False:
                yield Message("AGENT", "Approved plan:\n\n" + str(result["plan"]))
                yield Message("USER", "Approved the plan.")
        else:
            visible = _message(role, _visible_parts([block], user=kind == "user", human=human))
            if visible:
                yield visible


def _claude_entries(path: Path, seen: set[str] | None = None, *, include_tools: bool = False) -> Iterator[Entry]:
    calls: dict[str, tuple[str, Record]] = {}
    seen = seen if seen is not None else set()
    for record in _records(path):
        uuid = record.get("uuid")
        duplicate = isinstance(uuid, str) and uuid in seen
        if isinstance(uuid, str):
            seen.add(uuid)
        # Even copied calls must populate the result lookup for this session.
        messages = list(_claude_record(record, calls, include_tools=include_tools))
        if not duplicate:
            for entry in messages:
                yield _located(entry, record, path) if isinstance(entry, Message) else entry


def _codex_message(payload: Record) -> Message | None:
    role = payload.get("role")
    if role not in {"user", "assistant"} or payload.get("phase") == "analysis" or payload.get("channel") == "analysis":
        return None
    message = _message("USER" if role == "user" else "AGENT", _visible_parts(payload.get("content"), user=role == "user"))
    if message and role == "assistant":
        plan = re.fullmatch(r"\s*<proposed_plan>\s*(.*?)\s*</proposed_plan>\s*", message.text, re.S)
        if plan:
            message = replace(message, text=plan[1])
    return message


def _codex_representation(record: Record) -> tuple[int, Message] | None:
    payload = _mapping(record.get("payload"))
    kind = payload.get("type")
    message = None
    lane = 0
    if record.get("type") == "response_item" and kind == "message":
        message = _codex_message(payload)
    elif record.get("type") == "event_msg":
        lane = 1
        if kind in {"user_message", "agent_message"}:
            message = _codex_message(
                {
                    "role": "user" if kind == "user_message" else "assistant",
                    "phase": payload.get("phase"),
                    "content": payload.get("message"),
                }
            )
            if kind == "user_message":
                attachments = [f"[local_image: {p}]" for p in payload.get("local_images", [])]
                attachments += ["[input_image: embedded attachment; see source log]" for _ in payload.get("images", [])]
                attachments += [f"[audio: {p}]" for p in payload.get("local_audio", [])]
                if attachments:
                    message = _message("USER", ([message.text] if message else []) + attachments)
        elif kind == "item_completed":
            lane = 2
            item = _mapping(payload.get("item"))
            if item.get("type") in {"UserMessage", "AgentMessage"}:
                message = _codex_message({**item, "role": "user" if item["type"] == "UserMessage" else "assistant"})
            elif item.get("type") == "Plan":
                message = _message("AGENT", [str(item.get("text", ""))])
            elif item.get("type") == "ExitedReviewMode":
                message = _message("AGENT", [_display(item.get("review_output"))])
        elif kind == "task_complete" and payload.get("last_agent_message"):
            lane = 3
            message = _message("AGENT", [str(payload["last_agent_message"])])
    return (lane, message) if message else None


def _message_key(message: Message) -> tuple[str, str]:
    # Mirror events omit binary attachments. Their textual portion still pairs.
    text = re.sub(
        r"\[(?:input_image|output_image|local_image|image|audio|input_audio|output_audio|document|file|input_file): [^\n]*\]",
        "",
        message.text,
    )
    return message.role, text.strip()


def _codex_records(paths: Sequence[Path]) -> Iterator[tuple[str, Path, Record]]:
    scope = "initial"
    for path in paths:
        for record in _records(path):
            payload = _mapping(record.get("payload"))
            if record.get("type") == "event_msg" and payload.get("type") == "task_started":
                scope = str(payload.get("turn_id") or f"{path}:{record['_line']}")
            elif record.get("type") == "turn_context" and payload.get("turn_id"):
                scope = str(payload["turn_id"])
            yield scope, path, record


def _contains_executable_question(code: str) -> bool:
    # Best-effort detection only. Do not mistake quoted source code or comments
    # (e.g. editing this exporter) for a live question invocation.
    code = re.sub(r"""(?s)//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`""", "", code)
    return bool(re.search(r"(?:tools|functions)\.request_user_input(?:_async)?\s*\(", code))


def _codex_entries(path: Path, *, paths: Sequence[Path] | None = None, include_tools: bool = False) -> Iterator[Entry]:
    # Event and response messages are two representations of the same exchange.
    # Match occurrence counts, not a text set: repeated real messages must survive.
    paths = paths or [path]
    counts: list[Counter[tuple[str, str, str]]] = [Counter() for _ in range(4)]
    def result_key(scope: str, payload: Record) -> tuple[str, str, str, str]:
        return scope, str(payload.get("type")), str(payload.get("call_id")), json.dumps(payload.get("output"), sort_keys=True)

    tool_counts: Counter[tuple[str, str, str, str]] = Counter()
    for scope, _, record in _codex_records(paths):
        payload = _mapping(record.get("payload"))
        if include_tools and record.get("type") == "response_item" and payload.get("type") in CODEX_TOOL_RESULTS:
            tool_counts[result_key(scope, payload)] += 1
        representation = _codex_representation(record)
        if representation:
            lane, message = representation
            counts[lane][scope, *_message_key(message)] += 1
    occurrences: list[Counter[tuple[str, str, str]]] = [Counter() for _ in range(4)]
    history: Counter[Message] = Counter()
    calls: dict[str, tuple[str, Record]] = {}
    for scope, path, record in _codex_records(paths):
        payload = _mapping(record.get("payload"))
        kind = payload.get("type")
        if record.get("type") == "session_meta" and len(paths) > 1:
            text = f"Session log: {path.name}"
            boundary = _mapping(payload.get("history_base")).get("end_ordinal_exclusive")
            if boundary is not None:
                text += f". Resumed from history before record {boundary}; earlier exchanges retained above."
            yield _located(Message("NOTICE", text), record, path)
        if record.get("type") == "turn_context" and isinstance(payload.get("model"), str):
            effort = payload.get("effort")
            yield ModelChange(payload["model"], effort if isinstance(effort, str) else None)
        elif record.get("type") == "response_item":
            yield from _codex_tool_uses(payload)
        if include_tools:
            if record.get("type") == "response_item" and kind in CODEX_TOOL_CALLS | CODEX_TOOL_RESULTS:
                yield _located(_tool_message(payload, result=kind in CODEX_TOOL_RESULTS), record, path)
            elif record.get("type") == "event_msg" and kind in CODEX_TOOL_RESULTS:
                # Some versions store results as events, others also mirror them there.
                key = result_key(scope, payload)
                if tool_counts[key]:
                    tool_counts[key] -= 1
                else:
                    yield _located(_tool_message(payload, result=True), record, path)
        visible = None
        representation = _codex_representation(record)
        if representation:
            lane, visible = representation
            key = (scope, *_message_key(visible))
            occurrences[lane][key] += 1
            if any(counts[higher][key] >= occurrences[lane][key] for higher in range(lane)):
                visible = None
        elif record.get("type") == "response_item":
            if kind == "function_call":
                name = str(payload.get("name", "")).split(".")[-1]
                if name in QUESTION_TOOLS:
                    args = _mapping(_decoded(payload.get("arguments")))
                    calls[str(payload.get("call_id"))] = (name, args)
                    visible = _dialogue_call(name, args)
            elif kind == "function_call_output" and str(payload.get("call_id")) in calls:
                visible = _dialogue_result(*calls[str(payload.get("call_id"))], payload.get("output"))
            elif kind == "custom_tool_call" and _contains_executable_question(str(payload.get("input", ""))):
                warnings.warn(
                    f"{path}:{record['_line']}: question inside executable tool code cannot be decoded", ExportWarning, stacklevel=2
                )
            elif kind not in {
                "message",
                "reasoning",
                "agent_message",
                "function_call",
                "function_call_output",
                "custom_tool_call",
                "custom_tool_call_output",
                "web_search_call",
                "compaction",
                "local_shell_call",
                "local_shell_call_output",
            }:
                warnings.warn(f"{path}:{record['_line']}: unknown Codex response type: {kind}", ExportWarning, stacklevel=2)
                visible = Message("NOTICE", f"[Unsupported {kind} response; see source log]")
        elif record.get("type") == "event_msg":
            if kind == "turn_aborted":
                visible = Message("NOTICE", "Turn interrupted: " + str(payload.get("reason", "unspecified")))
            elif kind == "thread_rolled_back":
                visible = Message(
                    "NOTICE", f"Conversation rolled back ({payload.get('num_turns', '?')} turns); earlier exchanges retained above."
                )
            elif kind not in {"user_message", "agent_message"} and isinstance(payload.get("message"), str):
                warnings.warn(f"{path}:{record['_line']}: unknown message event: {kind}", ExportWarning, stacklevel=2)
                visible = Message("NOTICE", f"{kind}:\n{payload['message']}")
        elif record.get("type") == "compacted":
            # Recover readable history when the source only retained a compacted
            # snapshot. Count occurrences within each snapshot to avoid replaying it.
            snapshot: Counter[Message] = Counter()
            for item in payload.get("replacement_history") or []:
                if not isinstance(item, dict) or item.get("type") != "message":
                    continue
                recovered = _codex_message(item)
                if recovered:
                    snapshot[recovered] += 1
                    if snapshot[recovered] > history[recovered]:
                        yield _located(Message("NOTICE", "Following message recovered from compaction history."), record, path)
                        yield _located(recovered, record, path)
            history |= snapshot
            summary = payload.get("message")
            visible = (
                Message("SUMMARY", summary)
                if isinstance(summary, str) and summary
                else Message("NOTICE", "Context compacted. No readable summary is stored in this record; earlier exchanges are retained.")
            )
        if visible:
            history[visible] += 1
            yield _located(visible, record, path)


def _record_formats(record: Record) -> set[SessionFormat]:
    record_type = record.get("type")
    if record_type == "session_meta":
        payload = _mapping(record.get("payload"))
        if str(payload.get("originator", "")).startswith("codex"):
            return {SessionFormat.CODEX}
    if record_type == "response_item":
        return {SessionFormat.CODEX}
    if record_type in {"compacted", "event_msg"}:
        return {SessionFormat.CODEX}
    if record_type in {"ai-title", "continued-in", "agent-name"}:
        return {SessionFormat.CLAUDE}
    if record_type in {"mode", "permission-mode", "bridge-session", "cost-state"} and record.get("sessionId"):
        return {SessionFormat.CLAUDE}
    if record_type in {"user", "assistant"} and isinstance(record.get("message"), dict):
        return {SessionFormat.CLAUDE}
    return set()


def detect_session_format(path: Path) -> SessionFormat:
    """Detect the format from structural records, not filename guesses."""

    formats: set[SessionFormat] = set()
    for record in _records(path):
        formats.update(_record_formats(record))
        if len(formats) > 1:
            raise SessionError(f"Session contains conflicting formats: {path}")

    if formats:
        return formats.pop()
    raise SessionError(f"Could not recognize session format: {path}")


def _record_session_ids(record: Record) -> set[str]:
    ids: set[str] = set()
    for key in ("sessionId", "session_id"):
        value = record.get(key)
        if isinstance(value, str):
            ids.add(value)

    payload = _mapping(record.get("payload"))
    for key in ("sessionId", "session_id", "id"):
        value = payload.get(key)
        if isinstance(value, str):
            ids.add(value)
    return ids


def _filename_matches(path: Path, session_id: str) -> bool:
    stem = path.stem
    return (
        stem == session_id
        or stem.endswith(f"-{session_id}")
        or (stem.startswith("rollout-") and stem.rsplit("_", 1)[0].endswith(f"-{session_id}"))
    )


def _codex_meta(path: Path) -> Record:
    """Read only the rollout header when discovering related log files."""
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            record = _json_object(handle.readline())
    except OSError:
        return {}
    return _mapping(record.get("payload")) if record.get("type") == "session_meta" else {}


def _codex_id(meta: Record) -> str | None:
    value = meta.get("id") or meta.get("session_id")
    return value if isinstance(value, str) else None


def _codex_segment_order(paths: Sequence[Path], session_id: str) -> list[Path] | None:
    """Accept one thread's base log and explicitly linked resumes, never another fork."""
    headers = [(path, _codex_meta(path)) for path in paths]
    if any(_codex_id(meta) != session_id for _, meta in headers):
        return None
    bases = [(path, meta) for path, meta in headers if not meta.get("history_base")]
    if len(bases) > 1:
        return None
    resumes = [(path, meta) for path, meta in headers if meta.get("history_base")]
    if any(_mapping(meta.get("history_base")).get("thread_id") != session_id for _, meta in resumes):
        return None
    resumes.sort(key=lambda pair: (str(pair[1].get("timestamp", "")), str(pair[0])))
    return [path for path, _ in [*bases, *resumes]]


def codex_continuation_paths(path: Path) -> list[Path]:
    """Find explicit resumes of the same Codex thread across dated log directories."""
    meta = _codex_meta(path)
    session_id = _codex_id(meta)
    if not session_id:
        return [path]
    # A copied rollout can still find its siblings; installed logs span dates and
    # may have moved between sessions/ and archived_sessions/.
    root = next((p for p in path.parents if p.name in {"sessions", "archived_sessions"}), path.parent)
    roots = [root]
    if root.name in {"sessions", "archived_sessions"}:
        roots = [root.parent / "sessions", root.parent / "archived_sessions"]
    candidates = [path]
    for directory in roots:
        for candidate in directory.rglob("*.jsonl"):
            if _filename_matches(candidate, session_id) and _codex_id(_codex_meta(candidate)) == session_id:
                candidates.append(candidate)
    paths = _codex_segment_order(_unique_resolved(candidates), session_id)
    if paths is None:
        if len(_unique_resolved(candidates)) > 1:
            raise SessionError("Ambiguous Codex continuation files; use --single-session to export one file.")
        paths = [path]
    base = _mapping(_codex_meta(paths[0]).get("history_base"))
    if base:
        warnings.warn(
            f"{paths[0]}: linked Codex history is missing (thread {base.get('thread_id')})", ExportWarning, stacklevel=2
        )
    return paths


def _candidate_matches(path: Path, session_id: str) -> bool:
    if _filename_matches(path, session_id):
        return True

    # This is primarily for Claude layouts whose filename is not the session
    # ID. Session metadata is near the beginning, so bounded inspection keeps
    # lookup cheap even with very large transcripts.
    try:
        return any(session_id in _record_session_ids(record) for record in islice(_records(path), 64))
    except SessionError:
        return False


def _unique_resolved(paths: Iterable[Path]) -> list[Path]:
    resolved_paths: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            resolved_paths.append(resolved)
    return resolved_paths


def resolve_session(source: str, roots: Sequence[Path] = DEFAULT_SESSION_ROOTS) -> Path:
    """Resolve a direct file path or a session ID under the known log roots."""

    path = Path(source).expanduser()
    if path.exists():
        if not path.is_file():
            raise SessionError(f"Session source is not a file: {path}")
        return path.resolve()

    candidates: list[Path] = []
    for root in roots:
        root = root.expanduser()
        if not root.is_dir():
            continue
        try:
            candidates.extend(root.rglob("*.jsonl"))
        except OSError:
            continue

    # The normal case (Codex rollouts and current Claude sessions) puts the ID
    # in the filename. Do this cheap pass before opening any transcript: a
    # parent session ID is also copied into many Claude subagent records.
    filename_matches = _unique_resolved(
        candidate for candidate in candidates if candidate.is_file() and _filename_matches(candidate, source)
    )
    if filename_matches:
        matches = filename_matches
    else:
        metadata_matches = _unique_resolved(
            candidate for candidate in candidates if candidate.is_file() and _candidate_matches(candidate, source)
        )
        matches = metadata_matches

    # Subagent logs can copy the parent session ID into their metadata. The
    # canonical file named by that ID is the unambiguous answer when present.
    if not matches:
        searched = ", ".join(str(root.expanduser()) for root in roots)
        raise SessionError(f"Session not found: {source} (searched {searched})")
    if len(matches) > 1:
        if joined := _codex_segment_order(matches, source):
            return joined[0]
        details = "\n".join(f"  {match}" for match in matches)
        raise SessionError(f"Multiple sessions matched {source!r}:\n{details}")
    return matches[0]


def entries_from(path: Path, session_format: SessionFormat | None = None, *, include_tools: bool = False) -> Iterator[Entry]:
    """Yield visible messages, tool uses, and model changes from *path* in source order."""

    session_format = session_format or detect_session_format(path)
    if session_format is SessionFormat.CLAUDE:
        yield from _claude_entries(path, include_tools=include_tools)
    else:
        yield from _codex_entries(path, include_tools=include_tools)


def messages_from(path: Path, session_format: SessionFormat | None = None) -> Iterator[Message]:
    """Yield visible messages from *path* in source order."""

    return (entry for entry in entries_from(path, session_format) if isinstance(entry, Message))


def continuation_paths(path: Path) -> list[Path]:
    """Follow only explicit Claude links, never titles, timestamps, or textual mentions."""
    successors: dict[str, set[str]] = {}
    predecessors: dict[str, set[str]] = {}
    for sibling in path.parent.glob("*.jsonl"):
        # Avoid parsing large tool results merely to discover a rare metadata record.
        try:
            with sibling.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if '"continued-in"' not in line:
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(record, dict) or record.get("type") != "continued-in":
                        continue
                    previous, following = record.get("sessionId"), record.get("continuedInSessionId")
                    if not isinstance(previous, str) or not isinstance(following, str):
                        continue
                    successors.setdefault(previous, set()).add(following)
                    predecessors.setdefault(following, set()).add(previous)
        except OSError as exc:
            warnings.warn(f"Cannot inspect continuation metadata in {sibling}: {exc}", ExportWarning, stacklevel=2)

    def next_id(links: dict[str, set[str]], current: str) -> str | None:
        targets = links.get(current, set())
        if len(targets) > 1:
            raise SessionError("Ambiguous continuation links; use --single-session to export one file.")
        return next(iter(targets), None)

    start = path.stem
    visited = set()
    while start in predecessors:
        if start in visited:
            raise SessionError("Cyclic continuation links; use --single-session.")
        visited.add(start)
        start = next_id(predecessors, start)
    paths = []
    visited.clear()
    while start:
        if start in visited:
            raise SessionError("Cyclic continuation links; use --single-session.")
        visited.add(start)
        if Path(start).name != start or "\\" in start or start in {".", ".."}:
            raise SessionError("Invalid linked session ID; use --single-session.")
        candidate = path if start == path.stem else path.parent / f"{start}.jsonl"
        if candidate.is_file():
            paths.append(candidate)
        else:
            warnings.warn(f"Linked session is missing: {start}", ExportWarning, stacklevel=2)
        start = next_id(successors, start)
    return paths


def conversation_entries(
    path: Path, *, single_session: bool = False, session_format: SessionFormat | None = None, include_tools: bool = False
) -> Iterator[Entry]:
    """Yield the entries of a session, joined with its explicit continuations."""

    session_format = session_format or detect_session_format(path)
    if session_format is SessionFormat.CODEX:
        paths = [path] if single_session else codex_continuation_paths(path)
        yield from _codex_entries(path, paths=paths, include_tools=include_tools)
        return
    paths = [path] if single_session else continuation_paths(path)
    seen: set[str] = set()
    for source in paths:
        if len(paths) > 1:
            yield Message("NOTICE", f"Session {source.stem}", source=str(source))
        yield from _claude_entries(source, seen, include_tools=include_tools)


def conversation_from(path: Path, *, single_session: bool = False) -> Iterator[Message]:
    return (entry for entry in conversation_entries(path, single_session=single_session) if isinstance(entry, Message))


# Session metadata ---------------------------------------------------------

AGENT_NAMES = {SessionFormat.CLAUDE: "Claude Code", SessionFormat.CODEX: "Codex"}
UUID_SUFFIX = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")


@dataclass(slots=True)
class SessionInfo:
    """What identifies a session to a person: where, when, and what it was about."""

    path: Path
    format: SessionFormat
    id: str
    title: str | None = None
    cwd: str | None = None
    branch: str | None = None
    started: datetime | None = None
    updated: datetime | None = None
    first_prompt: str | None = None
    interactive: bool = True


def _json_object(line: str) -> Record:
    try:
        record = json.loads(line)
    except ValueError:
        return {}
    return record if isinstance(record, dict) else {}


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).astimezone()
    except ValueError:
        return None


def _one_line(text: str, limit: int = 80) -> str | None:
    for line in text.splitlines():
        line = " ".join(line.split())
        if line:
            return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"
    return None


def _prompt_line(text: str) -> str | None:
    """A prompt as a one-line label; slash commands read as they were typed."""

    command = re.search(r"<command-name>(.*?)</command-name>", text, re.S)
    if command:
        args = re.search(r"<command-args>(.*?)</command-args>", text, re.S)
        text = command[1].strip() + (" " + args[1].strip() if args and args[1].strip() else "")
    return _one_line(text)


def _claude_info(path: Path) -> SessionInfo:
    info = SessionInfo(path, SessionFormat.CLAUDE, path.stem, interactive="subagents" not in path.parts)
    titles: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                # Tool results can make lines huge; parse only the few that matter.
                if not (
                    '"ai-title"' in line
                    or '"custom-title"' in line
                    or (info.cwd is None and '"cwd"' in line)
                    or (info.first_prompt is None and '"human"' in line)
                ):
                    continue
                record = _json_object(line)
                for kind, key in (("custom-title", "customTitle"), ("ai-title", "aiTitle")):
                    if record.get("type") == kind and isinstance(record.get(key), str) and record[key].strip():
                        titles[kind] = record[key].strip()
                if info.cwd is None and isinstance(record.get("cwd"), str):
                    info.cwd = record["cwd"]
                    info.branch = record.get("gitBranch") or None
                    info.started = _time(record.get("timestamp"))
                if info.first_prompt is None and record.get("type") == "user" and _mapping(record.get("origin")).get("kind") == "human":
                    info.first_prompt = _prompt_line("\n".join(_text_parts(_mapping(record.get("message")).get("content"), "text")))
    except OSError:
        pass
    info.title = titles.get("custom-title") or titles.get("ai-title")
    return info


_codex_title_cache: dict[Path, dict[str, str]] = {}


def _codex_title(path: Path, session_id: str) -> str | None:
    """Codex keeps short thread names in session_index.jsonl beside its sessions directory."""

    for parent in [*path.parents, Path.home() / ".codex"]:
        index = parent / "session_index.jsonl"
        if index.is_file():
            break
    else:
        return None
    if index not in _codex_title_cache:
        titles: dict[str, str] = {}
        try:
            for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
                record = _json_object(line)
                name = record.get("thread_name")
                if isinstance(record.get("id"), str) and isinstance(name, str) and name.strip():
                    titles[record["id"]] = name.strip()
        except OSError:
            pass
        _codex_title_cache[index] = titles
    return _codex_title_cache[index].get(session_id)


def _codex_info(path: Path) -> SessionInfo:
    match = UUID_SUFFIX.search(path.stem)
    info = SessionInfo(path, SessionFormat.CODEX, match[1] if match else path.stem)
    meta: Record = {}
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            first = _json_object(handle.readline())
            if first.get("type") == "session_meta":
                meta = _mapping(first.get("payload"))
            # The first prompt is near the top; do not read multi-megabyte rollouts to find it.
            for line in islice(handle, 400):
                if '"user' in line or '"UserMessage"' in line:
                    representation = _codex_representation(_json_object(line))
                    if representation and representation[1].role == "USER":
                        info.first_prompt = _one_line(representation[1].text)
                        if info.first_prompt:
                            break
    except OSError:
        pass
    session_id = meta.get("id") or meta.get("session_id")
    if isinstance(session_id, str):
        info.id = session_id
    info.cwd = meta.get("cwd") if isinstance(meta.get("cwd"), str) else None
    info.branch = _mapping(meta.get("git")).get("branch") or None
    info.started = _time(meta.get("timestamp"))
    source = meta.get("source")
    info.interactive = source is None or (isinstance(source, str) and source != "exec" and meta.get("thread_source") != "subagent")
    info.title = _codex_title(path, info.id)
    return info


def session_info(path: Path, session_format: SessionFormat | None = None) -> SessionInfo:
    """Describe a session without exporting it."""

    session_format = session_format or detect_session_format(path)
    return _claude_info(path) if session_format is SessionFormat.CLAUDE else _codex_info(path)


def session_title(info: SessionInfo, messages: Iterable[Message] = ()) -> str:
    if info.title or info.first_prompt:
        return info.title or info.first_prompt or ""
    first = next((message for message in messages if message.role == "USER"), None)
    return (_one_line(first.text) if first else None) or f"Session {info.id}"


# Rendering ----------------------------------------------------------------


def _home(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home) :] if path == home or path.startswith(home + os.sep) else path


def _within(path: str | None, directory: str) -> bool:
    return path is not None and (path == directory or path.startswith(directory.rstrip(os.sep) + os.sep))


def _relative(path: str, cwd: str | None) -> str:
    if cwd and os.path.isabs(path) and _within(path, cwd):
        return os.path.relpath(path, cwd)
    return _home(path)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _describe_model(model: ModelChange) -> str:
    return f"{model.model} ({model.effort} effort)" if model.effort else model.model


def activity_line(tools: Sequence[ToolUse], cwd: str | None = None, code: str = "") -> str | None:
    """Summarize one turn's tool use in a line; *code* wraps file names (e.g. a backtick)."""

    counts = Counter(tool.kind for tool in tools)
    files = list(dict.fromkeys(_relative(name, cwd) for tool in tools for name in tool.files))
    parts = []
    if counts["command"]:
        parts.append(_plural(counts["command"], "command"))
    if files:
        shown = ", ".join(f"{code}{name}{code}" for name in files[:6])
        parts.append(f"edited {shown}" + (f" and {len(files) - 6} more" if len(files) > 6 else ""))
    elif counts["edit"]:
        parts.append(_plural(counts["edit"], "edit"))
    if counts["web"]:
        parts.append(_plural(counts["web"], "web lookup"))
    if counts["agent"]:
        parts.append(_plural(counts["agent"], "subagent"))
    others = Counter(tool.name for tool in tools if tool.kind == "other")
    parts += [f"{name} ({count} calls)" if count > 1 else name for name, count in others.most_common(3)]
    if len(others) > 3:
        parts.append(_plural(len(others) - 3, "other tool"))
    return "Tool activity: " + "; ".join(parts) + "." if parts else None


def _blocks(entries: Iterable[Entry], cwd: str | None, activity: bool, code: str) -> Iterator[tuple[str, str]]:
    """Yield (kind, text) pairs: kind is a message role, "MODEL", or "ACTIVITY"."""

    tools: list[ToolUse] = []
    current: ModelChange | None = None

    def pending() -> Iterator[tuple[str, str]]:
        line = activity_line(tools, cwd, code) if activity else None
        tools.clear()
        if line:
            yield "ACTIVITY", line

    for entry in entries:
        if isinstance(entry, ToolUse):
            tools.append(entry)
        elif isinstance(entry, ModelChange):
            if entry.effort is None and current:
                entry = replace(entry, effort=current.effort)
            if current and entry != current:
                yield from pending()
                yield "MODEL", f"Switched to {_describe_model(entry)}."
            current = entry
        else:
            if entry.role not in {"AGENT", *TOOL_ROLES}:
                yield from pending()
            yield entry.role, entry.text
    yield from pending()


def _models(entries: Iterable[Entry]) -> list[ModelChange]:
    models: list[ModelChange] = []
    for entry in entries:
        if isinstance(entry, ModelChange):
            if entry.effort is None and models:
                entry = replace(entry, effort=models[-1].effort)
            if entry not in models:
                models.append(entry)
    return models


def _span(entries: Sequence[Entry], info: SessionInfo) -> str | None:
    times = [time for entry in entries if isinstance(entry, Message) and (time := _time(entry.timestamp))]
    start, end = min(times, default=info.started), max(times, default=None)
    if start is None:
        return None
    text = start.strftime("%Y-%m-%d %H:%M")
    if end and end.strftime("%Y-%m-%d %H:%M") != text:
        text += end.strftime(" to %H:%M") if end.date() == start.date() else end.strftime(" → %Y-%m-%d %H:%M")
    return text


def _header(info: SessionInfo, entries: Sequence[Entry], markdown: bool, activity: bool) -> list[str]:
    code = "`" if markdown else ""
    facts = []
    if info.cwd:
        facts.append(("Project", f"{code}{_home(info.cwd)}{code}" + (f" (branch {code}{info.branch}{code})" if info.branch else "")))
    if span := _span(entries, info):
        facts.append(("Date", span))
    if models := _models(entries):
        facts.append(("Models" if len(models) > 1 else "Model", ", then ".join(map(_describe_model, models))))
    facts.append(("Session", f"{AGENT_NAMES[info.format]} {code}{info.id}{code}"))
    facts.append(("Log", f"{code}{_home(str(info.path))}{code}"))
    note = "Visible conversation only: reasoning, tool calls and their output, and injected context are omitted."
    if any(isinstance(entry, Message) and entry.role in TOOL_ROLES for entry in entries):
        note = "Conversation with recorded tool calls and results: reasoning and injected context are omitted."
    if activity:
        note += " Each agent turn ends with a one-line summary of its tool activity."
    title = session_title(info, (entry for entry in entries if isinstance(entry, Message)))
    if markdown:
        return [f"# {title}", "\n".join(f"- **{label}:** {value}" for label, value in facts), f"*{note}*", "---"]
    return [title, "\n".join(f"{label}: {value}" for label, value in facts), note]


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def render(entries: Iterable[Entry], output_format: str = "markdown", *, info: SessionInfo | None = None, activity: bool = True) -> str:
    """Render a conversation as markdown or plain text (merged turns), or JSON (one object per message)."""

    entries = list(entries)
    if output_format == "json":
        return json.dumps([asdict(entry) for entry in entries if isinstance(entry, Message)], ensure_ascii=False, indent=2)
    markdown = output_format == "markdown"
    parts = _header(info, entries, markdown, activity) if info else []
    speaker = None
    for kind, text in _blocks(entries, info.cwd if info else None, activity, "`" if markdown else ""):
        if kind in TOOL_ROLES:
            label = "Tool result" if kind == "TOOL_RESULT" else "Tool call"
            if markdown:
                fence = "`" * max(3, max((len(run) + 1 for run in re.findall(r"`+", text)), default=0))
                parts.append(f"### {label}\n\n{fence}json\n{text}\n{fence}")
            else:
                parts.append(f"{label.upper()}:\n{text}")
        elif kind in {"NOTICE", "MODEL"}:
            parts.append(_quote(text) if markdown else f"[{text}]")
        elif kind == "ACTIVITY":
            parts.append(f"*{text}*" if markdown else f"[{text}]")
        else:
            # Consecutive messages from one speaker form a single section.
            if kind == speaker:
                parts.append(text)
            elif markdown:
                parts += [f"## {kind.title()}", text]
            else:
                parts.append(f"{kind}:\n{text}")
            speaker = kind
    return "\n\n".join(parts)


# Choosing a session -------------------------------------------------------

RECENT_LIMIT = 300


def recent_sessions(roots: Sequence[Path] = DEFAULT_SESSION_ROOTS, limit: int = RECENT_LIMIT) -> list[SessionInfo]:
    """Interactive sessions with at least one prompt, most recently active first."""

    found: list[tuple[float, Path, SessionFormat]] = []
    for root in roots:
        root = root.expanduser()
        candidates = [(path, SessionFormat.CLAUDE) for path in (root / "projects").glob("*/*.jsonl")]
        if (root / "sessions").is_dir():
            candidates += [(path, SessionFormat.CODEX) for path in (root / "sessions").rglob("*.jsonl")]
        for path, session_format in candidates:
            try:
                found.append((path.stat().st_mtime, path, session_format))
            except OSError:
                continue
    found.sort(key=lambda item: item[0], reverse=True)
    sessions = []
    for mtime, path, session_format in found[:limit]:
        info = _claude_info(path) if session_format is SessionFormat.CLAUDE else _codex_info(path)
        if info.interactive and info.first_prompt:
            info.updated = datetime.fromtimestamp(mtime).astimezone()
            sessions.append(info)
    return sessions


def _picker_row(info: SessionInfo, here: str) -> str:
    when = info.updated.strftime("%b %d %H:%M") if info.updated else ""
    agent = "claude" if info.format is SessionFormat.CLAUDE else "codex"
    folder = "." if info.cwd == here else _home(info.cwd or "?")
    folder = folder if len(folder) <= 28 else "…" + folder[-27:]
    title = " ".join((info.title or info.first_prompt or info.id).split())
    return f"{info.path}\t{when:<12}  {agent:<6}  {folder:<28}  {title}"


def pick_session(roots: Sequence[Path] = DEFAULT_SESSION_ROOTS) -> Path:
    """Let the user choose a recent session with fzf; sessions from this directory come first."""

    fzf = shutil.which("fzf")
    if not fzf:
        raise SessionError("Pass a session ID or JSONL path, or install fzf to choose from recent sessions.")
    here = os.getcwd()
    sessions = sorted(recent_sessions(roots), key=lambda info: not _within(info.cwd, here))
    if not sessions:
        raise SessionError("No recent sessions found.")
    preview = f"{shlex.quote(sys.executable)} -m scripts_agent_export {{1}} -o - 2>/dev/null"
    if shutil.which("bat"):
        preview += " | bat --language=markdown --color=always --style=plain --paging=never"
    result = subprocess.run(
        [
            fzf,
            "--delimiter=\t",
            "--with-nth=2..",
            "--tiebreak=index",
            "--layout=reverse",
            "--prompt=session> ",
            "--header=Enter exports · Esc cancels",
            "--preview",
            preview,
            "--preview-window=right,55%,wrap",
        ],
        input="".join(_picker_row(info, here) + "\n" for info in sessions),
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise typer.Exit(130 if result.returncode == 130 else 1)
    return Path(result.stdout.split("\t", 1)[0].strip())


# Command line -------------------------------------------------------------

FORMAT_SUFFIXES = {"markdown": ".md", "text": ".txt", "json": ".json"}
SUFFIX_FORMATS = {".md": "markdown", ".markdown": "markdown", ".txt": "text", ".json": "json"}


def _slug(text: str, limit: int = 60) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug if len(slug) <= limit else slug[:limit].rsplit("-", 1)[0]


def default_filename(info: SessionInfo, title: str, suffix: str = ".md") -> str:
    """DATE-TITLE.md, dated by when the session started."""

    date = (info.started or info.updated or datetime.now().astimezone()).strftime("%Y-%m-%d")
    return f"{date}-{_slug(title) or info.id[:8]}{suffix}"


def _unclaimed(path: Path, session_id: str) -> Path:
    """Re-exporting a session replaces its file; a different session gets its own name."""

    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            existing = handle.read(4096)
    except FileNotFoundError:
        return path
    except OSError:
        existing = ""
    return path if session_id in existing else path.with_stem(f"{path.stem}-{session_id[:8]}")


def _stdout_is_terminal() -> bool:
    return sys.stdout.isatty()


def _shown(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return _home(str(path))


app = typer.Typer(add_completion=False, help="Export the visible conversation from a Claude or Codex session.")


@app.command()
def export(
    source: Annotated[
        str | None, typer.Argument(help="Session ID or JSONL path. Omit it to choose a recent session with fzf.", show_default=False)
    ] = None,
    output: Annotated[
        str | None,
        typer.Option(
            "--output",
            "-o",
            help="File or directory to write, or '-' for stdout. Default: DATE-TITLE.md here, or stdout when piped.",
            show_default=False,
        ),
    ] = None,
    output_format: Annotated[
        str | None,
        typer.Option(
            "--format", help="markdown, text, or json (per-message, with source locations). Default: from -o's extension, else markdown."
        ),
    ] = None,
    activity: Annotated[bool, typer.Option(help="End each agent turn with a one-line summary of its tool use.")] = True,
    include_tools: Annotated[bool, typer.Option("--include-tools", help="Include recorded tool calls, arguments, and results.")] = False,
    single_session: Annotated[
        bool, typer.Option(help="Export only this file, without joining Claude continuations or Codex resumes.")
    ] = False,
    strict: Annotated[bool, typer.Option(help="Fail without producing an export if completeness warnings occur.")] = False,
) -> None:
    """Export a session's prompts, replies, questions, answers, plans, and summaries as a readable transcript."""
    if output_format not in {None, *FORMAT_SUFFIXES}:
        raise typer.BadParameter("Choose markdown, text, or json", param_hint="--format")
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ExportWarning)
            path = pick_session() if source is None else resolve_session(source.strip())
            session_format = detect_session_format(path)
            entries = list(
                conversation_entries(path, single_session=single_session, session_format=session_format, include_tools=include_tools)
            )
            info = session_info(path, session_format)
            if session_format is SessionFormat.CODEX and not single_session:
                first_source = next((entry.source for entry in entries if isinstance(entry, Message) and entry.source), None)
                if first_source and Path(first_source) != path:
                    info = session_info(Path(first_source), session_format)
        diagnostics = list(dict.fromkeys(str(warning.message) for warning in caught))
        for diagnostic in diagnostics:
            typer.echo(f"Warning: {diagnostic}", err=True)
        if strict and diagnostics:
            raise SessionError("Export cancelled by --strict because completeness warnings occurred.")

        messages = [entry for entry in entries if isinstance(entry, Message)]
        info.title = session_title(info, messages)
        explicit = Path(output).expanduser() if output and output != "-" else None
        if explicit and not explicit.is_dir():
            output_format = output_format or SUFFIX_FORMATS.get(explicit.suffix.lower())
        output_format = output_format or "markdown"
        if output == "-" or (output is None and not _stdout_is_terminal()):
            destination = None
        elif explicit and not explicit.is_dir():
            destination = explicit
        else:
            name = default_filename(info, info.title, FORMAT_SUFFIXES[output_format])
            destination = _unclaimed((explicit or Path.cwd()) / name, info.id)

        text = render(entries, output_format, info=info, activity=activity)
        if not messages:
            typer.echo("No conversation messages found in this session.", err=True)
        if destination is None:
            typer.echo(text)
            return
        resolved = destination.resolve()
        if resolved == path or resolved.suffix == ".jsonl":
            raise SessionError("Refusing to overwrite a session log; choose a .md, .txt, or .json output file.")
        destination.write_text(text + "\n", encoding="utf-8")
        tokens = len(text) // 4
        size = f"{tokens / 1000:.0f}k" if tokens >= 1000 else str(tokens)
        typer.echo(f"Saved {_shown(destination)} ({_plural(len(messages), 'message')}, ≈{size} tokens)", err=True)
    except (SessionError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


def main() -> None:
    app()


if __name__ == "__main__":
    main()
