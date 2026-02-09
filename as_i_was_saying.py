import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from redaction import Redactor
from backends import normalize_event
from models import Event

# Mode documentation for both CLI help and Output headers
MODE_DESCRIPTIONS = {
    "chat": "Conversation text only. No thinking blocks or tool details.",
    "thoughts": "Logic flow. Includes thinking and tool usage. Tool outputs are summarized.",
    "verbose": "Full record. Includes all thinking, tool usage, and full tool outputs.",
}

SUPPORTED_BACKENDS = ("claude", "codex", "gemini")


def format_timestamp(ts_str: str) -> str:
    try:
        # Handle formats like 2026-01-21T21:13:13.514Z
        if not ts_str:
            return ""
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts_str


def get_base_dir(backend: str) -> Path:
    if backend == "codex":
        env_path = os.getenv("CODEX_LOG_DIR")
        return Path(env_path) if env_path else Path.home() / ".codex" / "sessions"
    if backend == "gemini":
        env_path = os.getenv("GEMINI_LOG_DIR")
        return Path(env_path) if env_path else Path.home() / ".gemini" / "tmp"
    
    env_path = os.getenv("CLAUDE_LOG_DIR")
    return Path(env_path) if env_path else Path.home() / ".claude" / "projects"


def infer_backend_from_path(path: str) -> Optional[str]:
    if not path:
        return None
    expanded = str(Path(path).expanduser())
    codex_base = str(get_base_dir("codex"))
    claude_base = str(get_base_dir("claude"))
    gemini_base = str(get_base_dir("gemini"))
    if expanded.startswith(codex_base):
        return "codex"
    if expanded.startswith(claude_base):
        return "claude"
    if expanded.startswith(gemini_base):
        return "gemini"
    return None


