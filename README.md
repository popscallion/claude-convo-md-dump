# as-i-was-saying

A small CLI that turns Claude, Codex, or Gemini session logs into a single Markdown transcript.

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

**Filter Output**
Limit to the most recent messages (`-n` / `--tail`) or the first messages (`--head`).
Note: These flags count messages containing text, ignoring tool-only turns.
```bash
# Show only the last 5 messages
as-i-was-saying -n 5

# Show the first 2 messages
as-i-was-saying --head 2
```

## Install to PATH (optional)

Use `uv` to install the CLI and add it to your shell PATH:
```bash
uv tool install --editable .
uv tool update-shell
```

Restart your shell after updating PATH. You can also add the tool directory manually:
```bash
uv tool dir
```

To uninstall:
```bash
uv tool uninstall as-i-was-saying
```

## Backends

Claude is the default backend. Codex and Gemini sessions require specifying the backend or using a path that allows inference.

```bash
as-i-was-saying --backend codex ~/.codex/sessions/2026/01/27/rollout-...jsonl
as-i-was-saying --backend gemini ~/.gemini/tmp/.../chats/session-...json
```

If you pass a file path under `~/.codex/sessions`, `~/.claude/projects`, or `~/.gemini/tmp`, the tool will infer the backend automatically.

## Modes

- `chat` (default): text-only, no thinking or tool output.
- `thoughts`: includes thinking and tool usage, omits tool outputs.
- `verbose`: includes all thinking and full tool outputs.

```bash
as-i-was-saying --thoughts path/to/session.jsonl
as-i-was-saying --verbose path/to/session.jsonl
as-i-was-saying --mode verbose path/to/session.jsonl
```

## Redaction

- `--redact`: pattern-based redaction of common identifiers in output.
- `--redact-strict`: more aggressive redaction (may over-redact useful context).
- `--redact-level {standard|strict|none}`: explicit redaction level selection.

Redaction is opt-in and prints loud warnings in the output. It is not guaranteed to catch every secret.

## Data Locations

The tool automatically detects sessions in these default locations. You can override them by setting the corresponding environment variable.

- **Claude**: `~/.claude/projects` (Override: `CLAUDE_LOG_DIR`)
- **Codex**: `~/.codex/sessions` (Override: `CODEX_LOG_DIR`)
- **Gemini**: `~/.gemini/tmp` (Override: `GEMINI_LOG_DIR`)

## Known Limitations

- Codex `reasoning` entries are rendered from the summary when available; encrypted content is not shown.
- If a backend emits a new block type, it will appear as raw JSON until normalization is updated.
- `chat` mode omits tool-only turns (those without text blocks).
- Backend inference is path-based; if logs are moved, pass `--backend` explicitly.

## Privacy Notes

- Fixtures are anonymized, but logs can still contain sensitive data.
- Anonymization is pattern-based and not guaranteed to catch every secret; review before sharing.
- The anonymizer also redacts bare domains, IP addresses, and common token formats, which may over-redact legitimate text.
- Do not publish raw logs; anonymize before sharing or opening a PR.
- Keep fixtures minimal (single short session per backend) and trim large tool outputs.
- If you fork this repo and are not contributing back, keep the fork private.
- If you scrub history, delete any remote tags or branches that still reference pre-scrub commits.
- Anonymized fixtures are not guaranteed safe for public posting.

**Fixture Checklist**
Run these scans before committing fixtures:
```bash
rg -n "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}" tests/fixtures
rg -n "https?://" tests/fixtures | rg -n -v "https?://HOST-"
rg -n "\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b" tests/fixtures
rg -n "\\b(?:[0-9A-Fa-f]{1,4}:){2,}[0-9A-Fa-f]{1,4}\\b" tests/fixtures
rg -n "\\b(sk-[A-Za-z0-9]{10,}|sk_live_[A-Za-z0-9]{10,}|gh[opurs]_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|A(?:KIA|SIA)[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|ya29\\.[0-9A-Za-z_-]+)\\b" tests/fixtures
```

## Maintenance & Agent Skills

This repo includes "Agent Skills" to assist with maintenance when schemas change.

- **Storage Investigator**: `skills/investigate_zed_storage.md`
    - Use this skill to rediscover log locations if Zed or an agent backend changes its storage strategy.
    - Findings are snapshotted in `tests/fixtures/docs/`.

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

The pre-commit hook runs `uv lock --check`, `pytest`, and privacy scans against `tests/fixtures`.

### History Scrub (if needed)

If you ever need to purge sensitive fixture history, use `git filter-repo` and force-push:

```bash
git filter-repo --path tests/fixtures --invert-paths

git push --force --all
git push --force --tags
```

Then re-add sanitized fixtures and regenerate outputs.

## Credits

Inspired by [simonw/claude-code-transcripts](https://github.com/simonw/claude-code-transcripts).

## Roadmap (v2)

The current version (v0.2.0) focuses on robust parsing and simple recent-session discovery. Future versions aims to improve retrieval:

- **Unified Search**: Search across all backends simultaneously.
- **Content Search**: Fuzzy finding within conversation content (not just summaries).
- **Turn-based Retrieval**: Ability to extract specific turns rather than full sessions.
- **Date Filtering**: Scoped searches (e.g., `--since 2d`).

**Implementation Notes:**
- The current backend-agnostic architecture (`backends.py`) makes adding new sources (like OpenAI or local LLMs) straightforward.
- Performance: Standard `rg` and `fzf` integration is preferred over building a custom indexing database for now.

## License

GPL-3.0-only. See `LICENSE`.
