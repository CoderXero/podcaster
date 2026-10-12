from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def redact(value: str) -> str:
    value = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", value)
    return re.sub(r"([?&](?:sig|token|secret|key)=)[^&\s]+", r"\1[REDACTED]", value)


def audit(log_root: Path, slug: str, stage: str, **data: Any) -> None:
    log_root.mkdir(parents=True, exist_ok=True)
    event = {"at": datetime.now(UTC).isoformat(), "slug": slug, "stage": stage}
    event.update({key: redact(str(value)) if isinstance(value, str) else value for key, value in data.items()})
    path = log_root / f"{slug}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        handle.flush()
