# Agent Skill: Investigate Zed Agent Storage

**Objective**: Determine the current file system locations and database schemas used by Zed Editor's Agent Panel to store conversation history for external agents (Gemini, Claude, Codex, etc.).

**Trigger**: Run this skill when `as-i-was-saying` fails to locate recent sessions, or when Zed releases a major update that might affect storage paths.

## 1. Discovery Phase

**Goal**: Identify candidate directories and databases.

1.  **Inspect Zed Application Support:**
    ```bash
    ls -la ~/Library/Application\ Support/Zed/
    ```
    *Look for `threads/`, `db/`, `external_agents/`.*

2.  **Check First-Party Threads DB:**
    ```bash
    sqlite3 ~/Library/Application\ Support/Zed/threads/threads.db ".schema"
    ```
    *Verify table structure. Check if it contains external agent data or only first-party data (usually zstd compressed blobs).*

3.  **Check Key-Value Store (Metadata):**
    ```bash
    sqlite3 ~/Library/Application\ Support/Zed/db/0-stable/db.sqlite \
      "SELECT key, value FROM kv_store WHERE key LIKE '%agent%';"
    ```
    *Look for `recent-agent-threads` or similar keys containing UUIDs.*

## 2. UUID Cross-Reference

**Goal**: Find where the session content is actually stored by searching for UUIDs found in step 1.

1.  **Extract a UUID** from the `kv_store` or from the Zed UI (if accessible).
2.  **Search the Home Directory**:
    ```bash
    grep -r "YOUR_UUID_HERE" ~ --include="*.json" --include="*.jsonl" 2>/dev/null
    ```
    *Common locations:*
    *   `~/.gemini/tmp/...`
    *   `~/.claude/projects/...`
    *   `~/.codex/sessions/...`

## 3. Timestamp Correlation (Time-Based Signal Isolation)

**Goal**: Verify storage by correlating active usage with file modifications.

1.  **Isolate Activity**: Ensure no other CLI tools for the agent are running.
2.  **Generate Traffic**: Send a message to the agent in the Zed Panel.
3.  **Find Recently Modified Files**:
    ```bash
    # Example for Gemini
    find ~/.gemini -type f -mmin -5
    
    # Example for Claude
    find ~/.claude -type f -mmin -5
    ```
4.  **Verify Content**: Read the found file to confirm it contains the message you just sent.

## 4. Adapter Source Analysis (Optional)

**Goal**: Confirm logic if source code is available.

*   Look for `acp-agent.ts` (TypeScript) or `*.rs` (Rust) files in adapter repositories.
*   Search for "storage", "path", "home", or "session" keywords.

## Output Artifact

Produce a report containing:
1.  **Confirmed Locations**: The exact path patterns for each agent.
2.  **Format**: JSON, JSONL, SQLite, etc.
3.  **Persistence Behavior**: Real-time write vs. lazy write.
4.  **Breaking Changes**: What changed since the last snapshot?
