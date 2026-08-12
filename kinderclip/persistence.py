"""Safe JSON persistence for project and review artefacts."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


REPLACE_ATTEMPTS = 6
REPLACE_RETRY_SECONDS = 0.2


def load_json(path: str | Path, default: Any | None = None) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return default
    with file_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_json_atomic(
    path: str | Path,
    payload: Any,
    validator: Callable[[Any], list[str]] | None = None,
) -> None:
    """Write valid JSON through a same-directory temporary file then replace."""
    if validator:
        errors = validator(payload)
        if errors:
            raise ValueError("Refusing to save invalid JSON: " + "; ".join(errors))
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-", suffix=".tmp", dir=destination.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        with Path(temporary_name).open(encoding="utf-8") as handle:
            json.load(handle)
        # Windows can briefly lock a file while Explorer, antivirus, or another
        # Streamlit rerun reads it. Retrying preserves atomic replacement and
        # prevents a harmless short-lived lock from interrupting the workflow.
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                os.replace(temporary_name, destination)
                break
            except PermissionError:
                if attempt == REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(REPLACE_RETRY_SECONDS * (attempt + 1))
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()
