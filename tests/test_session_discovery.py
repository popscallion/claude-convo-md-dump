import pytest

import as_i_was_saying as app


def test_parse_since_cutoff_accepts_supported_units():
    day_cutoff = app.parse_since_cutoff("1d")
    week_cutoff = app.parse_since_cutoff("1w")
    hour_cutoff = app.parse_since_cutoff("12h")

    assert isinstance(day_cutoff, float)
    assert isinstance(week_cutoff, float)
    assert isinstance(hour_cutoff, float)
    assert week_cutoff < day_cutoff
    assert hour_cutoff > day_cutoff


def test_parse_since_cutoff_rejects_invalid_values():
    with pytest.raises(ValueError):
        app.parse_since_cutoff("yesterday")
    with pytest.raises(ValueError):
        app.parse_since_cutoff("2m")


def test_rank_sessions_without_query_is_mtime_desc_then_path():
    sessions = [
        {"path": "b", "mtime": 100, "backend": "claude"},
        {"path": "a", "mtime": 100, "backend": "claude"},
        {"path": "z", "mtime": 200, "backend": "claude"},
    ]
    ranked = app.rank_sessions(sessions)
    assert [s["path"] for s in ranked] == ["z", "b", "a"]


def test_rank_sessions_with_query_uses_match_count_then_recency(monkeypatch):
    sessions = [
        {"path": "one", "mtime": 100, "backend": "claude"},
        {"path": "two", "mtime": 300, "backend": "codex"},
        {"path": "three", "mtime": 200, "backend": "gemini"},
    ]
    counts = {"one": 3, "two": 3, "three": 1}

    def fake_analyze(path, _backend, _query):
        return counts[path], "ctx"

    monkeypatch.setattr(app, "analyze_session_query", fake_analyze)
    ranked = app.rank_sessions(sessions, "auth")

    assert [s["path"] for s in ranked] == ["two", "one", "three"]
    assert ranked[0]["match_count"] == 3


def test_emit_sessions_tsv_outputs_header_and_row(capsys):
    sessions = [
        {
            "backend": "claude",
            "mtime": 1735689600,
            "size": 1234,
            "match_count": 2,
            "display_id": "abcd1234",
            "path": "/tmp/a.jsonl",
            "summary": "hello",
        }
    ]
    app.emit_sessions_tsv(sessions)
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0] == "backend\ttimestamp\tsize_bytes\tsize_display\tmatch_count\tsession_id\tpath\tsummary"
    assert out[1].startswith("claude\t")
    assert "\t1234\t  1.2KB\t2\tabcd1234\t/tmp/a.jsonl\thello" in out[1]


def test_format_size_is_fixed_width_with_unit():
    values = [1, 1234, 999_949, 999_950, 1_234_567_890]
    rendered = [app.format_size(v) for v in values]
    assert all(len(x) == 7 for x in rendered)
    assert rendered[2].endswith("KB")
    assert rendered[3].endswith("MB")
    assert rendered[4].endswith("GB")


def test_assign_display_ids_fixed_8_chars():
    sessions = [
        {"session_id": "abcdef012345"},
        {"session_id": "abcdef999999"},
        {"session_id": "abc999777777"},
    ]
    app.assign_display_ids(sessions, max_len=8)

    assert sessions[0]["display_id"] == "abcdef01"
    assert sessions[1]["display_id"] == "abcdef99"
    assert sessions[2]["display_id"] == "abc99977"
    assert len(sessions[2]["display_id"]) == 8


def test_extract_session_id_backend_normalization():
    from pathlib import Path

    claude = app.extract_session_id(
        Path("/tmp/b9fc3ac2-040e-4502-b940-b28894e6661e.jsonl"), "claude"
    )
    codex = app.extract_session_id(
        Path("/tmp/rollout-2026-02-09T15-10-02-019c4406-8031-7130-a1ab-657bc80bb228.jsonl"),
        "codex",
    )
    gemini = app.extract_session_id(
        Path("/tmp/session-2026-02-09T20-05-813001ce.json"),
        "gemini",
    )

    assert claude == "b9fc3ac2"
    assert codex == "657bc80bb228"
    assert gemini == "813001ce"


def test_get_session_context_jsonl_latest_and_earliest(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"type":"user","message":{"content":"first question"}}',
                '{"type":"assistant","message":{"content":"answer"}}',
                '{"type":"user","message":{"content":"last question"}}',
            ]
        ),
        encoding="utf-8",
    )
    latest, earliest = app.get_session_context(str(path), "claude")
    assert latest == "last question"
    assert earliest == "first question"


def test_analyze_session_query_returns_count_and_context(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text(
        '{"type":"user","message":{"content":"auth auth and session context"}}\n',
        encoding="utf-8",
    )
    count, context = app.analyze_session_query(str(path), "claude", "auth")
    assert count == 2
    assert "auth" in context.lower()


def test_list_context_columns_swaps_in_query_mode():
    session = {
        "latest_summary": "latest",
        "earliest_summary": "earliest",
        "match_context": "matched",
    }
    p1, s1 = app.list_context_columns(session, query_mode=False)
    assert p1 == "latest"
    assert s1 == "earliest"

    p2, s2 = app.list_context_columns(session, query_mode=True)
    assert p2 == "latest"
    assert s2 == "matched"


def test_format_context_column_fixed_width():
    short = app.format_context_column("abc", width=8)
    assert short == "abc     "
    long = app.format_context_column("abcdefghijk", width=8)
    assert len(long) == 8


def test_session_id_for_path_codex_falls_back_to_filename_uuid(tmp_path):
    session = tmp_path / "rollout-2026-02-10T10-15-39-019d34ab-1234-5678-abcd-1234567890ef.jsonl"
    session.write_text('{"type":"user","message":{"content":"x"}}\n', encoding="utf-8")
    sid = app.session_id_for_path(str(session), "codex")
    assert sid == "019d34ab-1234-5678-abcd-1234567890ef"


def test_session_id_for_path_gemini_falls_back_to_stem_when_no_uuid(tmp_path):
    session = tmp_path / "session-2026-02-10T10-15-39-abc12345.json"
    session.write_text("{}", encoding="utf-8")
    sid = app.session_id_for_path(str(session), "gemini")
    assert sid == "2026-02-10T10-15-39-abc12345"


def test_session_id_for_path_claude_agent_prefix_fallback(tmp_path):
    session = tmp_path / "agent-xyz123.jsonl"
    session.write_text("", encoding="utf-8")
    sid = app.session_id_for_path(str(session), "claude")
    assert sid == "xyz123"
