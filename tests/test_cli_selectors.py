import sys
from pathlib import Path

import pytest

import as_i_was_saying as app


def test_resolve_session_by_id_exact_full_id(monkeypatch):
    sessions = [
        {
            "path": Path("/tmp/a.jsonl"),
            "backend": "codex",
            "session_id": "657bc80bb228",
            "full_session_id": "019c4406-8031-7130-a1ab-657bc80bb228",
        }
    ]
    monkeypatch.setattr(app, "scan_sessions_for_resolution", lambda **_kwargs: sessions)
    matched = app.resolve_session_by_id("019c4406-8031-7130-a1ab-657bc80bb228")
    assert str(matched["path"]) == "/tmp/a.jsonl"


def test_resolve_session_by_id_prefers_exact_over_prefix(monkeypatch):
    sessions = [
        {
            "path": Path("/tmp/exact.jsonl"),
            "backend": "claude",
            "session_id": "abc12345",
            "full_session_id": "abc12345",
        },
        {
            "path": Path("/tmp/prefix.jsonl"),
            "backend": "claude",
            "session_id": "abc123456789",
            "full_session_id": "abc123456789",
        },
    ]
    monkeypatch.setattr(app, "scan_sessions_for_resolution", lambda **_kwargs: sessions)
    matched = app.resolve_session_by_id("abc12345")
    assert str(matched["path"]) == "/tmp/exact.jsonl"


def test_resolve_session_by_id_ambiguous_prefix(monkeypatch):
    sessions = [
        {
            "path": Path("/tmp/one.jsonl"),
            "backend": "claude",
            "session_id": "abc12345",
            "full_session_id": "abc12345-0000-0000-0000-000000000001",
        },
        {
            "path": Path("/tmp/two.jsonl"),
            "backend": "claude",
            "session_id": "abc12399",
            "full_session_id": "abc12399-0000-0000-0000-000000000002",
        },
    ]
    monkeypatch.setattr(app, "scan_sessions_for_resolution", lambda **_kwargs: sessions)
    with pytest.raises(ValueError) as exc:
        app.resolve_session_by_id("abc123")
    assert "Ambiguous ID prefix" in str(exc.value)


def test_resolve_session_by_id_prefix_requires_min_length(monkeypatch):
    sessions = [
        {
            "path": Path("/tmp/a.jsonl"),
            "backend": "claude",
            "session_id": "abc12345",
            "full_session_id": "abc12345-0000-0000-0000-000000000001",
        }
    ]
    monkeypatch.setattr(app, "scan_sessions_for_resolution", lambda **_kwargs: sessions)
    with pytest.raises(ValueError) as exc:
        app.resolve_session_by_id("abc", min_prefix_len=6)
    assert "Prefix lookups require at least 6 characters" in str(exc.value)


def test_resolve_session_by_id_not_found(monkeypatch):
    sessions = [
        {
            "path": Path("/tmp/a.jsonl"),
            "backend": "claude",
            "session_id": "abc12345",
            "full_session_id": "abc12345-0000-0000-0000-000000000001",
        }
    ]
    monkeypatch.setattr(app, "scan_sessions_for_resolution", lambda **_kwargs: sessions)
    with pytest.raises(ValueError) as exc:
        app.resolve_session_by_id("zzz999")
    assert "No session matched ID" in str(exc.value)


def test_latest_flag_selects_first_session(monkeypatch):
    mock_sessions = [
        {"path": "/tmp/s1.jsonl", "mtime": 100, "backend": "claude"},
        {"path": "/tmp/s2.jsonl", "mtime": 50, "backend": "claude"},
    ]
    monkeypatch.setattr(app, "discover_sessions", lambda **_kwargs: mock_sessions)
    called = {}

    def fake_convert(filepath, output_file, mode, backend, redaction, tail, head):
        called["filepath"] = filepath
        called["backend"] = backend

    monkeypatch.setattr(app, "convert", fake_convert)
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "--latest"])
    app.main()

    assert called["filepath"] == "/tmp/s1.jsonl"
    assert called["backend"] == "claude"


def test_latest_flag_no_sessions_error(monkeypatch, capsys):
    monkeypatch.setattr(app, "discover_sessions", lambda **_kwargs: [])
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "--latest"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 1
    assert "No sessions found to select latest from" in capsys.readouterr().err


