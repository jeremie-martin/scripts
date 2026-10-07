import json
from pathlib import Path

import pytest
import scripts_agent_export
from scripts_agent_export import (
    ExportWarning,
    Message,
    ModelChange,
    SessionError,
    SessionFormat,
    ToolUse,
    app,
    codex_continuation_paths,
    continuation_paths,
    conversation_from,
    detect_session_format,
    entries_from,
    messages_from,
    recent_sessions,
    render,
    resolve_session,
    session_info,
)
from typer.testing import CliRunner


def write_jsonl(path: Path, records: list[dict[str, object]]) -> Path:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    return path


def test_claude_export_keeps_human_and_text_blocks_only(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "claude.jsonl",
        [
            {"type": "file-history-snapshot", "snapshot": {}},
            {"type": "user", "isMeta": True, "message": {"content": [{"type": "text", "text": "hidden"}]}},
            {
                "type": "user",
                "origin": {"kind": "task-notification"},
                "message": {"content": [{"type": "text", "text": "<task-notification>hidden</task-notification>"}]},
            },
            {"type": "user", "origin": {"kind": "human"}, "message": {"content": [{"type": "text", "text": "Hello"}]}},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "thinking", "thinking": "private"},
                        {"type": "text", "text": "Visible answer"},
                        {"type": "tool_use", "name": "Read"},
                    ]
                },
            },
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "private"}]}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Done"}]}},
        ],
    )

    assert detect_session_format(path) is SessionFormat.CLAUDE
    assert list(messages_from(path)) == [Message("USER", "Hello"), Message("AGENT", "Visible answer"), Message("AGENT", "Done")]


def test_codex_export_ignores_setup_reasoning_and_tools(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "rollout-2026-session-id.jsonl",
        [
            {"type": "session_meta", "payload": {"session_id": "session-id", "originator": "codex-tui"}},
            {
                "type": "response_item",
                "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "private"}]},
            },
            {
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context>private"}]},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "analysis",
                    "content": [{"type": "output_text", "text": "private"}],
                },
            },
            {
                "type": "response_item",
                "payload": {"type": "reasoning", "summary": [{"type": "summary_text", "text": "private"}]},
            },
            {
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Hello Codex"}]},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Visible reply"}, {"type": "output_image", "url": "private"}],
                },
            },
            {"type": "event_msg", "payload": {"type": "custom_tool_call_output", "output": "private"}},
        ],
    )

    assert detect_session_format(path) is SessionFormat.CODEX
    assert render(messages_from(path), "text") == "USER:\nHello Codex\n\nAGENT:\nVisible reply\n\n[output_image: private]"


def test_resolve_session_matches_filename_and_reports_ambiguity(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    codex = tmp_path / ".codex"
    claude.mkdir()
    codex.mkdir()
    first = write_jsonl(claude / "session-id.jsonl", [{"type": "user", "message": {"content": "hello"}}])

    assert resolve_session("session-id", (claude, codex)) == first.resolve()

    write_jsonl(codex / "rollout-session-id.jsonl", [{"type": "session_meta", "payload": {"originator": "codex-tui"}}])
    with pytest.raises(SessionError, match="Multiple sessions"):
        resolve_session("session-id", (claude, codex))


def test_resolve_session_prefers_canonical_filename_over_metadata_matches(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir()
    canonical = write_jsonl(claude / "session-id.jsonl", [{"type": "user", "message": {"content": "hello"}}])
    write_jsonl(
        claude / "subagent.jsonl",
        [{"type": "user", "sessionId": "session-id", "message": {"content": "copied metadata"}}],
    )

    assert resolve_session("session-id", (claude,)) == canonical.resolve()


def test_resolve_session_accepts_explicit_path(tmp_path: Path) -> None:
    path = write_jsonl(tmp_path / "direct.jsonl", [])
    assert resolve_session(str(path)) == path.resolve()


def claude(role: str, content: object, **metadata: object) -> dict:
    return {"type": role, "message": {"content": content}, **metadata}


def response(kind: str, **payload: object) -> dict:
    return {"type": "response_item", "payload": {"type": kind, **payload}}


def event(kind: str, **payload: object) -> dict:
    return {"type": "event_msg", "payload": {"type": kind, **payload}}


def test_commands_questions_answers_plan_and_approval(tmp_path: Path) -> None:
    question = {"question": "Which color?", "options": [{"label": "Blue", "description": "Cool"}, {"label": "Red"}]}
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            claude("user", "<command-name>/plan</command-name><command-args>Build a clock.\nInclude alarms.</command-args>"),
            claude("assistant", [{"type": "tool_use", "id": "q", "name": "AskUserQuestion", "input": {"questions": [question]}}]),
            claude(
                "user",
                [{"type": "tool_result", "tool_use_id": "q", "content": "tool wrapper"}],
                toolUseResult={"questions": [question], "answers": {"Which color?": "Green, actually"}},
            ),
            claude("assistant", [{"type": "tool_use", "id": "p", "name": "ExitPlanMode", "input": {"plan": "Make a green clock."}}]),
            claude("user", [{"type": "tool_result", "tool_use_id": "p", "content": "User has approved your plan. More plumbing."}]),
            claude("assistant", [{"type": "tool_use", "id": "edit", "name": "Write", "input": {"content": "private code"}}]),
            claude("user", [{"type": "tool_result", "tool_use_id": "edit", "content": "private code"}]),
        ],
    )
    assert list(messages_from(path)) == [
        Message("USER", "/plan\n\nBuild a clock.\nInclude alarms."),
        Message("AGENT", "Which color?\n- Blue: Cool\n- Red"),
        Message("USER", "Which color?\nGreen, actually"),
        Message("AGENT", "Proposed plan:\n\nMake a green clock."),
        Message("USER", "Approved the plan."),
    ]


