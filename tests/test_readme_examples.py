import json
import re
import sys
from pathlib import Path

import pytest

import as_i_was_saying as app


README_EXAMPLE_CASES = {
    "as-i-was-saying": "interactive_default",
    "as-i-was-saying path/to/session.jsonl": "convert_path",
    "as-i-was-saying path/to/session.jsonl output.md": "convert_to_output",
    "as-i-was-saying --emit path": "emit_path",
    "as-i-was-saying --emit id": "emit_id",
    "as-i-was-saying path/to/session.jsonl | pbcopy": "pipe_output",
    "as-i-was-saying path/to/session.jsonl | wl-copy": "pipe_output",
    "as-i-was-saying path/to/session.jsonl | xclip -selection clipboard": "pipe_output",
    "as-i-was-saying --list | fzf | cut -f7 | xargs -I{} as-i-was-saying \"{}\"": "list_tsv",
    "as-i-was-saying path/to/session.jsonl | fzf": "pipe_output",
    "as-i-was-saying --backend gemini --emit id | xargs -I{} gemini --resume {}": "emit_gemini_id",
    "as-i-was-saying -n 5": "tail",
    "as-i-was-saying --head 2": "head",
    "as-i-was-saying --latest": "latest",
    "as-i-was-saying -l": "latest_short",
    "as-i-was-saying 5a3b2c": "id_lookup",
    "as-i-was-saying --query auth": "query_interactive",
    "as-i-was-saying --query auth --since 1d": "query_interactive_since",
    "as-i-was-saying --query auth --all-time": "query_interactive_all_time",
    "as-i-was-saying --query auth --list": "query_list",
    "as-i-was-saying --backend codex ~/.codex/sessions/2026/01/27/rollout-...jsonl": "backend_codex",
    "as-i-was-saying --backend gemini ~/.gemini/tmp/.../chats/session-...json": "backend_gemini",
    "as-i-was-saying --thoughts path/to/session.jsonl": "mode_thoughts",
    "as-i-was-saying --verbose path/to/session.jsonl": "mode_verbose",
    "as-i-was-saying --mode verbose path/to/session.jsonl": "mode_verbose_long",
}


class _TTYIn:
    @staticmethod
    def isatty():
        return True


def _extract_readme_cli_commands():
    text = Path("README.md").read_text(encoding="utf-8")
    commands = []
    for block in re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL):
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if line.startswith("as-i-was-saying"):
                commands.append(line)
    return commands


def _run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["as_i_was_saying.py"] + argv)
    try:
        app.main()
        return 0
    except SystemExit as exc:
        return exc.code


def _make_claude_session(tmp_path):
    path = tmp_path / "b9fc3ac2-040e-4502-b940-b28894e6661e.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"type":"user","timestamp":"2026-01-01T00:00:00Z","message":{"content":"first"}}',
                '{"type":"assistant","timestamp":"2026-01-01T00:00:01Z","message":{"content":"second"}}',
            ]
        ),
        encoding="utf-8",
    )
    return path


def _make_codex_session(tmp_path):
    path = tmp_path / "rollout-2026-02-09T15-10-02-019c4406-8031-7130-a1ab-657bc80bb228.jsonl"
    path.write_text(
        '{"type":"session_meta","payload":{"id":"019c4406-8031-7130-a1ab-657bc80bb228"}}\n'
        '{"type":"event_msg","timestamp":"t","payload":{"type":"user_message","text":"u"}}\n',
        encoding="utf-8",
    )
    return path