def test_id_flag_resolves_and_converts(monkeypatch):
    monkeypatch.setattr(
        app,
        "resolve_session_by_id",
        lambda *_args, **_kwargs: {"path": "/tmp/id.jsonl", "backend": "codex"},
    )
    called = {}

    def fake_convert(filepath, output_file, mode, backend, redaction, tail, head):
        called["filepath"] = filepath
        called["backend"] = backend

    monkeypatch.setattr(app, "convert", fake_convert)
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "--id", "019c4406"])
    app.main()

    assert called["filepath"] == "/tmp/id.jsonl"
    assert called["backend"] == "codex"


def test_id_flag_conflicts_with_input_file(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "file.jsonl", "--id", "abc123"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 2
    assert "--id" in capsys.readouterr().err


def test_list_conflicts_with_selectors(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "--list", "--id", "abc123"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 2
    assert "--list" in capsys.readouterr().err

    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "--list", "--latest"])
    with pytest.raises(SystemExit) as exc2:
        app.main()
    assert exc2.value.code == 2
    assert "--latest" in capsys.readouterr().err


def test_id_and_latest_are_mutually_exclusive(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "--id", "abc123", "--latest"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 2
    assert "--id" in capsys.readouterr().err


def test_id_flag_ignores_query(monkeypatch, capsys):
    monkeypatch.setattr(
        app,
        "resolve_session_by_id",
        lambda *_args, **_kwargs: {"path": "/tmp/id.jsonl", "backend": "claude"},
    )
    monkeypatch.setattr(app, "convert", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "--id", "abc123", "--query", "auth"])
    app.main()
    assert "--query` is ignored with `--id`" in capsys.readouterr().err


def test_invalid_since_is_ignored_for_explicit_input_file(monkeypatch, tmp_path, capsys):
    src = tmp_path / "s.jsonl"
    src.write_text('{"type":"user","message":{"content":"x"}}\n', encoding="utf-8")
    called = {}

    def fake_convert(filepath, output_file, mode, backend, redaction, tail, head):
        called["filepath"] = filepath
        called["backend"] = backend

    monkeypatch.setattr(app, "convert", fake_convert)
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", str(src), "--since", "bad"])
    app.main()

    assert called["filepath"] == str(src)
    assert "--since`/`--all-time` only affect discovery" in capsys.readouterr().err


def test_resolve_session_by_id_scans_beyond_discovery_limits(monkeypatch, tmp_path):
    codex_root = tmp_path / "codex"
    session_dir = codex_root / "2026" / "02" / "12"
    session_dir.mkdir(parents=True)

    target_id = "00000000-0000-0000-0000-000000000001"
    target_path = session_dir / (
        "rollout-2026-02-12T10-00-01-{0}.jsonl".format(target_id)
    )
    target_path.write_text('{"type":"event_msg","payload":{"type":"user_message","text":"one"}}\n', encoding="utf-8")

    for idx in range(2, 30):
        sid = "00000000-0000-0000-0000-{0:012x}".format(idx)
        path = session_dir / "rollout-2026-02-12T10-00-{0:02d}-{1}.jsonl".format(idx, sid)
        path.write_text('{"type":"event_msg","payload":{"type":"user_message","text":"x"}}\n', encoding="utf-8")

    monkeypatch.setenv("CODEX_LOG_DIR", str(codex_root))
    matched = app.resolve_session_by_id(target_id, backend="codex")
    assert str(matched["path"]) == str(target_path)


def test_emit_id_round_trips_with_id_selector(monkeypatch, tmp_path, capsys):
    codex_root = tmp_path / "codex"
    session_dir = codex_root / "2026" / "02" / "12"
    session_dir.mkdir(parents=True)
    session_id = "019c4406-8031-7130-a1ab-657bc80bb228"
    session = session_dir / (
        "rollout-2026-02-12T10-00-01-{0}.jsonl".format(session_id)
    )
    session.write_text(
        '{"type":"session_meta","payload":{"id":"019c4406-8031-7130-a1ab-657bc80bb228"}}\n'
        '{"type":"event_msg","payload":{"type":"user_message","text":"hello"}}\n',
        encoding="utf-8",
    )

    monkeypatch.setenv("CODEX_LOG_DIR", str(codex_root))
    monkeypatch.setattr(
        sys,
        "argv",
        ["as_i_was_saying.py", "--backend", "codex", str(session), "--emit", "id"],
    )
    with pytest.raises(SystemExit) as first:
        app.main()
    assert first.value.code == 0
    emitted = capsys.readouterr().out.strip()
    assert emitted == session_id

    monkeypatch.setattr(
        sys,
        "argv",
        ["as_i_was_saying.py", "--backend", "codex", "--id", emitted, "--emit", "path"],
    )
    with pytest.raises(SystemExit) as second:
        app.main()
    assert second.value.code == 0
    assert capsys.readouterr().out.strip() == str(session)