def test_human_meta_and_unknown_origin_are_preserved(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            claude("user", "Please stop", isMeta=True, origin={"kind": "human"}),
            claude("user", "Queued reply", origin={"kind": "future-human-kind"}),
            claude("user", "Internal context", isMeta=True),
            claude("user", "Task finished", origin={"kind": "task-notification"}),
        ],
    )
    assert list(messages_from(path)) == [Message("USER", "Please stop"), Message("USER", "Queued reply")]


def test_mixed_setup_and_user_prompt_preserves_prompt(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            response(
                "message",
                role="user",
                content=[
                    {"type": "input_text", "text": "<environment_context>cwd</environment_context>\nActual request"},
                    {"type": "input_text", "text": "Another instruction"},
                ],
            )
        ],
    )
    assert list(messages_from(path)) == [Message("USER", "Actual request\n\nAnother instruction")]


def test_summaries_and_command_output_are_labelled(tmp_path: Path) -> None:
    summary = "This session is being continued from a previous conversation.\nSummary: clock built."
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            claude("user", summary),
            {"type": "system", "subtype": "away_summary", "content": "Work recap"},
            claude("user", "<local-command-stdout>Enabled plan mode</local-command-stdout>"),
        ],
    )
    assert list(messages_from(path)) == [
        Message("SUMMARY", summary),
        Message("SUMMARY", "Work recap"),
        Message("NOTICE", "Enabled plan mode"),
    ]


@pytest.mark.parametrize("name", ["request_user_input", "functions.request_user_input", "request_user_input_async"])
def test_codex_questions_and_answers(tmp_path: Path, name: str) -> None:
    args = {"questions": [{"id": "color", "title": "Which color?", "options": ["Blue", "Green"]}]}
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            response("function_call", name=name, call_id="q", arguments=json.dumps(args)),
            response("function_call_output", call_id="q", output=json.dumps({"answers": {"color": {"answers": ["Green"]}}})),
        ],
    )
    assert list(messages_from(path)) == [Message("AGENT", "Which color?\n- Blue\n- Green"), Message("USER", "Which color?\nGreen")]


def test_async_ack_is_not_user_approval(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            response("function_call", name="request_user_input_async", call_id="q", arguments='{"questions":[{"title":"Proceed?"}]}'),
            response("function_call_output", call_id="q", output='{"accepted":true}'),
            response("message", role="user", content="No, wait."),
        ],
    )
    assert list(messages_from(path)) == [Message("AGENT", "Proceed?"), Message("USER", "No, wait.")]


def test_refusal_and_unfamiliar_dialogue_result_survive(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            claude("assistant", [{"type": "tool_use", "id": "p", "name": "ExitPlanMode", "input": {"plan": "Do it"}}]),
            claude("user", [{"type": "tool_result", "tool_use_id": "p", "content": "User rejected this plan: use blue."}]),
        ],
    )
    assert "User rejected this plan: use blue." in render(messages_from(path))
    assert "Approved" not in render(messages_from(path))


def test_codex_mirrors_are_deduplicated_but_repeated_user_text_is_not(tmp_path: Path) -> None:
    records = []
    for _ in range(2):
        records.extend(
            [
                response("message", role="user", content="yes"),
                event("user_message", message="yes"),
                event("item_completed", item={"type": "UserMessage", "content": [{"type": "text", "text": "yes"}]}),
            ]
        )
    records.extend(
        [
            event("agent_message", message="Done"),
            response("message", role="assistant", content="Done"),
            event("item_completed", item={"type": "AgentMessage", "content": [{"type": "Text", "text": "Done"}]}),
            event("task_complete", last_agent_message="Done"),
            event("agent_message", message="Only in event"),
            event("item_completed", item={"type": "AgentMessage", "content": [{"type": "Text", "text": "Only in item"}]}),
            event("task_complete", last_agent_message="Only in completion"),
        ]
    )
    path = write_jsonl(tmp_path / "session.jsonl", records)
    assert list(messages_from(path)) == [
        Message("USER", "yes"),
        Message("USER", "yes"),
        Message("AGENT", "Done"),
        Message("AGENT", "Only in event"),
        Message("AGENT", "Only in item"),
        Message("AGENT", "Only in completion"),
    ]


def test_attachment_reference_survives_without_binary_or_mirror_duplicate(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            response(
                "message",
                role="user",
                content=[
                    {"type": "input_text", "text": "Look at this"},
                    {"type": "input_image", "image_url": "data:image/png;base64,SECRET_BINARY"},
                ],
            ),
            event("user_message", message="Look at this", images=["SECRET_BINARY"]),
        ],
    )
    messages = list(messages_from(path))
    assert len(messages) == 1
    assert "embedded attachment" in messages[0].text
    assert "SECRET_BINARY" not in messages[0].text


