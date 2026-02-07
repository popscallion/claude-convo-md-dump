#!/usr/bin/env python3
"""Regenerate expected Markdown outputs for fixtures."""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional


def iter_fixtures(fixtures_root: Path, backend_filter: Optional[str], fixture_filter: Optional[str]):
    for backend_dir in fixtures_root.iterdir():
        if not backend_dir.is_dir():
            continue
        backend = backend_dir.name
        if backend_filter and backend != backend_filter:
            continue
        for fixture_dir in backend_dir.iterdir():
            if not fixture_dir.is_dir():
                continue
            if fixture_filter and fixture_filter not in str(fixture_dir):
                continue
            yield backend, fixture_dir


def run_cli(repo_root: Path, raw_path: Path, backend: str, mode_flag: Optional[str]) -> str:
    cmd = [sys.executable, str(repo_root / "as_i_was_saying.py"), str(raw_path)]
    if backend != "claude":
        cmd.extend(["--backend", backend])
    if mode_flag:
        cmd.append(mode_flag)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Command failed")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate expected Markdown outputs for fixtures.")
    parser.add_argument("--backend", choices=["claude", "codex", "gemini"], help="Limit to a backend")
    parser.add_argument("--fixture", help="Substring filter for fixture paths")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    fixtures_root = repo_root / "tests" / "fixtures"

    for backend, fixture_dir in iter_fixtures(fixtures_root, args.backend, args.fixture):
        raw_path = fixture_dir / "raw.jsonl"
        if not raw_path.exists():
            raw_path = fixture_dir / "raw.json"
        
        if not raw_path.exists():
            continue

        for mode, flag in [("chat", None), ("thoughts", "--thoughts"), ("verbose", "--verbose")]:
            try:
                output = run_cli(repo_root, raw_path, backend, flag)
                out_path = fixture_dir / f"expected_{mode}.md"
                out_path.write_text(output, encoding="utf-8")
                print(f"Regenerated {out_path}")
            except RuntimeError as e:
                print(f"Error regenerating {fixture_dir.name} ({mode}): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
