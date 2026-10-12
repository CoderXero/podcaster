from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path


class EpisodeLock:
    def __init__(self, path: Path, stale_after: int = 24 * 3600):
        self.path = path
        self.stale_after = stale_after
        self.acquired = False

    def __enter__(self) -> EpisodeLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"pid": os.getpid(), "host": socket.gethostname(), "created": time.time()}
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                old = json.loads(self.path.read_text())
                stale = time.time() - float(old.get("created", 0)) > self.stale_after
            except (OSError, ValueError, TypeError):
                stale = False
            if stale:
                self.path.unlink(missing_ok=True)
                return self.__enter__()
            raise RuntimeError(f"job is locked: {self.path}")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        self.acquired = True
        return self

    def __exit__(self, *_: object) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)
            self.acquired = False
