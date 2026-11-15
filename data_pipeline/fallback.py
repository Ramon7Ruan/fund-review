"""数据源降级链。

顺序：主数据源 → 备用数据源 → 上层缓存 → 明确报错。
本模块只负责前两级的切换，缓存由 service 层处理。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from data_pipeline.sources.akshare_source import SourceUnavailable

Fetcher = Callable[..., Any]


@dataclass
class FetchOutcome:
    data: Any
    source: str
    attempts: list[str] = field(default_factory=list)


class SourceChain:
    """按顺序尝试多个抓取函数，第一个成功的即返回。"""

    def __init__(self, name: str, fetchers: list[tuple[str, Fetcher]]) -> None:
        if not fetchers:
            raise ValueError(f"{name} 至少需要一个数据源")
        self.name = name
        self.fetchers = fetchers

    def fetch(self, *args: Any, **kwargs: Any) -> FetchOutcome:
        attempts: list[str] = []
        for label, fetcher in self.fetchers:
            try:
                data = fetcher(*args, **kwargs)
                return FetchOutcome(data=data, source=label, attempts=attempts)
            except Exception as exc:  # noqa: BLE001 - 任一源失败都要继续尝试
                attempts.append(f"{label}: {type(exc).__name__}: {exc}")
        raise SourceUnavailable(f"{self.name} 全部数据源失败：" + " | ".join(attempts))
