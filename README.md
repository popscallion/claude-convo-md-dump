# claude-convo-md-dump

A lightweight tool to convert Claude Code JSONL transcripts into single-file Markdown transcripts.

## Usage

Installation:

```bash
uv tool install .
```

Run:

```bash
claude-md-dump <input.jsonl> [output.md] [--thoughts | --verbose]
```

## Modes

*   (Default) **Chat**: Clean text only. No tools or thinking blocks.
*   `--thoughts`: **Logic Flow**. Includes thinking blocks and tool inputs, but suppresses file dump outputs. Best for reviewing the agent's decision-making.
*   `--verbose`: **Full Record**. Includes everything.

## Credits

Inspired by [simonw/claude-code-transcripts](https://github.com/simonw/claude-code-transcripts).