def test_compaction_does_not_replay_history_but_recovers_missing_messages(tmp_path: Path) -> None:
    history = [
        {"type": "message", "role": "user", "content": "Original"},
        {"type": "message", "role": "user", "content": "Recovered"},
        {"type": "compaction", "encrypted_content": "SECRET"},
    ]
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            response("message", role="user", content="Original"),
            {"type": "compacted", "payload": {"message": "Readable summary", "replacement_history": history}},
            {"type": "compacted", "payload": {"message": "", "replacement_history": history}},
        ],
    )
    messages = list(messages_from(path))
    assert [m.text for m in messages if m.role == "USER"] == ["Original", "Recovered"]
    assert Message("SUMMARY", "Readable summary") in messages
    assert "No readable summary" in messages[-1].text
    assert "SECRET" not in render(messages)


def test_continuations_both_directions_deduplicate_by_uuid_only(tmp_path: Path) -> None:
    first = write_jsonl(
        tmp_path / "first.jsonl",
        [
            claude("user", "Original", uuid="original"),
            claude("user", "Repeated", uuid="shared"),
            {"type": "continued-in", "sessionId": "first", "continuedInSessionId": "second"},
        ],
    )
    second = write_jsonl(
        tmp_path / "second.jsonl",
        [
            claude("user", "Repeated", uuid="shared"),
            claude("user", "Repeated", uuid="new"),
        ],
    )
    assert continuation_paths(first) == continuation_paths(second) == [first, second]
    assert [m.text for m in conversation_from(second) if m.role == "USER"] == ["Original", "Repeated", "Repeated"]
    assert len(list(conversation_from(second, single_session=True))) == 2


def test_missing_continuation_warns(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "first.jsonl",
        [
            claude("user", "Original"),
            {"type": "continued-in", "sessionId": "first", "continuedInSessionId": "missing"},
        ],
    )
    with pytest.warns(ExportWarning, match="Linked session is missing"):
        assert continuation_paths(path) == [path]


def test_continuation_cycle_fails(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "first.jsonl",
        [
            {"type": "continued-in", "sessionId": "first", "continuedInSessionId": "second"},
            {"type": "continued-in", "sessionId": "second", "continuedInSessionId": "first"},
        ],
    )
    with pytest.raises(SessionError, match="Cyclic"):
        continuation_paths(path)


def codex_rollout(path: Path, records: list[dict], *, day: str, base: str | None = None, session_id: str = "thread") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"id": session_id, "originator": "codex-tui", "timestamp": f"2026-10-{day}T10:00:00Z"}
    if base:
        meta["history_base"] = {"thread_id": base, "end_ordinal_exclusive": 3, "end_byte_offset": 100}
    return write_jsonl(path, [{"type": "session_meta", "payload": meta}, *records])


def test_codex_resumes_across_dates_keep_history_and_source_locations(tmp_path: Path) -> None:
    root = tmp_path / ".codex"
    first = codex_rollout(
        root / "sessions/2026/10/01/rollout-2026-10-01-thread.jsonl",
        [
            event("task_started", turn_id="first-turn"),
            response("message", id="u1", role="user", content="Original"),
            {**response("message", id="a1", role="assistant", content="Done"), "ordinal": 4},
        ],
        day="01",
    )
    second = codex_rollout(
        root / "sessions/2026/10/02/rollout-2026-10-02-thread_resume1.jsonl",
        [
            event("task_started", turn_id="second-turn"),
            {**response("message", id="u2", role="user", content="Continue"), "ordinal": 4},
            {
                "type": "compacted",
                "payload": {"replacement_history": [{"type": "message", "role": "user", "content": "Original"}]},
            },
            response("message", id="a2", role="assistant", content="Done"),
        ],
        day="02",
        base="thread",
    )
    third = codex_rollout(
        root / "archived_sessions/rollout-2026-10-03-thread_resume2.jsonl",
        [event("task_started", turn_id="third-turn"), response("message", role="user", content="Latest")],
        day="03",
        base="thread",
    )
    codex_rollout(
        first.parent / "rollout-2026-10-01-fork.jsonl",
        [response("message", role="user", content="Separate fork")],
        day="01",
        base="thread",
        session_id="fork",
    )
    expected = [
        Message("USER", "Original"), Message("AGENT", "Done"), Message("USER", "Continue"),
        Message("AGENT", "Done"), Message("USER", "Latest"),
    ]
    assert resolve_session("thread", [root]) == first
    for selected in (first, second, third):
        assert codex_continuation_paths(selected) == [first, second, third]
        messages = [m for m in conversation_from(selected) if m.role in {"USER", "AGENT"}]
        assert messages == expected
        assert [(m.source, m.line) for m in messages] == [
            (str(first), 3), (str(first), 4), (str(second), 3), (str(second), 5), (str(third), 3),
        ]
    assert [m.text for m in conversation_from(first, single_session=True)] == ["Original", "Done"]
    result = CliRunner().invoke(app, [str(third)])
    assert result.exit_code == 0
    assert "2026-10-01" in result.stdout
    assert "Latest" in result.stdout
    assert "earlier exchanges retained" in result.stdout


