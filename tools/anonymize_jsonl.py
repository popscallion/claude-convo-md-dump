#!/usr/bin/env python3
"""Anonymize JSONL session logs for fixtures.

This script redacts common user identifiers while preserving structure.
It is intentionally conservative: it only replaces obvious identifiers
and truncates very large text blobs to keep fixtures small.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict

HOME_PATH_RE = re.compile(r"/Users/[^/]+")
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

DEFAULT_TRUNCATE = 2000


def _stable_token(value: str, prefix: str, mapping: Dict[str, str]) -> str:
    existing = mapping.get(value)
    if existing:
        return existing
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    token = f"{prefix}-{digest}"
    mapping[value] = token
    return token


def _redact_string(value: str, mappings: Dict[str, Dict[str, str]], max_len: int) -> str:
    if not value:
        return value

    # Normalize home paths
    value = HOME_PATH_RE.sub("/Users/USER", value)

    # Replace UUIDs with stable tokens
    def _uuid_repl(match: re.Match[str]) -> str:
        return _stable_token(match.group(0), "UUID", mappings["uuid"])

    value = UUID_RE.sub(_uuid_repl, value)

    # Truncate extremely long strings to keep fixtures small
    if len(value) > max_len:
        return value[: max_len // 2] + f"[TRUNCATED len={len(value)}]" + value[-max_len // 2 :]

    return value


def _redact(obj: Any, mappings: Dict[str, Dict[str, str]], max_len: int) -> Any:
    if isinstance(obj, dict):
        return {k: _redact(v, mappings, max_len) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v, mappings, max_len) for v in obj]
    if isinstance(obj, str):
        return _redact_string(obj, mappings, max_len)
    return obj


def anonymize_file(input_path: Path, output_path: Path, max_len: int) -> None:
    mappings: Dict[str, Dict[str, str]] = {
        "uuid": {},
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8") as src, output_path.open(
        "w", encoding="utf-8"
    ) as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            redacted = _redact(obj, mappings, max_len)
            dst.write(json.dumps(redacted, ensure_ascii=True, sort_keys=True))
            dst.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Anonymize a JSONL file for fixtures.")
    parser.add_argument("input", help="Input JSONL file")
    parser.add_argument("output", help="Output JSONL file")
    parser.add_argument(
        "--max-len",
        type=int,
        default=DEFAULT_TRUNCATE,
        help=f"Maximum length for string fields (default: {DEFAULT_TRUNCATE})",
    )

    args = parser.parse_args()
    anonymize_file(Path(args.input), Path(args.output), args.max_len)


if __name__ == "__main__":
    main()