def extract_text_from_blocks(blocks: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for block in blocks:
        if block.get("type") == "text":
            text = block.get("text", "")
            if text:
                parts.append(text)
    return " ".join(parts).strip()


def get_session_summary(filepath: str, backend: str) -> Optional[str]:
    """Read first user message from session file"""
    try:
        # Gemini is a single JSON file, not JSONL
        if backend == "gemini":
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                messages = data.get("messages", [])
                for msg in messages:
                    events = normalize_event(msg, backend)
                    for event in events:
                        if event.get("role") != "user":
                            continue
                        text = extract_text_from_blocks(event.get("blocks", []))
                        if text:
                            return text
            return None

        # Claude/Codex (JSONL)
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue

                events = normalize_event(data, backend)
                for event in events:
                    if event.get("role") != "user":
                        continue
                    text = extract_text_from_blocks(event.get("blocks", []))
                    if text and not text.startswith("<"):
                        return text
    except Exception:
        pass
    return None


def find_recent_sessions(backend: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Scan backend directory for recent sessions"""
    base_dir = get_base_dir(backend)
    if not base_dir.exists():
        return []

    sessions: List[Dict[str, Any]] = []
    
    # Gemini optimization: Scan top project directories first
    if backend == "gemini":
        # Get all project directories
        project_dirs = []
        try:
            for entry in base_dir.iterdir():
                if entry.is_dir():
                    project_dirs.append(entry)
        except OSError:
            pass
            
        # Sort by mtime descending
        project_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Limit to top 20 most recent projects
        search_dirs = project_dirs[:20]
        
        for p_dir in search_dirs:
            chats_dir = p_dir / "chats"
            if not chats_dir.exists():
                continue
            for path in chats_dir.glob("session-*.json"):
                try:
                    stat = path.stat()
                    sessions.append({"path": path, "mtime": stat.st_mtime, "size": stat.st_size})
                except OSError:
                    continue
    else:
        # Standard recursive scan for other backends
        for path in base_dir.rglob("*.jsonl"):
            if backend == "claude" and "agent-" in path.name:
                continue

            try:
                stat = path.stat()
                sessions.append({"path": path, "mtime": stat.st_mtime, "size": stat.st_size})
            except OSError:
                continue

    sessions.sort(key=lambda x: x["mtime"], reverse=True)

    valid_sessions: List[Dict[str, Any]] = []
    candidates = sessions[: limit * 2]

    for s in candidates:
        raw_summary = get_session_summary(str(s["path"]), backend)
        if not raw_summary:
            continue

        clean_summary = raw_summary.replace("\n", " ").strip()
        if len(clean_summary) > 60:
            clean_summary = clean_summary[:57] + "..."
        s["summary"] = clean_summary
        valid_sessions.append(s)

        if len(valid_sessions) >= limit:
            break

    return valid_sessions


def collect_all_sessions(limit_per_backend: int = 50) -> List[Dict[str, Any]]:
    """Aggregate recent sessions from all supported backends."""
    all_sessions = []
    for backend in SUPPORTED_BACKENDS:
        sessions = find_recent_sessions(backend, limit=limit_per_backend)
        for s in sessions:
            s["backend"] = backend
        all_sessions.extend(sessions)
    
    # Sort unified list by time (newest first)
    all_sessions.sort(key=lambda x: x["mtime"], reverse=True)
    return all_sessions


def fzf_select(sessions: List[Dict[str, Any]]) -> Optional[str]:
    """Use fzf to select a session from the list."""
    fzf = shutil.which("fzf")
    if not fzf:
        return None

    # Format lines for fzf: "[BACKEND] YYYY-MM-DD HH:MM | Summary"
    lines = []
    map_lines = {}
    
    for s in sessions:
        dt = datetime.fromtimestamp(s["mtime"]).strftime("%Y-%m-%d %H:%M")
        # Pad backend name for alignment
        bk = s['backend'].upper()
        summary = s.get('summary', 'No summary')
        line = f"[{bk:<6}] {dt} | {summary}"
        lines.append(line)
        map_lines[line] = str(s["path"])

    try:
        proc = subprocess.Popen(
            [fzf, "--no-sort", "--header", "Select a session (most recent first)"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, _ = proc.communicate(input="\n".join(lines))
        
        if proc.returncode == 0 and stdout.strip():
            selected = stdout.strip()
            return map_lines.get(selected)
    except Exception:
        pass
        
    return None


def select_session(backend: Optional[str] = None) -> str:
    """Interactive session selector.
    
    If backend is provided, limits to that backend.
    Otherwise, aggregates all backends.
    """
    if backend:
        sessions = find_recent_sessions(backend)
        if not sessions:
            print(f"No {backend.title()} sessions found in {get_base_dir(backend)}", file=sys.stderr)
            sys.exit(1)
        # Tag them for consistency
        for s in sessions:
            s["backend"] = backend
    else:
        sessions = collect_all_sessions()
        if not sessions:
            print("No sessions found in any backend.", file=sys.stderr)
            sys.exit(1)

    # Try fzf first
    path = fzf_select(sessions)
    if path:
        return path

    # Fallback to simple numeric menu
    print(f"\nRecent Sessions:", file=sys.stderr)
    
    display_limit = 20
    for i, s in enumerate(sessions[:display_limit]):
        dt = datetime.fromtimestamp(s["mtime"]).strftime("%Y-%m-%d %H:%M")
        size_kb = f"{s['size'] / 1024:.0f}KB"
        bk = s['backend'].upper()
        print(f"{i+1:2}. [{bk:<6}] {dt} ({size_kb:>5})  {s['summary']}", file=sys.stderr)

    while True:
        try:
            sys.stderr.write(f"\nSelect session (1-{min(len(sessions), display_limit)}) or 'q' to quit: ")
            sys.stderr.flush()
            choice = sys.stdin.readline().strip().lower()

            if choice == "q":
                sys.exit(0)

            if not choice:
                continue

            idx = int(choice) - 1
            if 0 <= idx < len(sessions):
                return str(sessions[idx]["path"])
            sys.stderr.write("Invalid number.\n")
        except ValueError:
            sys.stderr.write("Please enter a number.\n")
        except KeyboardInterrupt:
            sys.exit(0)


def render_block(block: Dict[str, Any], mode: str, redactor: Optional[Redactor] = None) -> str:
    b_type = block.get("type")

    # --chat mode (DEFAULT): Skip everything except text
    if mode == "chat":
        if b_type == "text":
            text = block.get("text", "")
            if redactor:
                text = redactor.redact(text)
            return text
        return ""

    # Common for Thoughts and Verbose
    if b_type == "text":
        text = block.get("text", "")
        if redactor:
            text = redactor.redact(text)
        return text

    if b_type == "thinking":
        thinking = block.get("thinking", "")
        if redactor:
            thinking = redactor.redact(thinking)
        return "> **Thinking**\n" + "\n".join(f"> {line}" for line in thinking.splitlines())

    if b_type == "tool_use":
        name = block.get("name")
        input_data = block.get("input")
        if redactor:
            input_data = redactor.redact(input_data)
        return f"**Tool Use: `{name}`**\n```json\n{json.dumps(input_data, indent=2)}\n```"

    if b_type == "tool_result":
        if mode == "thoughts":
            is_error = block.get("is_error", False)
            status = "Error" if is_error else "Success"
            return f"_[Tool Result: {status} - Output Omitted]_"

        if mode == "verbose":
            content = block.get("content", "")
            if redactor:
                content = redactor.redact(content)
            is_error = block.get("is_error", False)
            header = "**Tool Result (Error)**" if is_error else "**Tool Result**"

            text_content = ""
            if isinstance(content, str):
                text_content = content
            elif isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    elif isinstance(item, dict) and item.get("type") == "image":
                        parts.append("[Image Data Omitted]")
                    else:
                        parts.append(str(item))
                text_content = "\n".join(parts)
            else:
                text_content = str(content)

            return f"{header}\n```text\n{text_content}\n```"

    if b_type == "meta":
        label = block.get("label", "Meta")
        content = block.get("content", {})
        if redactor:
            content = redactor.redact(content)
        return f"**{label}**\n```json\n{json.dumps(content, indent=2)}\n```"

    if b_type == "unknown":
        source = block.get("source", "unknown")
        raw = block.get("raw", {})
        if redactor:
            raw = redactor.redact(raw)
        return f"**Unknown Block: `{source}`**\n```json\n{json.dumps(raw, indent=2)}\n```"

    return ""


def collect_events(filepath: str, backend: str) -> List[Event]:
    events: List[Event] = []
    
    if backend == "gemini":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            messages = data.get("messages", [])
            for msg in messages:
                norm = normalize_event(msg, backend)
                events.extend(norm)
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                events.extend(normalize_event(data, backend))
            
    return events


def convert(
    filepath: str,
    output_file: Optional[str] = None,
    mode: str = "chat",
    backend: str = "claude",
    redaction: str = "none",
    tail: Optional[int] = None,
    head: Optional[int] = None,
) -> None:
    """Convert a JSONL session into Markdown.

    redaction: "none" | "standard" | "strict"
    tail: if set, only show the last N text-containing events
    head: if set, only show the first N text-containing events
    """
    if not os.path.exists(filepath):
        print(f"Error: File not found {filepath}")
        return

    out = sys.stdout
    if output_file:
        out = open(output_file, "w", encoding="utf-8")

    redactor: Optional[Redactor] = None
    if redaction in {"standard", "strict"}:
        redactor = Redactor(strict=redaction == "strict")

    try:
        out.write(f"# Transcript: {os.path.basename(filepath)}\n")
        out.write(f"Mode: {mode}\n")
        out.write(f"Description: {MODE_DESCRIPTIONS.get(mode, '')}\n\n")
        if redactor:
            out.write(f"Redaction: {redaction}\n")
            out.write("WARNING: Redaction enabled (pattern-based; not guaranteed safe to share).\n")
            if redaction == "strict":
                out.write("WARNING: Strict redaction may over-redact and remove useful context.\n")
            out.write("\n")

        events = collect_events(filepath, backend)
        
        # Apply head/tail filter if requested
        if (tail is not None and tail > 0) or (head is not None and head > 0):
            # Filter for events that contain text blocks
            # We want to keep the N specific events
            # But we must respect the original order
            
            # 1. Identify indices of text-containing events
            text_indices = []
            for i, event in enumerate(events):
                has_text = any(b.get("type") == "text" for b in event.get("blocks", []))
                if has_text:
                    text_indices.append(i)
            
            # 2. Slice to get the indices to keep
            keep_indices = set()
            if head:
                keep_indices.update(text_indices[:head])
            elif tail:
                keep_indices.update(text_indices[-tail:])
            
            # 3. Filter events list
            events = [e for i, e in enumerate(events) if i in keep_indices]

        for event in events:
            blocks = event.get("blocks", [])
            rendered_blocks: List[str] = []

            for block in blocks:
                rendered = render_block(block, mode, redactor)
                if rendered:
                    rendered_blocks.append(rendered)

            if not rendered_blocks:
                continue

            role = event.get("role", "")
            timestamp = format_timestamp(event.get("timestamp", ""))
            out.write(f"## {role.title()} ({timestamp})\n\n")
            out.write("\n\n".join(rendered_blocks))
            out.write("\n\n---\n\n")

    finally:
        if output_file and out is not sys.stdout:
            out.close()
            print(f"Successfully converted to {output_file} ({mode} mode)")


def main() -> None:
    desc = "Convert Claude or Codex JSONL to Markdown.\n\n"
    desc += "Run without arguments to select a recent session interactively.\n\n"
    desc += "Modes:\n"
    for m, d in MODE_DESCRIPTIONS.items():
        desc += f"  {m:<10} {d}\n"

    parser = argparse.ArgumentParser(description=desc, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("input_file", nargs="?", help="Path to input .jsonl file")
    parser.add_argument("output_file", nargs="?", help="Path to output .md file (optional)")

    parser.add_argument(
        "--backend",
        choices=SUPPORTED_BACKENDS,
        help="Select backend (default: auto/all)",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--mode",
        choices=["chat", "thoughts", "verbose"],
        help="Select rendering mode (default: chat)",
    )
    mode_group.add_argument("--thoughts", action="store_true", help="Enable 'thoughts' mode (Logic flow, summarized outputs)")
    mode_group.add_argument("--verbose", action="store_true", help="Enable 'verbose' mode (Full record with outputs)")

    redaction_group = parser.add_mutually_exclusive_group()
    redaction_group.add_argument(
        "--redact",
        action="store_true",
        help="Enable pattern-based redaction in output (not guaranteed safe)",
    )
    redaction_group.add_argument(
        "--redact-strict",
        action="store_true",
        help="Enable aggressive redaction (may over-redact useful context)",
    )
    redaction_group.add_argument(
        "--redact-level",
        choices=["standard", "strict", "none"],
        help="Select redaction level (standard|strict|none)",
    )

    # Convenience Flags
    filter_group = parser.add_mutually_exclusive_group()
    filter_group.add_argument(
        "-n", "--tail",
        type=int,
        metavar="N",
        help="Show only the last N messages containing text (excludes tool-only turns)",
    )
    filter_group.add_argument(
        "--head",
        type=int,
        metavar="N",
        help="Show only the first N messages containing text (excludes tool-only turns)",
    )

    args = parser.parse_args()

    mode = "chat"
    if args.mode:
        mode = args.mode
    elif args.verbose:
        mode = "verbose"
    elif args.thoughts:
        mode = "thoughts"

    redaction = "none"
    if args.redact_level:
        if args.redact_level == "standard":
            redaction = "standard"
        elif args.redact_level == "strict":
            redaction = "strict"
        else:
            redaction = "none"
    elif args.redact_strict:
        redaction = "strict"
    elif args.redact:
        redaction = "standard"

    backend = args.backend

    if args.input_file:
        inferred = infer_backend_from_path(args.input_file)
        # If explicitly set, respect it. If not, use inferred.
        if inferred and not backend:
            backend = inferred
        # If explicit mismatch, keep explicit (though it might fail parsing)

    if not args.input_file:
        if sys.stdin.isatty():
            # If backend is None, select_session will aggregate all
            args.input_file = select_session(backend)
            # After selection, we must ensure we know the backend for parsing
            if not backend:
                backend = infer_backend_from_path(args.input_file)
                # Fallback if inference fails (unlikely for known paths)
                if not backend:
                    # Try to guess or error out? 
                    # Actually, normalize_event needs a backend.
                    # Let's assume standard paths for now or check file content type?
                    # For now, inference is robust enough for standard paths.
                    pass
        else:
            print("Error: No input file provided and not running interactively.", file=sys.stderr)
            sys.exit(1)
    
    # Final safety check: if we still don't have a backend (e.g. random file provided without --backend)
    # Default to claude? Or try to sniff? 
    # Current behavior was default='claude'. Let's keep a safe default if still None.
    if not backend:
        backend = "claude"

    convert(args.input_file, args.output_file, mode, backend, redaction, args.tail, args.head)


if __name__ == "__main__":
    main()