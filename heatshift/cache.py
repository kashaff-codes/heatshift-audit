"""Disk cache for completed FortyGuard activities.

FortyGuard charges again for an identical re-run, so every Completed result is
stored under sha256(endpoint + canonical JSON body). A later identical request
is served from disk and costs nothing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(body: Any) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_key(endpoint: str, body: Any) -> str:
    raw = endpoint.strip().lower() + "\n" + canonical_json(body)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DiskCache:
    def __init__(self, root: str | Path = ".cache"):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, endpoint: str, body: Any) -> dict | None:
        path = self._path(request_key(endpoint, body))
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, endpoint: str, body: Any, record: dict) -> Path:
        path = self._path(request_key(endpoint, body))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return path


    # -- pending markers: written right after submit, removed on a terminal status.
    # If the process dies mid-poll, the next run resumes this activity instead of
    # paying for a new one.
    def _pending_path(self, endpoint: str, body: Any) -> Path:
        return self.root / "pending" / f"{request_key(endpoint, body)}.json"

    def get_pending(self, endpoint: str, body: Any) -> str | None:
        path = self._pending_path(endpoint, body)
        try:
            return json.loads(path.read_text(encoding="utf-8"))["activity_id"]
        except (OSError, ValueError, KeyError):
            return None

    def put_pending(self, endpoint: str, body: Any, activity_id: str) -> None:
        path = self._pending_path(endpoint, body)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"endpoint": endpoint, "activity_id": activity_id}), encoding="utf-8")

    def clear_pending(self, endpoint: str, body: Any) -> None:
        try:
            self._pending_path(endpoint, body).unlink()
        except OSError:
            pass


class NullCache:
    """Cache that stores nothing (used in tests / --no-cache)."""

    def get(self, endpoint: str, body: Any) -> dict | None:
        return None

    def put(self, endpoint: str, body: Any, record: dict) -> None:
        return None

    def get_pending(self, endpoint: str, body: Any) -> str | None:
        return None

    def put_pending(self, endpoint: str, body: Any, activity_id: str) -> None:
        return None

    def clear_pending(self, endpoint: str, body: Any) -> None:
        return None