def test_codex_resume_preserves_question_lookup_and_mirror_deduplication(tmp_path: Path) -> None:
    first = codex_rollout(
        tmp_path / "rollout-2026-10-01-thread.jsonl",
        [
            event("task_started", turn_id="turn"),
            response("message", role="assistant", content="Picking a color"),
            response(
                "function_call", name="request_user_input", call_id="q",
                arguments=json.dumps({"questions": [{"id": "color", "title": "Which color?"}]}),
            ),
        ],
        day="01",
    )
    codex_rollout(
        tmp_path / "rollout-2026-10-02-thread_resume.jsonl",
        [
            event("agent_message", message="Picking a color"),
            response("function_call_output", call_id="q", output=json.dumps({"answers": {"color": {"answers": ["Green"]}}})),
        ],
        day="02",
        base="thread",
    )
    assert [m for m in conversation_from(first) if m.role != "NOTICE"] == [
        Message("AGENT", "Picking a color"), Message("AGENT", "Which color?"), Message("USER", "Which color?\nGreen"),
    ]


def test_codex_resume_missing_base_warns_and_strict_refuses_output(tmp_path: Path) -> None:
    path = codex_rollout(
        tmp_path / "rollout-2026-10-02-thread_resume.jsonl",
        [response("message", role="user", content="Latest")],
        day="02",
        base="thread",
    )
    assert resolve_session("thread", [tmp_path]) == path
    with pytest.warns(ExportWarning, match="linked Codex history is missing"):
        assert [m.text for m in conversation_from(path)] == ["Latest"]
    output = tmp_path / "out.md"
    result = CliRunner().invoke(app, [str(path), "--strict", "-o", str(output)])
    assert result.exit_code == 1
    assert not output.exists()
    assert "linked Codex history is missing" in result.stderr
    assert CliRunner().invoke(app, [str(path), "--strict", "--single-session"]).exit_code == 0


def test_codex_unlinked_logs_with_same_id_remain_ambiguous(tmp_path: Path) -> None:
    first = codex_rollout(tmp_path / "rollout-2026-10-01-thread.jsonl", [], day="01")
    codex_rollout(tmp_path / "rollout-2026-10-02-thread_other.jsonl", [], day="02")
    with pytest.raises(SessionError, match="Multiple sessions"):
        resolve_session("thread", [tmp_path])
    with pytest.raises(SessionError, match="Ambiguous Codex"):
        list(conversation_from(first))
    assert list(conversation_from(first, single_session=True)) == []


def test_unknown_conversation_block_warns_and_preserves_text(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            response(
                "message",
                role="user",
                content=[
                    {"type": "future_text", "text": "Important request"},
                ],
            )
        ],
    )
    with pytest.warns(ExportWarning, match="future_text"):
        assert "Important request" in render(messages_from(path))


def test_source_locations_and_formats(tmp_path: Path) -> None:
    path = write_jsonl(tmp_path / "session.jsonl", [claude("user", "Hello", timestamp="2026-09-10T10:00:00Z")])
    messages = list(messages_from(path))
    assert json.loads(render(messages, "json")) == [
        {
            "role": "USER",
            "text": "Hello",
            "source": str(path),
            "line": 1,
            "timestamp": "2026-09-10T10:00:00Z",
        }
    ]
    assert render(messages, "markdown") == "## User\n\nHello"


def test_cli_warns_for_corrupt_logs_and_strict_prevents_output(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    path = write_jsonl(tmp_path / "session.jsonl", [claude("user", "Hello")])
    with path.open("a") as handle:
        handle.write('{"truncated":')
    runner = CliRunner()
    result = runner.invoke(app, [str(path), "--single-session"])
    assert result.exit_code == 0
    assert "Hello" in result.stdout
    assert "invalid JSON" in result.stderr
    output = tmp_path / "output.md"
    result = runner.invoke(app, [str(path), "--strict", "-o", str(output)])
    assert result.exit_code == 1
    assert not output.exists()


def test_cli_output_and_invalid_format(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    path = write_jsonl(tmp_path / "session.jsonl", [claude("user", "Hello")])
    output = tmp_path / "output.md"
    runner = CliRunner()
    result = runner.invoke(app, [str(path), "-o", str(output)])
    assert result.exit_code == 0
    text = output.read_text()
    assert text.startswith("# Hello\n")
    assert "Claude Code `session`" in text
    assert text.endswith("## User\n\nHello\n")
    assert runner.invoke(app, [str(path), "--format", "invalid"]).exit_code != 0
    assert runner.invoke(app, [str(path), "-o", str(path)]).exit_code != 0


def test_identical_event_only_and_response_only_messages_in_different_turns_survive(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            event("task_started", turn_id="first"),
            event("user_message", message="yes"),
            event("task_started", turn_id="second"),
            response("message", role="user", content="yes"),
        ],
    )
    assert list(messages_from(path)) == [Message("USER", "yes"), Message("USER", "yes")]


def test_plan_item_matches_proposed_plan_response(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            response("message", role="assistant", content="<proposed_plan>\nBuild a clock\n</proposed_plan>"),
            event("item_completed", item={"type": "Plan", "text": "Build a clock"}),
        ],
    )
    assert list(messages_from(path)) == [Message("AGENT", "Build a clock")]


def test_orphan_claude_question_result_and_plan_are_recovered(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            claude(
                "user",
                [{"type": "tool_result", "tool_use_id": "q", "content": "plumbing"}],
                toolUseResult={"answers": {"Which color?": "Green"}},
            ),
            claude(
                "user",
                [{"type": "tool_result", "tool_use_id": "p", "content": "plumbing"}],
                toolUseResult={"plan": "Build a green clock", "isAgent": False},
            ),
        ],
    )
    assert list(messages_from(path)) == [
        Message("USER", "Which color?\nGreen"),
        Message("AGENT", "Approved plan:\n\nBuild a green clock"),
        Message("USER", "Approved the plan."),
    ]


