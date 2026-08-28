from __future__ import annotations

import os
from pathlib import Path


def load_project_env(path: Path) -> None:
    """Load simple .env values without ever printing their contents.

    python-dotenv is used when installed; the fallback intentionally supports the
    project’s simple KEY=value configuration so the collection commands work
    before optional dependencies are installed.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        if not path.exists():
            return
        for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key.startswith("export "):
                key = key[7:].strip()
            if not key:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ.setdefault(key, value)
    else:
        load_dotenv(path, override=False)
