"""Export the visible part of a Claude or Codex JSONL session.

Session logs contain much more than the conversation shown to a person: model
reasoning, tool calls, tool results, injected context, and bookkeeping records.
This module deliberately has one small job: turn the two supported log formats
into the same stream of visible user/agent messages.
"""

from __future__ import annotations

import json
import re
import warnings
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from itertools import islice
from pathlib import Path
from typing import Annotated, Literal

import typer


class SessionFormat(StrEnum):
    """The session log formats understood by the exporter."""

    CLAUDE = "claude"
    CODEX = "codex"


Role = Literal["USER", "AGENT", "SUMMARY", "NOTICE"]
Record = dict[str, object]


@dataclass(frozen=True, slots=True)
class Message:
    """A visible conversation message."""

    role: Role
    text: str
    source: str = field(default="", compare=False)
    line: int | None = field(default=None, compare=False)
    timestamp: str | None = field(default=None, compare=False)


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


def _records(path: Path) -> Iterator[Record]:
    """Yield valid JSON objects from a JSONL file, ignoring broken lines."""

    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SessionError(f"Could not read session file {path}: {exc}") from exc

    with handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                warnings.warn(f"{path}:{number}: invalid JSON record skipped", ExportWarning, stacklevel=2)
                continue
            if isinstance(record, dict):
                record["_line"] = number
                yield record
            else:
                warnings.warn(f"{path}:{number}: non-object record skipped", ExportWarning, stacklevel=2)


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


def _claude_record(record: Record, calls: dict[str, tuple[str, Record]]) -> Iterator[Message]:
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
            name = str(block.get("name", ""))
            args = _mapping(block.get("input"))
            if name in DIALOGUE_TOOLS:
                calls[str(block.get("id"))] = (name, args)
                yield _dialogue_call(name, args)
        elif isinstance(block, dict) and block.get("type") == "tool_result":
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


def _claude_messages(path: Path, seen: set[str] | None = None) -> Iterator[Message]:
    calls: dict[str, tuple[str, Record]] = {}
    seen = seen if seen is not None else set()
    for record in _records(path):
        uuid = record.get("uuid")
        duplicate = isinstance(uuid, str) and uuid in seen
        if isinstance(uuid, str):
            seen.add(uuid)
        # Even copied calls must populate the result lookup for this session.
        messages = list(_claude_record(record, calls))
        if not duplicate:
            for message in messages:
                yield _located(message, record, path)


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


def _codex_records(path: Path) -> Iterator[tuple[str, Record]]:
    scope = "initial"
    for record in _records(path):
        payload = _mapping(record.get("payload"))
        if record.get("type") == "event_msg" and payload.get("type") == "task_started":
            scope = str(payload.get("turn_id") or record["_line"])
        elif record.get("type") == "turn_context" and payload.get("turn_id"):
            scope = str(payload["turn_id"])
        yield scope, record


def _contains_executable_question(code: str) -> bool:
    # Best-effort detection only. Do not mistake quoted source code or comments
    # (e.g. editing this exporter) for a live question invocation.
    code = re.sub(r"""(?s)//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`""", "", code)
    return bool(re.search(r"(?:tools|functions)\.request_user_input(?:_async)?\s*\(", code))


def _codex_messages(path: Path) -> Iterator[Message]:
    # Event and response messages are two representations of the same exchange.
    # Match occurrence counts, not a text set: repeated real messages must survive.
    counts: list[Counter[tuple[str, str, str]]] = [Counter() for _ in range(4)]
    for scope, record in _codex_records(path):
        representation = _codex_representation(record)
        if representation:
            lane, message = representation
            counts[lane][scope, *_message_key(message)] += 1
    occurrences: list[Counter[tuple[str, str, str]]] = [Counter() for _ in range(4)]
    history: Counter[Message] = Counter()
    calls: dict[str, tuple[str, Record]] = {}
    for scope, record in _codex_records(path):
        payload = _mapping(record.get("payload"))
        kind = payload.get("type")
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
    return stem == session_id or stem.endswith(f"-{session_id}")


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
        details = "\n".join(f"  {match}" for match in matches)
        raise SessionError(f"Multiple sessions matched {source!r}:\n{details}")
    return matches[0]


def messages_from(path: Path, session_format: SessionFormat | None = None) -> Iterator[Message]:
    """Yield visible messages from *path* in source order."""

    session_format = session_format or detect_session_format(path)
    if session_format is SessionFormat.CLAUDE:
        yield from _claude_messages(path)
    else:
        yield from _codex_messages(path)


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


def conversation_from(path: Path, *, single_session: bool = False) -> Iterator[Message]:
    session_format = detect_session_format(path)
    paths = continuation_paths(path) if session_format is SessionFormat.CLAUDE and not single_session else [path]
    seen: set[str] = set()
    for source in paths:
        if len(paths) > 1:
            yield Message("NOTICE", f"Session {source.stem}", source=str(source))
        if session_format is SessionFormat.CLAUDE:
            yield from _claude_messages(source, seen)
        else:
            yield from _codex_messages(source)


def render(messages: Iterable[Message], output_format: str = "text") -> str:
    """Render normalized messages in the command's stable plain-text format."""

    if output_format == "json":
        return json.dumps([asdict(message) for message in messages], ensure_ascii=False, indent=2)
    if output_format == "markdown":
        return "\n\n".join(f"## {message.role}\n\n{message.text}" for message in messages)
    return "\n\n".join(f"{message.role}:\n{message.text}" for message in messages)


app = typer.Typer(add_completion=False, help="Export the visible conversation from a Claude or Codex JSONL session.")


@app.command()
def export(
    source: str = typer.Argument(..., help="Session ID or path to a JSONL session file."),
    single_session: bool = typer.Option(False, help="Export only this file, without joining explicit Claude continuations."),
    output_format: str = typer.Option("text", "--format", help="Output format: text, markdown, or json (includes source locations)."),
    output_path: Annotated[
        Path | None, typer.Option("--output", "-o", help="Save to a file instead of stdout. Existing files are replaced.")
    ] = None,
    strict: bool = typer.Option(False, help="Fail without producing an export if completeness warnings occur."),
) -> None:
    """Export prompts, replies, questions, answers, plans, summaries, and attachment references."""
    if output_format not in {"text", "markdown", "json"}:
        raise typer.BadParameter("Choose text, markdown, or json", param_hint="--format")
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ExportWarning)
            path = resolve_session(source)
            messages = list(conversation_from(path, single_session=single_session))
        diagnostics = list(dict.fromkeys(str(warning.message) for warning in caught))
        for diagnostic in diagnostics:
            typer.echo(f"Warning: {diagnostic}", err=True)
        if strict and diagnostics:
            raise SessionError("Export cancelled by --strict because completeness warnings occurred.")
        output = render(messages, output_format)
        if not messages:
            typer.echo("No conversation messages found in this session.", err=True)
        if output_path:
            destination = output_path.expanduser().resolve()
            if destination == path or destination.suffix == ".jsonl":
                raise SessionError("Refusing to overwrite a session log; choose a .txt, .md, or .json output file.")
            output_path.expanduser().write_text(output + "\n", encoding="utf-8")
            typer.echo(f"Exported {len(messages)} entries to {output_path}", err=True)
        elif output:
            typer.echo(output)
    except (SessionError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


def main() -> None:
    app()


if __name__ == "__main__":
    main()
