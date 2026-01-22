# claude-convo-md-dump

A lightweight tool to convert Claude Code JSONL transcripts into single-file Markdown transcripts.

## Usage

### Interactive Mode (Recommended)

Run without arguments to see a list of recent sessions:

```bash
claude-md-dump
```

Select a session number, and the Markdown will be printed to stdout.

**Tip:** Pipe to your clipboard or a file:

```bash
# Copy to clipboard (Mac)
claude-md-dump | pbcopy

# Save to file
claude-md-dump > transcript.md
```

### Direct File Mode

Convert a specific file:

```bash
claude-md-dump path/to/session.jsonl [output.md]
```

## Modes

*   (Default) **Chat**: Clean text only. No tools or thinking blocks.
*   `--thoughts`: **Logic Flow**. Includes thinking blocks and tool inputs, but suppresses file dump outputs. Best for reviewing the agent's decision-making.
*   `--verbose`: **Full Record**. Includes everything.

## Features

*   **Smart Filtering:** Automatically hides "ghost" sessions (warmups or failed starts with no user prompts).
*   **Clean Summaries:** Shows the first user prompt in the interactive list.
*   **Stdio Friendly:** Interactive menu prints to stderr, so you can safely redirect stdout (Markdown) to files or pipes.

## Credits

Inspired by [simonw/claude-code-transcripts](https://github.com/simonw/claude-code-transcripts).