def test_local_images_and_file_delivery_are_preserved(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "codex.jsonl",
        [
            event("item_completed", item={"type": "UserMessage", "content": [{"type": "local_image", "path": "/tmp/image.png"}]}),
        ],
    )
    assert list(messages_from(path)) == [Message("USER", "[local_image: /tmp/image.png]")]
    path = write_jsonl(
        tmp_path / "claude.jsonl",
        [
            claude(
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "id": "file",
                        "name": "SendUserFile",
                        "input": {"caption": "Your report", "files": ["/tmp/report.pdf"]},
                    }
                ],
            ),
        ],
    )
    assert list(messages_from(path)) == [Message("AGENT", "Your report\n\n[file: /tmp/report.pdf]")]


def test_metadata_only_session_is_empty_not_unrecognized(tmp_path: Path) -> None:
    path = write_jsonl(tmp_path / "session.jsonl", [{"type": "mode", "sessionId": "empty", "mode": "normal"}])
    assert list(messages_from(path)) == []


def test_claude_copied_question_call_still_connects_to_new_answer(tmp_path: Path) -> None:
    call = claude(
        "assistant",
        [{"type": "tool_use", "id": "q", "name": "AskUserQuestion", "input": {"questions": [{"question": "Which color?"}]}}],
        uuid="shared",
    )
    write_jsonl(tmp_path / "first.jsonl", [call, {"type": "continued-in", "sessionId": "first", "continuedInSessionId": "second"}])
    path = write_jsonl(
        tmp_path / "second.jsonl",
        [
            call,
            claude(
                "user",
                [{"type": "tool_result", "tool_use_id": "q", "content": "plumbing"}],
                toolUseResult={"answers": {"Which color?": "Blue"}},
            ),
        ],
    )
    assert [m for m in conversation_from(path) if m.role != "NOTICE"] == [
        Message("AGENT", "Which color?"),
        Message("USER", "Which color?\nBlue"),
    ]


def test_executable_question_call_warns_but_plain_mentions_do_not(tmp_path: Path) -> None:
    path = write_jsonl(tmp_path / "session.jsonl", [response("custom_tool_call", name="exec", input='text("request_user_input")')])
    assert list(messages_from(path)) == []
    path = write_jsonl(
        tmp_path / "session.jsonl", [response("custom_tool_call", name="exec", input="await tools.request_user_input({questions: qs})")]
    )
    with pytest.warns(ExportWarning, match="question inside executable"):
        assert list(messages_from(path)) == []


def test_quoted_question_code_is_not_executed(tmp_path: Path) -> None:
    import warnings

    path = write_jsonl(
        tmp_path / "session.jsonl",
        [response("custom_tool_call", name="exec", input='await tools.apply_patch("await tools.request_user_input({questions: []})")')],
    )
    with warnings.catch_warnings(record=True) as caught:
        assert list(messages_from(path)) == []
    assert not caught


def test_unknown_response_and_message_event_are_visible_and_warn(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            response("future_interaction"),
            event("future_user_reply", message="Important reply"),
        ],
    )
    with pytest.warns(ExportWarning):
        exported = render(messages_from(path))
    assert "Unsupported future_interaction" in exported
    assert "Important reply" in exported


def test_cli_refuses_output_symlink_to_another_session(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    path = write_jsonl(tmp_path / "session.jsonl", [claude("user", "Hello")])
    other = write_jsonl(tmp_path / "other.jsonl", [claude("user", "Keep me")])
    output = tmp_path / "output.md"
    output.symlink_to(other)
    result = CliRunner().invoke(app, [str(path), "-o", str(output)])
    assert result.exit_code == 1
    assert "Keep me" in other.read_text()


def test_unrelated_ambiguous_links_do_not_block_export(tmp_path: Path) -> None:
    path = write_jsonl(tmp_path / "session.jsonl", [claude("user", "Hello")])
    write_jsonl(
        tmp_path / "other.jsonl",
        [
            {"type": "continued-in", "sessionId": "other", "continuedInSessionId": "a"},
            {"type": "continued-in", "sessionId": "other", "continuedInSessionId": "b"},
        ],
    )
    assert continuation_paths(path) == [path]
    with pytest.raises(SessionError, match="Ambiguous"):
        continuation_paths(tmp_path / "other.jsonl")


def test_invalid_link_target_is_not_followed(tmp_path: Path) -> None:
    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            {"type": "continued-in", "sessionId": "session", "continuedInSessionId": "../elsewhere"},
        ],
    )
    with pytest.raises(SessionError, match="Invalid linked"):
        continuation_paths(path)


