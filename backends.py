import json
from typing import Any, Dict, Iterable, List, Optional
from models import Event, Block

def _parse_json_maybe(text: str) -> Any:
    if not isinstance(text, str):
        return text
    text = text.strip()
    if not text:
        return text
    try:
        return json.loads(text)
    except Exception:
        return text

def _codex_text_from_items(items: Iterable[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if text:
            parts.append(text)
    return "\n".join(parts).strip()

def _codex_summary_text(summary: Any) -> str:
    if isinstance(summary, list):
        parts: List[str] = []
        for item in summary:
            if isinstance(item, dict) and item.get("text"):
                parts.append(item.get("text"))
            else:
                parts.append(str(item))
        return "\n".join(parts).strip()
    if isinstance(summary, str):
        return summary
    return ""

def normalize_claude_event(raw: Dict[str, Any]) -> List[Event]:
    row_type = raw.get("type")
    if row_type not in {"user", "assistant"}:
        return []

    msg = raw.get("message", {})
    role = msg.get("role") or row_type
    content = msg.get("content")

    blocks: List[Block] = []
    if isinstance(content, str):
        blocks.append({"type": "text", "text": content})
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                blocks.append(block)  # type: ignore

    if not blocks:
        return []

    return [
        {
            "role": role,
            "timestamp": raw.get("timestamp", ""),
            "blocks": blocks,
        }
    ]

def normalize_codex_event(raw: Dict[str, Any]) -> List[Event]:
    row_type = raw.get("type")
    payload = raw.get("payload", {})
    timestamp = raw.get("timestamp", "")

    if row_type == "session_meta":
        return [
            {
                "role": "meta",
                "timestamp": timestamp or payload.get("timestamp", ""),
                "blocks": [
                    {"type": "meta", "label": "Session Meta", "content": payload}
                ],
            }
        ]

    if row_type == "turn_context":
        return [
            {
                "role": "meta",
                "timestamp": timestamp,
                "blocks": [
                    {"type": "meta", "label": "Turn Context", "content": payload}
                ],
            }
        ]

    if row_type == "event_msg":
        msg_type = payload.get("type")
        text = payload.get("text") or payload.get("message") or ""

        if msg_type == "user_message":
            return [
                {
                    "role": "user",
                    "timestamp": timestamp,
                    "blocks": [{"type": "text", "text": text}],
                }
            ]

        if msg_type == "agent_message":
            return [
                {
                    "role": "assistant",
                    "timestamp": timestamp,
                    "blocks": [{"type": "text", "text": text}],
                }
            ]

        if msg_type == "agent_reasoning":
            return [
                {
                    "role": "assistant",
                    "timestamp": timestamp,
                    "blocks": [{"type": "thinking", "thinking": text}],
                }
            ]

        if msg_type == "token_count":
            return [
                {
                    "role": "meta",
                    "timestamp": timestamp,
                    "blocks": [
                        {"type": "meta", "label": "Token Count", "content": payload}
                    ],
                }
            ]

        return [
            {
                "role": "meta",
                "timestamp": timestamp,
                "blocks": [
                    {"type": "unknown", "source": "event_msg", "raw": payload}
                ],
            }
        ]

    if row_type != "response_item":
        return []

    item_type = payload.get("type")

    if item_type == "message":
        content = payload.get("content")
        role = payload.get("role")
        if not isinstance(content, list):
            return []

        if role:
            text = _codex_text_from_items(content)
            if not text:
                return []
            return [
                {
                    "role": role,
                    "timestamp": timestamp,
                    "blocks": [{"type": "text", "text": text}],
                }
            ]

        events: List[Event] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text", "")
            if not text:
                continue
            item_role = "assistant"
            if item.get("type") == "input_text":
                item_role = "user"
            elif item.get("type") == "output_text":
                item_role = "assistant"
            events.append(
                {
                    "role": item_role,
                    "timestamp": timestamp,
                    "blocks": [{"type": "text", "text": text}],
                }
            )
        return events

    if item_type == "function_call":
        role = payload.get("role") or "assistant"
        input_data = _parse_json_maybe(payload.get("arguments", ""))
        return [
            {
                "role": role,
                "timestamp": timestamp,
                "blocks": [
                    {
                        "type": "tool_use",
                        "name": payload.get("name"),
                        "input": input_data,
                    }
                ],
            }
        ]

    if item_type == "function_call_output":
        return [
            {
                "role": "assistant",
                "timestamp": timestamp,
                "blocks": [
                    {"type": "tool_result", "content": payload.get("output", "")}
                ],
            }
        ]

    if item_type == "reasoning":
        thinking = _codex_summary_text(payload.get("summary"))
        if not thinking:
            thinking = "[Reasoning summary unavailable]"
        return [
            {
                "role": "assistant",
                "timestamp": timestamp,
                "blocks": [{"type": "thinking", "thinking": thinking}],
            }
        ]

    return [
        {
            "role": "meta",
            "timestamp": timestamp,
            "blocks": [
                {"type": "unknown", "source": f"response_item:{item_type}", "raw": payload}
            ],
        }
    ]

def normalize_gemini_event(raw: Dict[str, Any]) -> List[Event]:
    msg_type = raw.get("type")
    timestamp = raw.get("timestamp", "")
    content = raw.get("content", "")

    if msg_type == "user":
        return [{
            "role": "user",
            "timestamp": timestamp,
            "blocks": [{"type": "text", "text": content}]
        }]

    if msg_type == "gemini":
        blocks: List[Block] = []
        
        # Handle thoughts (Gemini Flash Thinking / Reasoning)
        thoughts = raw.get("thoughts", [])
        if isinstance(thoughts, list):
            for t in thoughts:
                if isinstance(t, dict):
                    subject = t.get("subject", "")
                    desc = t.get("description", "")
                    if desc:
                        text = f"**{subject}**\n{desc}" if subject else desc
                        blocks.append({"type": "thinking", "thinking": text})

        if content:
            blocks.append({"type": "text", "text": content})

        tool_calls = raw.get("toolCalls", [])
        for call in tool_calls:
            blocks.append({
                "type": "tool_use",
                "name": call.get("name"),
                "input": call.get("args"),
            })
            
            results = call.get("result", [])
            output = ""
            is_error = False
            
            if results and isinstance(results, list):
                res_item = results[0]
                if "functionResponse" in res_item:
                    resp_body = res_item["functionResponse"].get("response", {})
                    if isinstance(resp_body, dict) and "output" in resp_body:
                        output = resp_body["output"]
                    else:
                        output = str(resp_body)
                elif "error" in res_item:
                    is_error = True
                    output = res_item.get("error", "Unknown error")
                else:
                    output = str(res_item)

            blocks.append({
                "type": "tool_result",
                "content": output,
                "is_error": is_error,
            })

        return [{
            "role": "assistant",
            "timestamp": timestamp,
            "blocks": blocks
        }]

    if msg_type in ("error", "info"):
        return [{
            "role": "meta",
            "timestamp": timestamp,
            "blocks": [{
                "type": "meta",
                "label": msg_type.title(),
                "content": content
            }]
        }]

    return []

def normalize_event(raw: Dict[str, Any], backend: str) -> List[Event]:
    if backend == "codex":
        return normalize_codex_event(raw)
    if backend == "gemini":
        return normalize_gemini_event(raw)
    return normalize_claude_event(raw)