def _make_gemini_session(tmp_path):
    path = tmp_path / "session-2026-02-09T20-05-813001ce.json"
    path.write_text(
        json.dumps(
            {
                "sessionId": "3ebe0729-869b-4760-9151-d5abf44957c6",
                "messages": [{"type": "user", "timestamp": "t", "content": "hello"}],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_readme_examples_all_have_test_cases():
    commands = _extract_readme_cli_commands()
    assert set(commands) == set(README_EXAMPLE_CASES.keys())


@pytest.mark.parametrize(
    "command,case",
    sorted(README_EXAMPLE_CASES.items()),
    ids=lambda item: item[0] if isinstance(item, tuple) else str(item),
)
def test_readme_example_case_behaviors(command, case, monkeypatch, tmp_path, capsys):
    claude = _make_claude_session(tmp_path)
    codex = _make_codex_session(tmp_path)
    gemini = _make_gemini_session(tmp_path)

    if case == "interactive_default":
        calls = {}

        def fake_select_session(**kwargs):
            calls["kwargs"] = kwargs
            return str(claude)

        def fake_convert(filepath, output_file, mode, backend, redaction, tail, head):
            calls["convert"] = (filepath, mode, backend)

        monkeypatch.setattr(sys, "stdin", _TTYIn())
        monkeypatch.setattr(app, "select_session", fake_select_session)
        monkeypatch.setattr(app, "convert", fake_convert)
        assert _run_main(monkeypatch, []) == 0
        assert calls["convert"][0] == str(claude)
        return

    if case == "convert_path":
        assert _run_main(monkeypatch, [str(claude)]) == 0
        assert "first" in capsys.readouterr().out
        return

    if case == "convert_to_output":
        out = tmp_path / "out.md"
        assert _run_main(monkeypatch, [str(claude), str(out)]) == 0
        assert out.exists()
        assert "first" in out.read_text(encoding="utf-8")
        return

    if case == "emit_path":
        monkeypatch.setattr(sys, "stdin", _TTYIn())
        monkeypatch.setattr(app, "select_session", lambda **_kwargs: str(claude))
        assert _run_main(monkeypatch, ["--emit", "path"]) == 0
        assert capsys.readouterr().out.strip() == str(claude)
        return

    if case == "emit_id":
        monkeypatch.setattr(sys, "stdin", _TTYIn())
        monkeypatch.setattr(app, "select_session", lambda **_kwargs: str(codex))
        monkeypatch.setattr(app, "infer_backend_from_path", lambda _path: "codex")
        assert _run_main(monkeypatch, ["--emit", "id"]) == 0
        assert capsys.readouterr().out.strip() == "019c4406-8031-7130-a1ab-657bc80bb228"
        return

    if case == "pipe_output":
        assert _run_main(monkeypatch, [str(claude)]) == 0
        assert "# Transcript:" in capsys.readouterr().out
        return

    if case == "list_tsv":
        monkeypatch.setattr(
            app,
            "discover_sessions",
            lambda **_kwargs: [
                {
                    "backend": "claude",
                    "mtime": 1735689600,
                    "size": 1234,
                    "display_id": "abcd1234",
                    "path": str(claude),
                    "summary": "hello",
                }
            ],
        )
        assert _run_main(monkeypatch, ["--list"]) == 0
        out = capsys.readouterr().out
        assert "backend\ttimestamp\tsize_bytes" in out
        assert str(claude) in out
        return

    if case == "emit_gemini_id":
        assert _run_main(monkeypatch, ["--backend", "gemini", str(gemini), "--emit", "id"]) == 0
        assert capsys.readouterr().out.strip() == "3ebe0729-869b-4760-9151-d5abf44957c6"
        return

    if case == "tail":
        assert _run_main(monkeypatch, [str(claude), "-n", "1"]) == 0
        out = capsys.readouterr().out
        assert "second" in out
        assert "first" not in out
        return

    if case == "head":
        assert _run_main(monkeypatch, [str(claude), "--head", "1"]) == 0
        out = capsys.readouterr().out
        assert "first" in out
        assert "second" not in out
        return

    if case in {"latest", "latest_short"}:
        monkeypatch.setattr(
            app,
            "discover_sessions",
            lambda **_kwargs: [{"path": str(claude), "mtime": 100, "backend": "claude"}],
        )
        flag = "--latest" if case == "latest" else "-l"
        assert _run_main(monkeypatch, [flag]) == 0
        assert "# Transcript:" in capsys.readouterr().out
        return

    if case == "id_lookup":
        monkeypatch.setattr(
            app,
            "discover_sessions",
            lambda **_kwargs: [
                {
                    "path": str(claude),
                    "session_id": "5a3b2c-full-id",
                    "backend": "claude",
                }
            ],
        )
        
        def fake_exists(path):
            return str(path) != "5a3b2c"

        monkeypatch.setattr(app.os.path, "exists", fake_exists)
        assert _run_main(monkeypatch, ["5a3b2c"]) == 0
        assert "# Transcript:" in capsys.readouterr().out
        return

    if case in {"query_interactive", "query_interactive_since", "query_interactive_all_time"}:
        calls = {}

        def fake_select_session(**kwargs):
            calls.update(kwargs)
            return str(claude)

        monkeypatch.setattr(sys, "stdin", _TTYIn())
        monkeypatch.setattr(app, "select_session", fake_select_session)
        monkeypatch.setattr(app, "convert", lambda *args, **kwargs: None)
        if case == "query_interactive":
            assert _run_main(monkeypatch, ["--query", "auth"]) == 0
            assert calls.get("query") == "auth"
            assert calls.get("since_label") == "1w"
        elif case == "query_interactive_since":
            assert _run_main(monkeypatch, ["--query", "auth", "--since", "1d"]) == 0
            assert calls.get("since_label") == "1d"
        else:
            assert _run_main(monkeypatch, ["--query", "auth", "--all-time"]) == 0
            assert calls.get("since_label") == "all-time"
        return

    if case == "query_list":
        monkeypatch.setattr(
            app,
            "discover_sessions",
            lambda **_kwargs: [
                {
                    "backend": "claude",
                    "mtime": 1735689600,
                    "size": 1234,
                    "match_count": 2,
                    "display_id": "abcd1234",
                    "path": str(claude),
                    "summary": "auth details",
                }
            ],
        )
        assert _run_main(monkeypatch, ["--query", "auth", "--list"]) == 0
        assert "auth details" in capsys.readouterr().out
        return

    if case == "backend_codex":
        assert _run_main(monkeypatch, ["--backend", "codex", str(codex)]) == 0
        assert "# Transcript:" in capsys.readouterr().out
        return

    if case == "backend_gemini":
        assert _run_main(monkeypatch, ["--backend", "gemini", str(gemini)]) == 0
        assert "# Transcript:" in capsys.readouterr().out
        return

    if case == "mode_thoughts":
        assert _run_main(monkeypatch, ["--thoughts", str(claude)]) == 0
        assert "Mode: thoughts" in capsys.readouterr().out
        return

    if case == "mode_verbose":
        assert _run_main(monkeypatch, ["--verbose", str(claude)]) == 0
        assert "Mode: verbose" in capsys.readouterr().out
        return

    if case == "mode_verbose_long":
        assert _run_main(monkeypatch, ["--mode", "verbose", str(claude)]) == 0
        assert "Mode: verbose" in capsys.readouterr().out
        return

    raise AssertionError("Unhandled README example case: {0}".format(case))
