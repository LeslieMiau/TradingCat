#!/usr/bin/env python3
"""Compatibility shim for sessions that still invoke the old Codex hook path."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    script = Path.home() / ".claude" / "scripts" / "permission_guard.sh"
    payload = sys.stdin.read()
    result = subprocess.run(
        ["/bin/bash", str(script)],
        input=payload,
        text=True,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
