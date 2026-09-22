import json
from pathlib import Path

import pytest
from scripts_agent_export import (
    ExportWarning,
    Message,
    SessionError,
    SessionFormat,
    app,
    continuation_paths,
    conversation_from,
    detect_session_format,
    messages_from,
    render,
    resolve_session,
)


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
    assert render(messages_from(path)) == "USER:\nHello Codex\n\nAGENT:\nVisible reply\n\n[output_image: private]"


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
    assert render(messages, "markdown") == "## USER\n\nHello"


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
    result = runner.invoke(app, [str(path), "--format", "markdown", "-o", str(output)])
    assert result.exit_code == 0
    assert output.read_text() == "## USER\n\nHello\n"
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
