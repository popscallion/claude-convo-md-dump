# as-i-was-saying

A small CLI that turns Claude or Codex JSONL session logs into a single Markdown transcript.

**Philosophy**
- Human-readable output over clever formatting.
- One renderer, consistent modes, and no silent data loss.
- Resilient to schema changes by preserving unknown blocks.

## Usage

**Interactive picker (Claude by default)**
```bash
as-i-was-saying
```

**Convert a specific file**
```bash
as-i-was-saying path/to/session.jsonl
as-i-was-saying path/to/session.jsonl output.md
```

## Backends

Claude is the default backend. Codex sessions require `--backend codex`.

```bash
as-i-was-saying --backend codex ~/.codex/sessions/2026/01/27/rollout-...jsonl
```

If you pass a file path under `~/.codex/sessions` or `~/.claude/projects`, the tool will infer the backend automatically.

## Modes

- `chat` (default): text-only, no thinking or tool output.
- `thoughts`: includes thinking and tool usage, omits tool outputs.
- `verbose`: includes all thinking and full tool outputs.

```bash
as-i-was-saying --thoughts path/to/session.jsonl
as-i-was-saying --verbose path/to/session.jsonl
```

## Data Locations

- Claude: `~/.claude/projects`
- Codex: `~/.codex/sessions`

## Development

Testing uses `uv`:
```bash
uv venv
uv pip install -e '.[dev]'
uv run python -m pytest -q
```

Fixtures are anonymized JSONL samples under `tests/fixtures/` with expected outputs.
Regenerate expected outputs with:
```bash
uv run python tools/regenerate_fixtures.py
```

## Credits

Inspired by [simonw/claude-code-transcripts](https://github.com/simonw/claude-code-transcripts).

## License

GPL-3.0-only. See `LICENSE`.
