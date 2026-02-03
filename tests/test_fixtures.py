import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def iter_fixtures():
    for backend_dir in FIXTURES_DIR.iterdir():
        if not backend_dir.is_dir():
            continue
        backend = backend_dir.name
        for fixture_dir in backend_dir.iterdir():
            if fixture_dir.is_dir():
                yield backend, fixture_dir


def parse_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            json.loads(line)


def run_cli(path: Path, backend: Optional[str], mode_flag: Optional[str]):
    cmd = [sys.executable, str(REPO_ROOT / "as_i_was_saying.py"), str(path)]
    if backend and backend != "claude":
        cmd.extend(["--backend", backend])
    if mode_flag:
        cmd.append(mode_flag)
    return subprocess.run(cmd, capture_output=True, text=True)


def test_fixtures_are_valid_json():
    for _backend, fixture_dir in iter_fixtures():
        raw_path = fixture_dir / "raw.jsonl"
        assert raw_path.exists(), f"Missing raw fixture: {raw_path}"
        parse_jsonl(raw_path)


def test_fixtures_match_expected_outputs():
    for backend, fixture_dir in iter_fixtures():
        raw_path = fixture_dir / "raw.jsonl"
        expected_chat = fixture_dir / "expected_chat.md"
        expected_thoughts = fixture_dir / "expected_thoughts.md"
        expected_verbose = fixture_dir / "expected_verbose.md"

        if not expected_chat.exists():
            continue

        result = run_cli(raw_path, backend, None)
        assert result.returncode == 0, result.stderr
        assert result.stdout == expected_chat.read_text(encoding="utf-8")

        if expected_thoughts.exists():
            result = run_cli(raw_path, backend, "--thoughts")
            assert result.returncode == 0, result.stderr
            assert result.stdout == expected_thoughts.read_text(encoding="utf-8")

        if expected_verbose.exists():
            result = run_cli(raw_path, backend, "--verbose")
            assert result.returncode == 0, result.stderr
            assert result.stdout == expected_verbose.read_text(encoding="utf-8")
