from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_json_file(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open('r', encoding='utf-8') as handle:
        return json.load(handle)


def dump_json_file(path: Path, payload: Any) -> None:
    ensure_parent_dir(path)
    with path.open('w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)


def slugify(value: str) -> str:
    compact = re.sub(r'[^a-zA-Z0-9]+', '-', value.strip().lower())
    return compact.strip('-') or 'item'


def compact_text(value: str, limit: int = 240) -> str:
    squashed = re.sub(r'\s+', ' ', (value or '')).strip()
    if len(squashed) <= limit:
        return squashed
    return squashed[: limit - 3].rstrip() + '...'