def test_claude_turns_merge_with_activity_and_model_switches(tmp_path: Path) -> None:
    def reply(model: str, *blocks: dict) -> dict:
        return claude("assistant", list(blocks), effort="high") | {"message": {"model": model, "content": list(blocks)}}

    path = write_jsonl(
        tmp_path / "session.jsonl",
        [
            claude("user", "Fix it", origin={"kind": "human"}, cwd="/work/app", gitBranch="main", timestamp="2026-09-10T10:00:00Z"),
            reply("opus", {"type": "text", "text": "Looking."}),
            reply("opus", {"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": "ls"}}),
            reply("opus", {"type": "tool_use", "id": "r", "name": "Read", "input": {"file_path": "/work/app/a.py"}}),
            reply("opus", {"type": "tool_use", "id": "e", "name": "Edit", "input": {"file_path": "/work/app/src/a.py"}}),
            reply("opus", {"type": "tool_use", "id": "m", "name": "mcp__docs__read", "input": {}}),
            reply("opus", {"type": "text", "text": "Fixed."}),
            claude("user", "Thanks", origin={"kind": "human"}, timestamp="2026-09-10T10:30:00Z"),
            reply("sonnet", {"type": "text", "text": "Welcome."}),
            {"type": "ai-title", "aiTitle": "Fix the app", "sessionId": "session"},
        ],
    )
    entries = list(entries_from(path))
    assert ModelChange("opus", "high") in entries
    assert ToolUse("edit", "Edit", ("/work/app/src/a.py",)) in entries
    assert not any(isinstance(entry, ToolUse) and entry.name == "Read" for entry in entries)

    info = session_info(path)
    assert (info.title, info.cwd, info.branch, info.first_prompt) == ("Fix the app", "/work/app", "main", "Fix it")
    text = render(entries, info=info)
    assert text.startswith("# Fix the app\n")
    assert "- **Project:** `/work/app` (branch `main`)" in text
    assert "- **Models:** opus (high effort), then sonnet (high effort)" in text
    body = text.split("---\n\n", 1)[1]
    assert body == (
        "## User\n\nFix it\n\n## Agent\n\nLooking.\n\nFixed.\n\n"
        "*Tool activity: 1 command; edited `src/a.py`; mcp__docs__read.*\n\n"
        "## User\n\nThanks\n\n> Switched to sonnet (high effort).\n\n## Agent\n\nWelcome."
    )
    assert "Tool activity" not in render(entries, info=info, activity=False)


def test_codex_exec_scripts_and_turn_context_become_activity(tmp_path: Path) -> None:
    script = 'text(await tools.exec_command({cmd:"ls"})); await tools.write_stdin({}); await tools.exec_command({cmd:"pwd"});'
    patch = 'await tools.apply_patch("*** Begin Patch\\n*** Update File: /work/x.py\\n@@\\n*** Add File: y.py\\n*** End Patch")'
    path = write_jsonl(
        tmp_path / "rollout-2026-01a0c761-a235-7662-948b-685893febde4.jsonl",
        [
            {"type": "session_meta", "payload": {"id": "01a0c761-a235-7662-948b-685893febde4", "originator": "codex-tui", "cwd": "/work"}},
            {"type": "turn_context", "payload": {"model": "gpt-a", "effort": "medium"}},
            response("message", role="user", content=[{"type": "input_text", "text": "Go"}]),
            response("custom_tool_call", name="exec", input=script),
            response("custom_tool_call", name="exec", input=patch),
            response("function_call", name="wait", arguments="{}"),
            response("web_search_call"),
            response("message", role="assistant", content=[{"type": "output_text", "text": "Done"}]),
            {"type": "turn_context", "payload": {"model": "gpt-b", "effort": "medium"}},
        ],
    )
    text = render(entries_from(path), info=session_info(path))
    assert "*Tool activity: 2 commands; edited `x.py`, `y.py`; 1 web lookup.*" in text
    assert text.endswith("> Switched to gpt-b (medium effort).")


def test_rewritten_codex_fragment_is_silent_but_lost_records_warn(tmp_path: Path) -> None:
    full = json.dumps(
        {"ordinal": 5, "type": "response_item", "payload": {"type": "custom_tool_call", "id": "ctc_1", "input": "x"}}, separators=(",", ":")
    )
    fragment = full[:-10]
    path = tmp_path / "session.jsonl"
    path.write_text(f"{fragment}\n{full}\n")
    with warnings_recorded() as caught:
        list(scripts_agent_export._records(path))
    assert caught == []
    path.write_text(f"{fragment}\n")
    with warnings_recorded() as caught:
        list(scripts_agent_export._records(path))
    assert len(caught) == 1


def warnings_recorded():
    import warnings

    class Recorder:
        def __enter__(self) -> list[str]:
            self._context = warnings.catch_warnings(record=True)
            self._caught = self._context.__enter__()
            warnings.simplefilter("always", ExportWarning)
            self.messages: list[str] = []
            return self.messages

        def __exit__(self, *exc: object) -> None:
            self.messages += [str(item.message) for item in self._caught]
            self._context.__exit__(*exc)

    return Recorder()


