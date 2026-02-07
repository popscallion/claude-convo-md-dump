from typing import Any, Dict, List, Optional, TypedDict, Union

class Block(TypedDict, total=False):
    type: str
    text: str
    thinking: str
    name: str  # for tool_use
    input: Any  # for tool_use
    content: Any  # for tool_result or meta
    is_error: bool # for tool_result
    label: str # for meta
    source: str # for unknown
    raw: Any # for unknown

class Event(TypedDict):
    role: str
    timestamp: str
    blocks: List[Block]
