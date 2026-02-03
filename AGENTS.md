# AGENTS

This file defines development rules and architectural choices for this repo. It is authoritative for contributors and automated agents.

## Doc Boundary

- Root-level Markdown files are limited to `README.md` and `AGENTS.md`.
- User-facing guidance belongs in `README.md`.
- Developer policies, architectural decisions, and workflow mandates belong here.
- If behavior changes, update both docs in a coordinated way:
  - `README.md` for user-facing changes.
  - `AGENTS.md` for policy or architecture changes.

## Language and Tooling

- Python only. No JS or Node tooling.
- Use `uv` for environments, installs, and test runs. Do not use `pip` directly.
- Target Python `>=3.7`. Avoid 3.10+ syntax like `X | None`.
- Always use explicit `encoding="utf-8"` for file I/O.

## Architecture (Authoritative)

- Single renderer with backend normalization.
- Backends:
  - Claude is default.
  - Codex is selected with `--backend codex`.
  - Backend inference from file paths is allowed but explicit flags are preferred in docs and tests.
- Normalization rules:
  - Claude events map from `user`/`assistant` message blocks.
  - Codex events map from `response_item` and `event_msg` lines.
  - Codex `session_meta` and `turn_context` render as `meta` blocks.
- Unknown or unhandled blocks must never be silently dropped:
  - Render as a JSON block (or `meta` block) so data is preserved.
- Rendering modes remain consistent across backends:
  - `chat`: text only.
  - `thoughts`: include thinking and tool usage; omit tool outputs.
  - `verbose`: include full tool outputs.

## Fixtures and Anonymization

- Fixtures live in `tests/fixtures/`.
- Always anonymize source JSONL before committing fixtures:
  - Use `tools/anonymize_jsonl.py`.
  - Replace home paths, UUIDs, emails, and hostnames; truncate long strings.
  - Preserve JSON structure; write keys sorted for stable diffs.
- Keep `tests/fixtures/manifest.json` up to date.
- Regenerate expected outputs with:
  - `uv run python tools/regenerate_fixtures.py`

## Testing

- Use `pytest` and run via `uv`:
  - `uv venv`
  - `uv pip install -e '.[dev]'`
  - `uv run python -m pytest -q`
- If you change parsing or rendering, update fixtures and expected outputs.

## Pre-Commit Hook

- The repo uses `.githooks/pre-commit` and expects `core.hooksPath` to be set to `.githooks`.
- If hooks are missing, run:
  - `git config core.hooksPath .githooks`
- The pre-commit hook runs:
  - `uv lock --check`
  - `uv run python -m pytest -q`

## Change Discipline

- Do not silently change output formatting.
- If you must change output or behavior:
  - Update fixtures and expected outputs.
  - Update `README.md` for user-facing effects.
  - Update this file for architectural or workflow changes.

## Session Handoff

- Before concluding a session, reflect briefly on what was done and whether any improvements are available.
- Be proactive about next steps (e.g., offer to commit/push or update docs/tests when appropriate), rather than waiting for the user to ask.