def test_cli_saves_dated_titled_markdown_when_run_in_a_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def session(name: str) -> Path:
        return write_jsonl(
            tmp_path / f"{name}.jsonl",
            [
                claude("user", "Hello", origin={"kind": "human"}, cwd="/w", timestamp="2026-09-10T10:00:00Z"),
                {"type": "ai-title", "aiTitle": "Review: prompt-add (v2)!", "sessionId": name},
            ],
        )

    first, second = session("aaaaaaaa-1"), session("bbbbbbbb-2")
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.chdir(out)
    monkeypatch.setattr(scripts_agent_export, "_stdout_is_terminal", lambda: True)
    runner = CliRunner()
    date = scripts_agent_export._time("2026-09-10T10:00:00Z").strftime("%Y-%m-%d")
    expected = out / f"{date}-review-prompt-add-v2.md"

    result = runner.invoke(app, [str(first)])
    assert result.exit_code == 0, result.stderr
    assert expected.is_file()
    assert f"Saved {expected.name} (1 message" in result.stderr
    assert runner.invoke(app, [str(first)]).exit_code == 0  # Re-export replaces its own file.
    assert runner.invoke(app, [str(second)]).exit_code == 0  # Another session never does.
    assert {path.name for path in out.iterdir()} == {expected.name, f"{date}-review-prompt-add-v2-bbbbbbbb.md"}

    assert runner.invoke(app, [str(first), "-o", str(tmp_path)]).exit_code == 0
    assert (tmp_path / expected.name).is_file()
    assert runner.invoke(app, [str(first), "-o", "t.json"]).exit_code == 0
    assert json.loads((out / "t.json").read_text())[0]["text"] == "Hello"
    result = runner.invoke(app, [str(first), "-o", "-"])
    assert result.stdout.startswith("# Review: prompt-add (v2)!")


def test_cli_prints_markdown_when_piped(tmp_path: Path) -> None:
    path = write_jsonl(tmp_path / "session.jsonl", [claude("user", "Hello")])
    result = CliRunner().invoke(app, [str(path)])
    assert result.exit_code == 0
    assert result.stdout.startswith("# Hello\n") and "## User\n\nHello" in result.stdout
    assert list(tmp_path.iterdir()) == [path]


def test_recent_sessions_lists_interactive_sessions_with_titles(tmp_path: Path) -> None:
    claude_root, codex_root = tmp_path / ".claude", tmp_path / ".codex"
    (claude_root / "projects" / "p" / "c1" / "subagents").mkdir(parents=True)
    write_jsonl(
        claude_root / "projects" / "p" / "c1.jsonl",
        [claude("user", "Build it", origin={"kind": "human"}, cwd="/w"), {"type": "custom-title", "customTitle": "Named"}],
    )
    command = "<command-message>review</command-message>\n<command-name>/review</command-name>\n<command-args>42</command-args>"
    write_jsonl(claude_root / "projects" / "p" / "c3.jsonl", [claude("user", command, origin={"kind": "human"})])
    write_jsonl(claude_root / "projects" / "p" / "c2.jsonl", [claude("user", [{"type": "tool_result"}])])
    write_jsonl(claude_root / "projects" / "p" / "c1" / "subagents" / "agent.jsonl", [claude("user", "x", origin={"kind": "human"})])
    day = codex_root / "sessions" / "2026" / "09" / "10"
    day.mkdir(parents=True)
    ids = {name: f"0000000{index}-0000-0000-0000-000000000000" for index, name in enumerate(["cli", "exec", "sub", "empty"])}
    for name, source in [("cli", "cli"), ("exec", "exec"), ("sub", {"subagent": {}}), ("empty", "cli")]:
        prompt = [] if name == "empty" else [event("user_message", message=f"\n  {name} prompt\nmore")]
        if name == "cli":  # Newer Codex records the prompt only as a response item, after injected context.
            prompt = [
                response("message", role="user", content=[{"type": "input_text", "text": "<environment_context>x</environment_context>"}]),
                response("message", role="user", content=[{"type": "input_text", "text": "\n  cli prompt\nmore"}]),
            ]
        meta = {"type": "session_meta", "payload": {"id": ids[name], "originator": "codex-tui", "source": source, "cwd": "/w"}}
        write_jsonl(day / f"rollout-2026-{ids[name]}.jsonl", [meta, *prompt])
    (codex_root / "session_index.jsonl").write_text(json.dumps({"id": ids["cli"], "thread_name": "Codex title"}) + "\n")

    sessions = recent_sessions([claude_root, codex_root])
    assert sorted(((info.format, info.title, info.first_prompt) for info in sessions), key=str) == [
        (SessionFormat.CLAUDE, "Named", "Build it"),
        (SessionFormat.CLAUDE, None, "/review 42"),
        (SessionFormat.CODEX, "Codex title", "cli prompt"),
    ]


