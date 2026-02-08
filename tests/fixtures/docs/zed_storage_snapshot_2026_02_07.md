# Zed Agent Storage Snapshot (2026-02-07)

**Status**: Verified
**Platform**: macOS Darwin 25.2.0

## Confirmed Storage Locations

| Agent | Storage Location Pattern | Format | Notes |
|-------|--------------------------|--------|-------|
| **Gemini** | `~/.gemini/tmp/<hash>/chats/session-*.json` | JSON | Single object. `<hash>` is SHA256 of project path. |
| **Claude Code** | `~/.claude/projects/<encoded-path>/<session-id>.jsonl` | JSONL | Adapts standard Claude CLI storage. |
| **Codex** | `~/.codex/sessions/<date>/rollout-*.jsonl` | JSONL | Adapts standard Codex CLI storage. |

## Internal Zed Databases

*   **`~/Library/Application Support/Zed/threads/threads.db`**:
    *   **Content**: Zed's first-party AI threads ONLY.
    *   **Format**: SQLite with zstd-compressed blobs.
    *   **Relevance**: Irrelevant for external agents (Gemini, Claude, Codex).

*   **`~/Library/Application Support/Zed/db/0-stable/db.sqlite`**:
    *   **Content**: UI state and metadata.
    *   **Key**: `recent-agent-threads` in `kv_store` table contains UUIDs.
    *   **Relevance**: Useful for finding *recent* UUIDs, but **not reliable** for finding the *active* session in real-time (lazy persistence).

## Integration Notes

*   **Unified Storage**: Zed does not maintain a separate store for external agents; it delegates storage to the agent's own CLI/SDK adapter.
*   **Discovery**: The reliable method to find the active Zed session is to scan the agent's standard storage directory for the most recently modified file matching the current project context.
