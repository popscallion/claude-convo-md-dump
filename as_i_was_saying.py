import argparse
import json
import os
import re
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
CONTEXT_COL_WIDTH = 40


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


def available_backends(requested_backend: Optional[str] = None) -> List[str]:
    """Return implemented backends that are present on this system.

    If a backend is explicitly requested, return it regardless of path existence.
    """
    if requested_backend:
        return [requested_backend]
    return [b for b in SUPPORTED_BACKENDS if get_base_dir(b).exists()]


def parse_since_cutoff(spec: str) -> float:
    """Parse duration spec into epoch cutoff timestamp.

    Supported units: h, d, w (e.g. 12h, 1d, 2w).
    """
    match = re.match(r"^\s*(\d+)\s*([hdw])\s*$", spec, re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid --since value: {spec!r}. Use formats like 12h, 1d, 2w.")
    amount = int(match.group(1))
    unit = match.group(2).lower()
    multiplier = {"h": 3600, "d": 86400, "w": 604800}[unit]
    return datetime.now().timestamp() - (amount * multiplier)


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


def _truncate_snippet(text: str, max_len: int = 50) -> str:
    clean = text.replace("\n", " ").strip()
    if len(clean) > max_len:
        return clean[: max_len - 3] + "..."
    return clean


def get_session_context(filepath: str, backend: str) -> Tuple[Optional[str], Optional[str]]:
    """Read latest and earliest user text snippets from a session file."""
    latest_user_text = None
    earliest_user_text = None
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
                        if not text:
                            continue
                        if earliest_user_text is None:
                            earliest_user_text = text
                        latest_user_text = text
            return latest_user_text, earliest_user_text

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
                        if earliest_user_text is None:
                            earliest_user_text = text
                        latest_user_text = text
        return latest_user_text, earliest_user_text
    except Exception:
        pass
    return None, None


def analyze_session_query(filepath: str, backend: str, query: str) -> Tuple[int, str]:
    """Return query match count plus a best-effort match-context snippet."""
    needle = query.lower().strip()
    if not needle:
        return 0, ""
    try:
        events = collect_events(filepath, backend)
    except Exception:
        return 0, ""

    total = 0
    first_context = ""
    for event in events:
        for block in event.get("blocks", []):
            if block.get("type") != "text":
                continue
            text = block.get("text", "")
            if not text:
                continue
            lowered = text.lower()
            total += lowered.count(needle)
            if not first_context:
                idx = lowered.find(needle)
                if idx >= 0:
                    start = max(0, idx - 25)
                    end = min(len(text), idx + len(query) + 25)
                    first_context = _truncate_snippet(text[start:end], max_len=60)
    return total, first_context


def get_session_summary(filepath: str, backend: str) -> Optional[str]:
    """Backward-compat helper: latest user snippet."""
    latest, _earliest = get_session_context(filepath, backend)
    return latest


def find_recent_sessions(
    backend: str,
    limit: int = 20,
    since_cutoff: Optional[float] = None,
) -> List[Dict[str, Any]]:
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
                    if since_cutoff is not None and stat.st_mtime < since_cutoff:
                        continue
                    sessions.append(
                        {
                            "path": path,
                            "mtime": stat.st_mtime,
                            "size": stat.st_size,
                            "session_id": extract_session_id(path, backend),
                        }
                    )
                except OSError:
                    continue
    else:
        # Standard recursive scan for other backends
        for path in base_dir.rglob("*.jsonl"):
            if backend == "claude" and "agent-" in path.name:
                continue

            try:
                stat = path.stat()
                if since_cutoff is not None and stat.st_mtime < since_cutoff:
                    continue
                sessions.append(
                    {
                        "path": path,
                        "mtime": stat.st_mtime,
                        "size": stat.st_size,
                        "session_id": extract_session_id(path, backend),
                    }
                )
            except OSError:
                continue

    sessions.sort(key=lambda x: x["mtime"], reverse=True)

    valid_sessions: List[Dict[str, Any]] = []
    candidates = sessions[: limit * 2]

    for s in candidates:
        latest_raw, earliest_raw = get_session_context(str(s["path"]), backend)
        if not latest_raw:
            continue

        s["summary"] = _truncate_snippet(latest_raw, max_len=50)
        s["latest_summary"] = s["summary"]
        s["earliest_summary"] = _truncate_snippet(earliest_raw or latest_raw, max_len=50)
        valid_sessions.append(s)

        if len(valid_sessions) >= limit:
            break

    return valid_sessions


def format_size(size_bytes: int) -> str:
    """Format size as fixed-width 7-char SI unit text (e.g. '999.9KB')."""
    value = size_bytes / 1000.0
    units = ["KB", "MB", "GB", "TB"]
    unit_idx = 0

    # Avoid displaying 1000.0 at a lower unit due to rounding.
    while unit_idx < len(units) - 1 and value >= 999.95:
        value /= 1000.0
        unit_idx += 1

    return f"{value:5.1f}{units[unit_idx]}"


def get_backend_abbr(backend: str) -> str:
    return {
        "claude": "CLD",
        "codex": "CDX",
        "gemini": "GMN",
    }.get(backend, backend[:3].upper())


def extract_session_id(path: Path, backend: str) -> str:
    """Extract backend-normalized human-friendly session id token."""
    stem = path.stem

    if backend == "claude":
        # Claude filenames are UUID-like; first chunk is most human-scannable.
        return stem.split("-")[0]

    if backend == "codex":
        # rollout-<datetime>-<uid>
        if stem.startswith("rollout-"):
            stem = stem[len("rollout-"):]
        parts = stem.split("-")
        return parts[-1] if parts else stem

    if backend == "gemini":
        # session-<datetime>-<uid>
        if stem.startswith("session-"):
            stem = stem[len("session-"):]
        parts = stem.split("-")
        return parts[-1] if parts else stem

    return stem


def session_id_for_path(path: str, backend: Optional[str] = None) -> str:
    """Best-effort full backend-native session id extraction for emit mode."""
    p = Path(path)
    inferred = backend or infer_backend_from_path(path)
    stem = p.stem

    if inferred == "codex":
        # Prefer explicit id from session metadata if present.
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if row.get("type") == "session_meta":
                        payload = row.get("payload", {})
                        sid = payload.get("id")
                        if isinstance(sid, str) and sid:
                            return sid
                        break
        except Exception:
            pass

        match = re.search(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", stem)
        if match:
            return match.group(0)

    if inferred == "gemini":
        # Prefer full sessionId from JSON payload when available.
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                sid = data.get("sessionId")
                if isinstance(sid, str) and sid:
                    return sid
        except Exception:
            pass

        match = re.search(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", stem)
        if match:
            return match.group(0)

    if inferred == "claude":
        match = re.search(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", stem)
        if match:
            return match.group(0)
        if stem.startswith("agent-"):
            return stem[len("agent-"):]
        return stem

    stem = p.stem
    for prefix in ("session-", "rollout-", "agent-"):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    return stem


def assign_display_ids(sessions: List[Dict[str, Any]], max_len: int = 8) -> None:
    """Assign fixed-width display IDs."""
    if not sessions:
        return

    for s in sessions:
        sid = str(s.get("session_id", ""))
        if not sid:
            s["display_id"] = " " * max_len
            continue
        s["display_id"] = sid[:max_len].ljust(max_len)


def collect_all_sessions(
    limit_per_backend: int = 50,
    since_cutoff: Optional[float] = None,
    requested_backend: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Aggregate recent sessions from all supported backends."""
    all_sessions = []
    for backend in available_backends(requested_backend):
        sessions = find_recent_sessions(backend, limit=limit_per_backend, since_cutoff=since_cutoff)
        for s in sessions:
            s["backend"] = backend
        all_sessions.extend(sessions)
    
    # Sort unified list by time (newest first)
    all_sessions.sort(key=lambda x: x["mtime"], reverse=True)
    return all_sessions


def count_session_matches(filepath: str, backend: str, query: str) -> int:
    """Count case-insensitive query matches in text blocks for ranking."""
    count, _context = analyze_session_query(filepath, backend, query)
    return count


def rank_sessions(sessions: List[Dict[str, Any]], query: Optional[str] = None) -> List[Dict[str, Any]]:
    if not query:
        return sorted(
            sessions,
            key=lambda x: (x.get("mtime", 0), str(x.get("path", ""))),
            reverse=True,
        )

    ranked: List[Dict[str, Any]] = []
    for s in sessions:
        backend = s.get("backend")
        if not backend:
            continue
        match_count, match_context = analyze_session_query(str(s["path"]), backend, query)
        if match_count > 0:
            s_copy = dict(s)
            s_copy["match_count"] = match_count
            s_copy["match_context"] = match_context or s_copy.get("latest_summary", "")
            ranked.append(s_copy)

    ranked.sort(
        key=lambda x: (
            x.get("match_count", 0),
            x.get("mtime", 0),
            str(x.get("path", "")),
        ),
        reverse=True,
    )
    return ranked


def discover_sessions(
    backend: Optional[str] = None,
    since_cutoff: Optional[float] = None,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if backend:
        sessions = find_recent_sessions(backend, since_cutoff=since_cutoff)
        for s in sessions:
            s["backend"] = backend
    else:
        sessions = collect_all_sessions(since_cutoff=since_cutoff)
    ranked = rank_sessions(sessions, query)
    assign_display_ids(ranked, max_len=8)
    return ranked


def emit_sessions_tsv(sessions: List[Dict[str, Any]]) -> None:
    """Emit script-friendly discovery results to stdout."""
    print("backend\ttimestamp\tsize_bytes\tsize_display\tmatch_count\tsession_id\tpath\tsummary")
    for s in sessions:
        ts = datetime.fromtimestamp(s["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
        matches = s.get("match_count", 0)
        sid = str(s.get("display_id", "")).strip()
        size_display = format_size(int(s.get("size", 0)))
        summary = str(s.get("summary", "")).replace("\t", " ").replace("\n", " ")
        print(
            f"{s.get('backend', '')}\t{ts}\t{s.get('size', 0)}\t{size_display}\t{matches}\t{sid}\t{s.get('path', '')}\t{summary}"
        )


def list_context_columns(session: Dict[str, Any], query_mode: bool) -> Tuple[str, str]:
    """Return (primary, secondary) context snippets for list rows."""
    latest = str(session.get("latest_summary") or session.get("summary") or "")
    earliest = str(session.get("earliest_summary") or latest)
    if query_mode:
        primary = latest
        secondary = str(session.get("match_context") or latest)
        return primary, secondary
    return latest, earliest


def format_context_column(text: str, width: int = CONTEXT_COL_WIDTH) -> str:
    return _truncate_snippet(text or "", max_len=width).ljust(width)


def fzf_select(sessions: List[Dict[str, Any]], header: str) -> Tuple[Optional[str], str]:
    """Use fzf to select a session from the list."""
    fzf = shutil.which("fzf")
    if not fzf:
        return None, "unavailable"

    # Format lines for fzf:
    # "BKD MM-DD HH:MM SIZE    HITS ID       Primary Context | Secondary Context"
    lines = []
    map_lines = {}
    query_mode = any("match_count" in s for s in sessions)
    
    for s in sessions:
        dt = datetime.fromtimestamp(s["mtime"]).strftime("%m-%d %H:%M")
        bk = get_backend_abbr(s['backend'])
        sz = format_size(s['size'])
        hits = s.get("match_count", "")
        hit_text = f"{hits:>3}" if hits != "" else "   "
        sid = s.get("display_id", " " * 8)
        primary, secondary = list_context_columns(s, query_mode)
        primary_col = format_context_column(primary)
        secondary_col = format_context_column(secondary)
        
        # "CLD 02-08 14:20 999.9KB  12 abc12345  Primary... | Secondary..."
        line = f"{bk} {dt} {sz} {hit_text} {sid}  {primary_col} | {secondary_col}"
        lines.append(line)
        map_lines[line] = str(s["path"])

    try:
        proc = subprocess.Popen(
            [fzf, "--no-sort", "--header", header],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, _ = proc.communicate(input="\n".join(lines))
        
        if proc.returncode == 0 and stdout.strip():
            selected = stdout.strip()
            return map_lines.get(selected), "selected"
        if proc.returncode in (1, 130):
            return None, "cancelled"
    except Exception:
        return None, "error"
        
    return None, "error"


def select_session(
    backend: Optional[str] = None,
    since_cutoff: Optional[float] = None,
    query: Optional[str] = None,
    since_label: str = "1w",
) -> str:
    """Interactive session selector. 
    
    If backend is provided, limits to that backend.
    Otherwise, aggregates all backends.
    """
    sessions = discover_sessions(backend=backend, since_cutoff=since_cutoff, query=query)
    if not sessions:
        if backend:
            print(f"No {backend.title()} sessions found in {get_base_dir(backend)}", file=sys.stderr)
        elif query:
            print(f"No sessions matched query: {query!r}", file=sys.stderr)
        else:
            print("No sessions found in any backend.", file=sys.stderr)
        sys.exit(1)
    # Try fzf first
    horizon = "all-time" if since_cutoff is None else since_label
    mode_text = "query-ranked" if query else "most recent first"
    path, fzf_status = fzf_select(sessions, f"Select a session ({mode_text}, since: {horizon})")
    if path:
        return path
    if fzf_status == "cancelled":
        sys.exit(0)
    if fzf_status == "unavailable":
        print("Error: `fzf` is required for interactive selection but was not found.", file=sys.stderr)
        print("Hint: install `fzf` or use `--list` for non-interactive discovery.", file=sys.stderr)
        sys.exit(2)

    print("Error: interactive picker failed.", file=sys.stderr)
    print("Hint: retry, or use `--list` to discover sessions and pass a path explicitly.", file=sys.stderr)
    sys.exit(1)


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
    desc = "Convert Claude, Codex, or Gemini session logs to Markdown.\n\n"
    desc += "Run without arguments to select a recent session interactively.\n\n"
    desc += "Modes:\n"
    for m, d in MODE_DESCRIPTIONS.items():
        desc += f"  {m:<10} {d}\n"

    parser = argparse.ArgumentParser(description=desc, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("input_file", nargs="?", help="Path to input session file (.jsonl or .json)")
    parser.add_argument("output_file", nargs="?", help="Path to output .md file (optional)")

    parser.add_argument(
        "--backend",
        choices=SUPPORTED_BACKENDS,
        help="Select backend (default: auto/all)",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="Print discovered sessions as TSV and exit (non-interactive)",
    )
    parser.add_argument(
        "--emit",
        choices=["path", "id"],
        help="Emit only selected/provided session path or id and exit.",
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
    parser.add_argument(
        "--query",
        help="Case-insensitive session search query (session-level ranking, full transcript output)",
    )
    since_group = parser.add_mutually_exclusive_group()
    since_group.add_argument(
        "--since",
        default="1w",
        metavar="DURATION",
        help="List/search horizon (default: 1w). Supports h/d/w (examples: 1d, 1w, 12h).",
    )
    since_group.add_argument(
        "--all-time",
        action="store_true",
        help="Disable date horizon for list/search discovery.",
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
        if args.list:
            print("Error: `--list` cannot be used with an input file path.", file=sys.stderr)
            sys.exit(2)
        if args.query:
            print("Warning: `--query` is ignored when an input file path is provided.", file=sys.stderr)
        if args.all_time or args.since != "1w":
            print("Warning: `--since`/`--all-time` only affect discovery and are ignored with input file.", file=sys.stderr)
        inferred = infer_backend_from_path(args.input_file)
        # If explicitly set, respect it. If not, use inferred.
        if inferred and not backend:
            backend = inferred
        # If explicit mismatch, keep explicit (though it might fail parsing)

    if not args.input_file:
        since_cutoff: Optional[float] = None
        since_label = "all-time"
        if not args.all_time:
            try:
                since_cutoff = parse_since_cutoff(args.since)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(2)
            since_label = args.since

        if args.list:
            if args.emit:
                print("Warning: `--emit` is ignored with `--list`.", file=sys.stderr)
            sessions = discover_sessions(backend=backend, since_cutoff=since_cutoff, query=args.query)
            if not sessions:
                print("No sessions found for the current filters.", file=sys.stderr)
                sys.exit(1)
            emit_sessions_tsv(sessions)
            sys.exit(0)

        if sys.stdin.isatty():
            # If backend is None, select_session will aggregate all
            args.input_file = select_session(
                backend=backend,
                since_cutoff=since_cutoff,
                query=args.query,
                since_label=since_label,
            )
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
            print("Error: no input file provided and not running interactively.", file=sys.stderr)
            print("Hint: use `--list` to discover sessions, or run in a TTY for interactive picker.", file=sys.stderr)
            sys.exit(1)

    if args.emit:
        if args.emit == "path":
            print(args.input_file)
        else:
            print(session_id_for_path(args.input_file, backend))
        sys.exit(0)
    
    # Final safety check: if we still don't have a backend (e.g. random file provided without --backend)
    # Default to claude? Or try to sniff? 
    # Current behavior was default='claude'. Let's keep a safe default if still None.
    if not backend:
        backend = "claude"

    convert(args.input_file, args.output_file, mode, backend, redaction, args.tail, args.head)


if __name__ == "__main__":
    main()
