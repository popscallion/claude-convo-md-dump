import backends


def test_normalize_claude_event_string_content():
    raw = {
        "type": "user",
        "timestamp": "2026-01-01T00:00:00Z",
        "message": {"role": "user", "content": "hello"},
    }
    events = backends.normalize_claude_event(raw)
    assert len(events) == 1
    assert events[0]["role"] == "user"
    assert events[0]["blocks"][0]["type"] == "text"


def test_normalize_codex_event_message_split_roles():
    raw = {
        "type": "response_item",
        "timestamp": "t",
        "payload": {
            "type": "message",
            "content": [
                {"type": "input_text", "text": "u"},
                {"type": "output_text", "text": "a"},
            ],
        },
    }
    events = backends.normalize_codex_event(raw)
    assert [e["role"] for e in events] == ["user", "assistant"]


def test_normalize_codex_event_function_call_and_reasoning_fallback():
    call_raw = {
        "type": "response_item",
        "timestamp": "t",
        "payload": {"type": "function_call", "name": "x", "arguments": '{"k":1}'},
    }
    call_events = backends.normalize_codex_event(call_raw)
    assert call_events[0]["blocks"][0]["type"] == "tool_use"
    assert call_events[0]["blocks"][0]["input"]["k"] == 1

    reason_raw = {
        "type": "response_item",
        "timestamp": "t",
        "payload": {"type": "reasoning", "summary": None},
    }
    reason_events = backends.normalize_codex_event(reason_raw)
    assert "unavailable" in reason_events[0]["blocks"][0]["thinking"].lower()


def test_normalize_codex_unknown_event_msg_maps_to_unknown_block():
    raw = {
        "type": "event_msg",
        "timestamp": "t",
        "payload": {"type": "weird", "foo": "bar"},
    }
    events = backends.normalize_codex_event(raw)
    assert events[0]["role"] == "meta"
    assert events[0]["blocks"][0]["type"] == "unknown"


def test_normalize_gemini_event_thoughts_and_tool_results():
    raw = {
        "type": "gemini",
        "timestamp": "t",
        "content": "answer",
        "thoughts": [{"subject": "s", "description": "d"}],
        "toolCalls": [
            {
                "name": "tool",
                "args": {"q": 1},
                "result": [{"functionResponse": {"response": {"output": "ok"}}}],
            },
            {"name": "tool2", "args": {}, "result": [{"error": "boom"}]},
        ],
    }
    events = backends.normalize_gemini_event(raw)
    blocks = events[0]["blocks"]
    assert any(b.get("type") == "thinking" for b in blocks)
    assert any(b.get("type") == "tool_use" and b.get("name") == "tool" for b in blocks)
    assert any(b.get("type") == "tool_result" and b.get("content") == "ok" for b in blocks)
    assert any(b.get("type") == "tool_result" and b.get("is_error") is True for b in blocks)


def test_normalize_event_dispatch_default_claude():
    raw = {
        "type": "assistant",
        "timestamp": "t",
        "message": {"content": "x"},
    }
    events = backends.normalize_event(raw, "unknown-backend")
    assert events[0]["role"] == "assistant"


def test_codex_normalize_session_meta_and_turn_context():
    session_meta = {
        "type": "session_meta",
        "payload": {"id": "abc", "timestamp": "p-ts"},
    }
    turn_context = {
        "type": "turn_context",
        "timestamp": "row-ts",
        "payload": {"turn": 2},
    }
    meta_events = backends.normalize_codex_event(session_meta)
    ctx_events = backends.normalize_codex_event(turn_context)

    assert meta_events[0]["role"] == "meta"
    assert meta_events[0]["timestamp"] == "p-ts"
    assert meta_events[0]["blocks"][0]["label"] == "Session Meta"
    assert ctx_events[0]["blocks"][0]["label"] == "Turn Context"


def test_codex_event_msg_variants_map_expected_roles():
    user_events = backends.normalize_codex_event(
        {"type": "event_msg", "timestamp": "t", "payload": {"type": "user_message", "text": "u"}}
    )
    reasoning_events = backends.normalize_codex_event(
        {"type": "event_msg", "timestamp": "t", "payload": {"type": "agent_reasoning", "message": "r"}}
    )
    token_events = backends.normalize_codex_event(
        {"type": "event_msg", "timestamp": "t", "payload": {"type": "token_count", "in": 1}}
    )

    assert user_events[0]["role"] == "user"
    assert reasoning_events[0]["blocks"][0]["type"] == "thinking"
    assert token_events[0]["blocks"][0]["type"] == "meta"
    assert token_events[0]["blocks"][0]["label"] == "Token Count"


def test_codex_message_with_role_and_invalid_content_shapes():
    role_message = {
        "type": "response_item",
        "timestamp": "t",
        "payload": {"type": "message", "role": "assistant", "content": [{"text": "only assistant"}]},
    }
    invalid_message = {
        "type": "response_item",
        "timestamp": "t",
        "payload": {"type": "message", "content": "not-a-list"},
    }

    role_events = backends.normalize_codex_event(role_message)
    invalid_events = backends.normalize_codex_event(invalid_message)

    assert role_events == [
        {
            "role": "assistant",
            "timestamp": "t",
            "blocks": [{"type": "text", "text": "only assistant"}],
        }
    ]
    assert invalid_events == []


def test_codex_function_call_output_and_reasoning_summary_list():
    output_raw = {
        "type": "response_item",
        "timestamp": "t",
        "payload": {"type": "function_call_output", "output": {"ok": True}},
    }
    reasoning_raw = {
        "type": "response_item",
        "timestamp": "t",
        "payload": {"type": "reasoning", "summary": [{"text": "first"}, {"x": 1}]},
    }
    output_events = backends.normalize_codex_event(output_raw)
    reasoning_events = backends.normalize_codex_event(reasoning_raw)

    assert output_events[0]["blocks"][0]["type"] == "tool_result"
    assert output_events[0]["blocks"][0]["content"] == {"ok": True}
    assert "first" in reasoning_events[0]["blocks"][0]["thinking"]


def test_gemini_user_error_and_info_paths():
    user = {"type": "user", "timestamp": "t", "content": "prompt"}
    error = {"type": "error", "timestamp": "t", "content": "bad"}
    info = {"type": "info", "timestamp": "t", "content": "note"}

    user_events = backends.normalize_gemini_event(user)
    error_events = backends.normalize_gemini_event(error)
    info_events = backends.normalize_gemini_event(info)

    assert user_events[0]["role"] == "user"
    assert error_events[0]["blocks"][0]["label"] == "Error"
    assert info_events[0]["blocks"][0]["label"] == "Info"
