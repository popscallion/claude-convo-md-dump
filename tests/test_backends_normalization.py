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
