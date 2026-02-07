#!/usr/bin/env python3
"""Anonymize JSONL session logs for fixtures.

This script redacts common user identifiers while preserving structure.
It is intentionally conservative: it only replaces obvious identifiers
and truncates very large text blobs to keep fixtures small.
"""

import argparse
import json
from pathlib import Path

from redaction import Redactor

DEFAULT_TRUNCATE = 2000


def anonymize_file(input_path: Path, output_path: Path, max_len: int) -> None:
    redactor = Redactor(max_len=max_len)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if input_path.suffix == ".json":
        # Handle single JSON object (Gemini)
        with input_path.open("r", encoding="utf-8") as src:
            data = json.load(src)
            redacted = redactor.redact(data)
        
        with output_path.open("w", encoding="utf-8") as dst:
            json.dump(redacted, dst, indent=2, ensure_ascii=True, sort_keys=True)
            dst.write("\n")
    else:
        # Handle JSONL (Claude/Codex)
        with input_path.open("r", encoding="utf-8") as src, output_path.open(
            "w", encoding="utf-8"
        ) as dst:
            for line in src:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    redacted = redactor.redact(obj)
                    dst.write(json.dumps(redacted, ensure_ascii=True, sort_keys=True))
                    dst.write("\n")
                except json.JSONDecodeError:
                    continue


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
