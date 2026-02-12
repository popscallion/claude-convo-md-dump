import sys
import pytest
import as_i_was_saying as app
from unittest.mock import MagicMock

def test_latest_flag_selects_first_session(monkeypatch):
    mock_sessions = [
        {"path": "/tmp/s1.jsonl", "mtime": 100, "backend": "claude"},
        {"path": "/tmp/s2.jsonl", "mtime": 50, "backend": "claude"}
    ]
    monkeypatch.setattr(app, "discover_sessions", lambda **_kwargs: mock_sessions)
    monkeypatch.setattr(app.os.path, "exists", lambda p: True)
    
    # Mock convert to verify it gets called with the right path
    mock_convert = MagicMock()
    monkeypatch.setattr(app, "convert", mock_convert)
    
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "--latest"])
    app.main()
    
    mock_convert.assert_called_once()
    assert mock_convert.call_args[0][0] == "/tmp/s1.jsonl"

def test_latest_flag_no_sessions_error(monkeypatch, capsys):
    monkeypatch.setattr(app, "discover_sessions", lambda **_kwargs: [])
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "--latest"])
    
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 1
    assert "No sessions found" in capsys.readouterr().err

def test_latest_flag_conflicts_with_input_file(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "file.jsonl", "--latest"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 2
    assert "cannot be used with an input file path" in capsys.readouterr().err

def test_id_resolution_exact_match(monkeypatch):
    mock_sessions = [
        {"path": "/tmp/s1.jsonl", "session_id": "abc-123", "backend": "claude"},
        {"path": "/tmp/s2.jsonl", "session_id": "def-456", "backend": "claude"}
    ]
    monkeypatch.setattr(app, "discover_sessions", lambda **_kwargs: mock_sessions)
    monkeypatch.setattr(app.os.path, "exists", lambda p: False) # Simulate file not found
    
    mock_convert = MagicMock()
    monkeypatch.setattr(app, "convert", mock_convert)
    
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "abc-123"])
    app.main()
    
    mock_convert.assert_called_once()
    assert mock_convert.call_args[0][0] == "/tmp/s1.jsonl"

def test_id_resolution_prefix_match(monkeypatch):
    mock_sessions = [
        {"path": "/tmp/s1.jsonl", "session_id": "abc-123", "backend": "claude"},
        {"path": "/tmp/s2.jsonl", "session_id": "def-456", "backend": "claude"}
    ]
    monkeypatch.setattr(app, "discover_sessions", lambda **_kwargs: mock_sessions)
    monkeypatch.setattr(app.os.path, "exists", lambda p: False)
    
    mock_convert = MagicMock()
    monkeypatch.setattr(app, "convert", mock_convert)
    
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "abc"])
    app.main()
    
    mock_convert.assert_called_once()
    assert mock_convert.call_args[0][0] == "/tmp/s1.jsonl"

def test_id_resolution_ambiguous_prefix(monkeypatch, capsys):
    mock_sessions = [
        {"path": "/tmp/s1.jsonl", "session_id": "abc-123", "backend": "claude"},
        {"path": "/tmp/s2.jsonl", "session_id": "abc-456", "backend": "claude"}
    ]
    monkeypatch.setattr(app, "discover_sessions", lambda **_kwargs: mock_sessions)
    monkeypatch.setattr(app.os.path, "exists", lambda p: False)
    
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "abc"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 1
    assert "Ambiguous ID" in capsys.readouterr().err

def test_id_resolution_not_found(monkeypatch, capsys):
    mock_sessions = [
        {"path": "/tmp/s1.jsonl", "session_id": "abc-123", "backend": "claude"}
    ]
    monkeypatch.setattr(app, "discover_sessions", lambda **_kwargs: mock_sessions)
    monkeypatch.setattr(app.os.path, "exists", lambda p: False)
    
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "xyz"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 1
    assert "File not found and no session matched ID" in capsys.readouterr().err

def test_id_resolution_prioritizes_exact_match_over_prefix_ambiguity(monkeypatch):
    # If we have "abc" and "abc-123", searching for "abc" should typically match "abc" exactly 
    # (though usually IDs are UUIDs or timestamps, having one as a prefix of another is rare but possible)
    mock_sessions = [
        {"path": "/tmp/s1.jsonl", "session_id": "abc", "backend": "claude"},
        {"path": "/tmp/s2.jsonl", "session_id": "abc-def", "backend": "claude"}
    ]
    monkeypatch.setattr(app, "discover_sessions", lambda **_kwargs: mock_sessions)
    monkeypatch.setattr(app.os.path, "exists", lambda p: False)
    
    mock_convert = MagicMock()
    monkeypatch.setattr(app, "convert", mock_convert)
    
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py", "abc"])
    app.main()
    
    mock_convert.assert_called_once()
    assert mock_convert.call_args[0][0] == "/tmp/s1.jsonl"
