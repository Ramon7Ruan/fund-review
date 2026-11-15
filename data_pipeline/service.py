"""数据服务：缓存 + 降级链的唯一入口。

上层（api）只与本模块打交道，不直接调用 akshare。
测试环境注入 MemoryCache 与假数据源即可，不访问网络。
"""

from __future__ import annotations

from typing import Any

from data_pipeline.cache.store import Cache, MemoryCache
from data_pipeline.fallback import SourceChain
from data_pipeline.sources import akshare_source

NAV_TTL_SECONDS = 6 * 3600
HOLDINGS_TTL_SECONDS = 7 * 24 * 3600


class DataService:
    def __init__(
        self,
        cache: Cache | None = None,
        nav_chain: SourceChain | None = None,
        holdings_chain: SourceChain | None = None,
    ) -> None:
        self.cache: Cache = cache or MemoryCache()
        self.nav_chain = nav_chain or SourceChain(
            "基金净值", [("akshare.eastmoney", akshare_source.fetch_fund_nav)]
        )
        self.holdings_chain = holdings_chain or SourceChain(
            "基金持仓", [("akshare.eastmoney", akshare_source.fetch_fund_holdings)]
        )

    # ---------- 基金信息 ----------

    def get_fund(self, code: str) -> dict[str, Any]:
        key = f"fund:basic:{code}"
        cached = self.cache.get(key)
        if cached is not None:
            return {**cached, "cached": True}
        info = akshare_source.fetch_fund_basic(code)
        self.cache.set(key, info, ttl_seconds=HOLDINGS_TTL_SECONDS)
        return {**info, "cached": False}

    # ---------- 净值 ----------

    def get_nav(
        self, code: str, month: str | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """返回该基金全部净值（或指定月份的子集）与数据来源信息。"""
        key = f"nav:all:{code}"
        series = self.cache.get(key)
        cached = series is not None
        source = "cache"
        attempts: list[str] = []

        if series is None:
            outcome = self.nav_chain.fetch(code)
            series = outcome.data
            source = outcome.source
            attempts = outcome.attempts
            self.cache.set(key, series, ttl_seconds=NAV_TTL_SECONDS)

        filtered = series
        if month:
            filtered = [p for p in series if str(p["date"]).startswith(month)]

        meta = {
            "source": source,
            "cached": cached,
            "total_points": len(series),
            "month_points": len(filtered) if month else len(series),
            "attempts": attempts,
        }
        return filtered, meta

    # ---------- 持仓 ----------

    def get_holdings(self, code: str, year: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        key = f"holdings:{code}:{year}"
        rows = self.cache.get(key)
        cached = rows is not None
        source = "cache"
        attempts: list[str] = []

        if rows is None:
            outcome = self.holdings_chain.fetch(code, year)
            rows = outcome.data
            source = outcome.source
            attempts = outcome.attempts
            self.cache.set(key, rows, ttl_seconds=HOLDINGS_TTL_SECONDS)

        latest_quarter = rows[0]["quarter"] if rows else ""
        latest = [r for r in rows if r["quarter"] == latest_quarter]
        meta = {
            "source": source,
            "cached": cached,
            "quarter": latest_quarter,
            "count": len(latest),
            "attempts": attempts,
        }
        return latest, meta

    def close(self) -> None:
        close = getattr(self.cache, "close", None)
        if callable(close):
            close()
