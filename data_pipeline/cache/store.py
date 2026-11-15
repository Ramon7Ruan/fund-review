"""缓存：SQLite 实现。

缓存键由调用方决定（建议 f"{source}:{kind}:{key}"）。
TTL 为秒数，0 表示不过期。
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Protocol


class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl_seconds: int = 0) -> None: ...
    def clear(self) -> None: ...


class SqliteCache:
    """极简键值缓存，值以 JSON 存储。"""

    def __init__(self, path: str | Path = "data/cache/fund_review.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at REAL NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.commit()

    def get(self, key: str) -> Any | None:
        row = self._conn.execute(
            "SELECT value, expires_at FROM kv WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        value, expires_at = row
        if expires_at and expires_at < time.time():
            self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
            self._conn.commit()
            return None
        return json.loads(value)

    def set(self, key: str, value: Any, ttl_seconds: int = 0) -> None:
        expires_at = time.time() + ttl_seconds if ttl_seconds else 0.0
        self._conn.execute(
            "INSERT OR REPLACE INTO kv (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False), expires_at),
        )
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM kv")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class MemoryCache:
    """测试与无盘环境使用。"""

    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at and expires_at < time.time():
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int = 0) -> None:
        self._data[key] = (value, time.time() + ttl_seconds if ttl_seconds else 0.0)

    def clear(self) -> None:
        self._data.clear()
