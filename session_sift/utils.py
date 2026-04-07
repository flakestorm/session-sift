from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def safe_str(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    if isinstance(content, list):
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def count_tokens(messages: list[dict]) -> int:
    chars = 0
    for message in messages:
        chars += len(safe_str(message.get("content", "")))
    return chars // 4


def ensure_parent_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