def test_picker_requires_fzf_and_returns_the_chosen_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / ".claude"
    (root / "projects" / "p").mkdir(parents=True)
    path = write_jsonl(root / "projects" / "p" / "s.jsonl", [claude("user", "Hi", origin={"kind": "human"}, cwd=str(tmp_path))])
    monkeypatch.setattr(scripts_agent_export.shutil, "which", lambda name: None)
    with pytest.raises(SessionError, match="install fzf"):
        scripts_agent_export.pick_session([root])

    rows: list[str] = []

    def fake_fzf(command: list[str], *, input: str, **kwargs: object) -> object:
        rows.append(input)
        return type("Result", (), {"returncode": 0, "stdout": input.splitlines()[0] + "\n"})()

    monkeypatch.setattr(scripts_agent_export.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(scripts_agent_export.subprocess, "run", fake_fzf)
    monkeypatch.chdir(tmp_path)
    assert scripts_agent_export.pick_session([root]) == path
    assert rows[0].split("\t")[1].split()[-2:] == [".", "Hi"]


@pytest.mark.parametrize("output_format", ["markdown", "text", "json"])
@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_include_tools_cli(tmp_path: Path, provider: str, output_format: str) -> None:
    if provider == "claude":
        records = [
            claude("user", "Run the command"),
            claude("assistant", [
                {"type": "text", "text": "Checking now"},
                {"type": "thinking", "thinking": "hidden reasoning"},
                {"type": "tool_use", "id": "call-1", "name": "Bash", "input": {"command": "echo tool-input"}},
            ]),
            claude("user", [{"type": "tool_result", "tool_use_id": "call-1", "content": "tool-output ```", "is_error": True}]),
            claude("assistant", "Finished"),
        ]
    else:
        records = [
            response("message", role="user", content="Run the command"),
            response("message", role="assistant", content="Checking now"),
            response("reasoning", summary=[{"type": "summary_text", "text": "hidden reasoning"}]),
            response("function_call", call_id="call-1", name="functions.exec_command", arguments='{"cmd":"echo tool-input"}'),
            response("function_call_output", call_id="call-1", output="tool-output ```"),
            response("message", role="assistant", content="Finished"),
        ]
    path = write_jsonl(tmp_path / "session.jsonl", records)
    runner = CliRunner()
    default = runner.invoke(app, [str(path), "--format", output_format, "-o", "-"])
    assert default.exit_code == 0, default.output
    assert "tool-input" not in default.stdout and "tool-output" not in default.stdout
    detailed = runner.invoke(app, [str(path), "--include-tools", "--no-activity", "--format", output_format, "-o", "-"])
    assert detailed.exit_code == 0, detailed.output
    assert "hidden reasoning" not in detailed.stdout
    assert "Tool activity:" not in detailed.stdout
    assert detailed.stdout.index("Checking now") < detailed.stdout.index("tool-input") < detailed.stdout.index("tool-output")
    assert detailed.stdout.index("tool-output") < detailed.stdout.index("Finished")
    if output_format == "json":
        messages = json.loads(detailed.stdout)
        assert [m["role"] for m in messages] == ["USER", "AGENT", "TOOL_CALL", "TOOL_RESULT", "AGENT"]
        assert messages[2]["source"] == str(path)
        assert messages[2]["line"] is not None
        assert json.loads(messages[2]["text"])["type"] in {"tool_use", "function_call"}
    elif output_format == "markdown":
        assert "````json" in detailed.stdout  # Embedded fences cannot close a tool block.
        assert "Conversation with recorded tool calls and results" in detailed.stdout


def test_include_codex_custom_native_and_event_tools(tmp_path: Path) -> None:
    path = write_jsonl(tmp_path / "session.jsonl", [
        response("custom_tool_call", call_id="exec-1", name="exec", input="await tools.example({})"),
        event("custom_tool_call_output", call_id="exec-1", output="first result"),
        response("custom_tool_call_output", call_id="exec-1", output="first result"),
        event("custom_tool_call_output", call_id="exec-2", output="event only"),
        response("local_shell_call", call_id="shell-1", action={"command": ["pwd"]}),
        response("local_shell_call_output", call_id="shell-1", output="/project"),
        response("web_search_call", id="web-1", action={"query": "example"}),
    ])
    messages = [e for e in entries_from(path, include_tools=True) if isinstance(e, Message)]
    assert [json.loads(m.text)["type"] for m in messages] == [
        "custom_tool_call", "custom_tool_call_output", "custom_tool_call_output",
        "local_shell_call", "local_shell_call_output", "web_search_call",
    ]
    assert sum("first result" in m.text for m in messages) == 1


def test_include_tools_claude_continuations_and_attachments(tmp_path: Path) -> None:
    call = claude("assistant", [{"type": "tool_use", "id": "read-1", "name": "Read", "input": {"file_path": "picture.png"}}], uuid="call")
    first = write_jsonl(tmp_path / "first.jsonl", [
        call, {"type": "continued-in", "sessionId": "first", "continuedInSessionId": "second"},
    ])
    write_jsonl(tmp_path / "second.jsonl", [
        call,
        claude("user", [{"type": "tool_result", "tool_use_id": "read-1", "content": [
            {"type": "image", "source": {"type": "base64", "data": "binary-content"}},
        ]}]),
    ])
    entries = list(scripts_agent_export.conversation_entries(first, include_tools=True))
    messages = [e for e in entries if isinstance(e, Message) and e.role in {"TOOL_CALL", "TOOL_RESULT"}]
    assert len(messages) == 2
    assert "embedded attachment" in messages[1].text
    assert "binary-content" not in render(entries)
    single = list(scripts_agent_export.conversation_entries(first, include_tools=True, single_session=True))
    assert not any(isinstance(e, Message) and e.role == "TOOL_RESULT" for e in single)


def test_include_tools_keeps_distinct_unidentified_results_and_arbitrary_arguments(tmp_path: Path) -> None:
    path = write_jsonl(tmp_path / "session.jsonl", [
        response("function_call", name="example", arguments={"type": ["arbitrary", "data"]}),
        event("function_call_output", output="event output"),
        response("function_call_output", output="different response output"),
    ])
    messages = [e for e in entries_from(path, include_tools=True) if isinstance(e, Message)]
    assert len(messages) == 3
    assert json.loads(messages[0].text)["arguments"] == {"type": ["arbitrary", "data"]}
    assert json.loads(messages[1].text)["output"] == "event output"
    assert json.loads(messages[2].text)["output"] == "different response output"
