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
