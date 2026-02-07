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


def get_fixture_path(fixture_dir: Path) -> Path:
    jsonl_path = fixture_dir / "raw.jsonl"
    if jsonl_path.exists():
        return jsonl_path
    json_path = fixture_dir / "raw.json"
    if json_path.exists():
        return json_path
    raise FileNotFoundError(f"No raw.jsonl or raw.json in {fixture_dir}")


def validate_fixture_file(path: Path):
    if path.suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                json.loads(line)
    else:
        with path.open("r", encoding="utf-8") as f:
            json.load(f)


def run_cli(path: Path, backend: Optional[str], mode_flag: Optional[str]):
    cmd = [sys.executable, str(REPO_ROOT / "as_i_was_saying.py"), str(path)]
    if backend and backend != "claude":
        cmd.extend(["--backend", backend])
    if mode_flag:
        cmd.append(mode_flag)
    return subprocess.run(cmd, capture_output=True, text=True)


def test_fixtures_are_valid_json():
    for _backend, fixture_dir in iter_fixtures():
        raw_path = get_fixture_path(fixture_dir)
        validate_fixture_file(raw_path)


def test_fixtures_match_expected_outputs():
    for backend, fixture_dir in iter_fixtures():
        try:
            raw_path = get_fixture_path(fixture_dir)
        except FileNotFoundError:
            continue
            
        expected_chat = fixture_dir / "expected_chat.md"
        expected_thoughts = fixture_dir / "expected_thoughts.md"
        expected_verbose = fixture_dir / "expected_verbose.md"

        if not expected_chat.exists():
            continue

        result = run_cli(raw_path, backend, None)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == expected_chat.read_text(encoding="utf-8").strip()

        if expected_thoughts.exists():
            result = run_cli(raw_path, backend, "--thoughts")
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip() == expected_thoughts.read_text(encoding="utf-8").strip()

        if expected_verbose.exists():
            result = run_cli(raw_path, backend, "--verbose")
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip() == expected_verbose.read_text(encoding="utf-8").strip()
