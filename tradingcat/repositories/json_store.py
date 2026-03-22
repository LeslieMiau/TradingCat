from __future__ import annotations

import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class _FileLock:
    """Advisory file lock using ``fcntl.flock`` on a sidecar ``.lock`` file."""

    def __init__(self, lock_path: Path, *, shared: bool) -> None:
        self._lock_path = lock_path
        self._shared = shared
        self._fd: int | None = None

    def __enter__(self) -> _FileLock:
        self._fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR)
        fcntl.flock(self._fd, fcntl.LOCK_SH if self._shared else fcntl.LOCK_EX)
        return self

    def __exit__(self, *_: object) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None


class JsonStore:
    """Thread-safe JSON file store with atomic writes.

    - **Atomic writes**: ``tempfile`` + ``os.replace()`` guarantees that a
      crash mid-write never leaves a half-written (corrupt) file.
    - **File locking**: ``fcntl.flock`` on a sidecar ``.lock`` file serialises
      concurrent readers/writers so data is never lost.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._path.with_suffix(self._path.suffix + ".lock")

    def load(self, default: Any = None) -> Any:
        """Read and parse the JSON file, returning *default* on any failure."""
        with _FileLock(self._lock_path, shared=True):
            if not self._path.exists():
                return default
            raw = self._path.read_text(encoding="utf-8").strip()
            if not raw:
                return default
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return default

    def save(self, payload: Any) -> None:
        """Atomically write *payload* as pretty-printed JSON."""
        data = json.dumps(payload, ensure_ascii=True, indent=2)
        with _FileLock(self._lock_path, shared=False):
            self._atomic_write(data)

    def _atomic_write(self, data: str) -> None:
        """Write to a temp file, fsync, then ``os.replace`` into place.

        ``os.replace`` is atomic on POSIX when source and target reside on the
        same filesystem, so readers never see a partially-written file.
        """
        dir_path = str(self._path.parent)
        fd = None
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
            os.write(fd, data.encode("utf-8"))
            os.fsync(fd)
            os.close(fd)
            fd = None  # mark as closed
            os.replace(tmp_path, str(self._path))
        except BaseException:
            if fd is not None:
                os.close(fd)
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise
