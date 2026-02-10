import json
import sys

import pytest

import as_i_was_saying as app


def test_select_session_reports_missing_fzf(monkeypatch):
    monkeypatch.setattr(app, "discover_sessions", lambda **_kwargs: [{"backend": "claude", "summary": "x"}])
    monkeypatch.setattr(app, "fzf_select", lambda *_args, **_kwargs: (None, "unavailable"))
    with pytest.raises(SystemExit) as exc:
        app.select_session()
    assert exc.value.code == 2


def test_render_block_variants():
    assert app.render_block({"type": "text", "text": "x"}, "chat") == "x"
    assert "Thinking" in app.render_block({"type": "thinking", "thinking": "t"}, "thoughts")
    assert "Tool Use" in app.render_block({"type": "tool_use", "name": "n", "input": {}}, "thoughts")
    assert "Output Omitted" in app.render_block({"type": "tool_result", "content": "x"}, "thoughts")
    assert "Tool Result" in app.render_block({"type": "tool_result", "content": "x"}, "verbose")
    assert "Unknown Block" in app.render_block({"type": "unknown", "source": "s", "raw": {}}, "verbose")


def test_collect_events_handles_json_and_jsonl(tmp_path):
    jsonl = tmp_path / "s.jsonl"
    jsonl.write_text(
        json.dumps({"type": "user", "message": {"content": "u"}}) + "\n",
        encoding="utf-8",
    )
    events = app.collect_events(str(jsonl), "claude")
    assert events and events[0]["role"] == "user"

    js = tmp_path / "s.json"
    js.write_text(
        json.dumps({"messages": [{"type": "user", "content": "u"}]}),
        encoding="utf-8",
    )
    events2 = app.collect_events(str(js), "gemini")
    assert events2 and events2[0]["role"] == "user"


def test_main_list_with_input_file_errors(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "/tmp/x.jsonl", "--list"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 2
    assert "--list" in capsys.readouterr().err


def test_main_no_input_non_tty_shows_hint(monkeypatch, capsys):
    class _FakeStdin:
        @staticmethod
        def isatty():
            return False

    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py"])
    monkeypatch.setattr(sys, "stdin", _FakeStdin())
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 1
    assert "--list" in capsys.readouterr().err


def test_main_emit_path_with_input_file(monkeypatch, capsys, tmp_path):
    session = tmp_path / "s.jsonl"
    session.write_text('{"type":"user","message":{"content":"u"}}\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", str(session), "--emit", "path"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == str(session)


def test_main_emit_id_with_input_file(monkeypatch, capsys, tmp_path):
    session = tmp_path / "rollout-2026-02-09T15-10-02-019c4406-8031-7130-a1ab-657bc80bb228.jsonl"
    session.write_text(
        '{"type":"session_meta","payload":{"id":"019c4406-8031-7130-a1ab-657bc80bb228"}}\n'
        '{"type":"user","message":{"content":"u"}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["as_i_was_saying.py", str(session), "--backend", "codex", "--emit", "id"],
    )
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "019c4406-8031-7130-a1ab-657bc80bb228"


def test_main_emit_id_with_gemini_uses_session_id(monkeypatch, capsys, tmp_path):
    session = tmp_path / "session-2026-02-09T20-05-813001ce.json"
    session.write_text(
        '{"sessionId":"3ebe0729-869b-4760-9151-d5abf44957c6","messages":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["as_i_was_saying.py", str(session), "--backend", "gemini", "--emit", "id"],
    )
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "3ebe0729-869b-4760-9151-d5abf44957c6"


def test_fzf_select_unavailable(monkeypatch):
    monkeypatch.setattr(app.shutil, "which", lambda _name: None)
    path, status = app.fzf_select([], "h")
    assert path is None
    assert status == "unavailable"


def test_select_session_cancelled_exits_zero(monkeypatch):
    monkeypatch.setattr(app, "discover_sessions", lambda **_kwargs: [{"backend": "claude"}])
    monkeypatch.setattr(app, "fzf_select", lambda *_args, **_kwargs: (None, "cancelled"))
    with pytest.raises(SystemExit) as exc:
        app.select_session()
    assert exc.value.code == 0


def test_select_session_error_exits_one(monkeypatch):
    monkeypatch.setattr(app, "discover_sessions", lambda **_kwargs: [{"backend": "claude"}])
    monkeypatch.setattr(app, "fzf_select", lambda *_args, **_kwargs: (None, "error"))
    with pytest.raises(SystemExit) as exc:
        app.select_session()
    assert exc.value.code == 1


def test_convert_file_not_found(capsys):
    app.convert("/tmp/does-not-exist-123.jsonl")
    assert "File not found" in capsys.readouterr().out


def test_convert_writes_output_file(tmp_path):
    src = tmp_path / "s.jsonl"
    out = tmp_path / "out.md"
    src.write_text(
        '{"type":"user","timestamp":"2026-01-01T00:00:00Z","message":{"content":"hello"}}\n',
        encoding="utf-8",
    )
    app.convert(str(src), output_file=str(out), mode="chat", backend="claude")
    text = out.read_text(encoding="utf-8")
    assert "# Transcript:" in text
    assert "hello" in text


def test_convert_head_filters_to_first_text_event(tmp_path):
    src = tmp_path / "s.jsonl"
    src.write_text(
        "\n".join(
            [
                '{"type":"user","timestamp":"2026-01-01T00:00:00Z","message":{"content":"first"}}',
                '{"type":"assistant","timestamp":"2026-01-01T00:00:01Z","message":{"content":"second"}}',
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out.md"
    app.convert(str(src), output_file=str(out), mode="chat", backend="claude", head=1)
    text = out.read_text(encoding="utf-8")
    assert "first" in text
    assert "second" not in text


def test_main_invalid_since_value_exits_2(monkeypatch):
    class _TtyIn:
        @staticmethod
        def isatty():
            return True

    monkeypatch.setattr(sys, "stdin", _TtyIn())
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "--since", "bad"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 2


def test_main_unknown_path_defaults_backend_to_claude(monkeypatch, tmp_path):
    src = tmp_path / "x.jsonl"
    src.write_text('{"type":"user","message":{"content":"x"}}\n', encoding="utf-8")
    called = {}

    def fake_convert(filepath, output_file, mode, backend, redaction, tail, head):
        called["backend"] = backend
        called["filepath"] = filepath

    monkeypatch.setattr(app, "convert", fake_convert)
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", str(src)])
    app.main()
    assert called["backend"] == "claude"
    assert called["filepath"] == str(src)
