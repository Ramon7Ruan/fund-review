"""缓存与降级链测试。全部用假数据，不访问网络。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from data_pipeline.cache.store import MemoryCache, SqliteCache
from data_pipeline.fallback import SourceChain
from data_pipeline.sources.akshare_source import SourceUnavailable


def test_memory_cache_roundtrip() -> None:
    cache = MemoryCache()
    cache.set("k", {"a": 1})
    assert cache.get("k") == {"a": 1}


def test_memory_cache_ttl_expires() -> None:
    cache = MemoryCache()
    cache.set("k", 1, ttl_seconds=1)
    assert cache.get("k") == 1
    time.sleep(1.05)
    assert cache.get("k") is None


def test_sqlite_cache_roundtrip(tmp_path: Path) -> None:
    cache = SqliteCache(tmp_path / "t.db")
    cache.set("k", [1, 2, 3])
    assert cache.get("k") == [1, 2, 3]
    cache.clear()
    assert cache.get("k") is None
    cache.close()


def test_sqlite_cache_ttl(tmp_path: Path) -> None:
    cache = SqliteCache(tmp_path / "t.db")
    cache.set("k", "v", ttl_seconds=1)
    time.sleep(1.05)
    assert cache.get("k") is None
    cache.close()


def test_chain_falls_back_to_second_source() -> None:
    calls: list[str] = []

    def primary() -> list[int]:
        calls.append("primary")
        raise RuntimeError("主源挂了")

    def backup() -> list[int]:
        calls.append("backup")
        return [1, 2]

    outcome = SourceChain("测试", [("primary", primary), ("backup", backup)]).fetch()

    assert outcome.data == [1, 2]
    assert outcome.source == "backup"
    assert calls == ["primary", "backup"]
    assert len(outcome.attempts) == 1


def test_chain_raises_when_all_fail() -> None:
    def broken() -> None:
        raise RuntimeError("坏")

    with pytest.raises(SourceUnavailable) as exc:
        SourceChain("测试", [("a", broken), ("b", broken)]).fetch()
    assert "全部数据源失败" in str(exc.value)


def test_chain_requires_at_least_one_source() -> None:
    with pytest.raises(ValueError):
        SourceChain("测试", [])
