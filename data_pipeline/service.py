"""数据服务：缓存 + 降级链的唯一入口。

上层（api）只与本模块打交道，不直接调用 akshare。
测试环境注入 MemoryCache 与假数据源即可，不访问网络。
"""

from __future__ import annotations

import csv
import io
from typing import Any

from data_pipeline.cache.store import Cache, MemoryCache
from data_pipeline.fallback import SourceChain
from data_pipeline.fund_store import FundDataStore
from data_pipeline.sources import akshare_source, danjuan_fund, eastmoney_dividends
from data_pipeline.sources.akshare_source import SourceUnavailable
from engine.returns.dividend import total_return_index

NAV_TTL_SECONDS = 6 * 3600
HOLDINGS_TTL_SECONDS = 7 * 24 * 3600
# 分红变动极少，缓存一周；sync_nav 主动同步时不走缓存
DIVIDEND_TTL_SECONDS = 7 * 24 * 3600


class DataService:
    def __init__(
        self,
        cache: Cache | None = None,
        nav_chain: SourceChain | None = None,
        holdings_chain: SourceChain | None = None,
        fund_store: FundDataStore | None = None,
    ) -> None:
        self.cache: Cache = cache or MemoryCache()
        self.nav_chain = nav_chain or SourceChain(
            "基金净值",
            [
                ("akshare.eastmoney", akshare_source.fetch_fund_nav),
                ("danjuan", danjuan_fund.fetch_fund_nav),
            ],
        )
        self.holdings_chain = holdings_chain or SourceChain(
            "基金持仓", [("akshare.eastmoney", akshare_source.fetch_fund_holdings)]
        )
        self._fund_store = fund_store

    @property
    def fund_store(self) -> FundDataStore:
        if self._fund_store is None:
            self._fund_store = FundDataStore()
        return self._fund_store

    def import_holdings_csv(self, content: str | bytes) -> dict[str, int]:
        return self.fund_store.import_holdings_csv(content)

    def month_snapshots(self, code: str, month: str) -> dict[str, Any]:
        return self.fund_store.month_snapshots(code, month)

    def import_nav_csv(self, content: str | bytes) -> dict[str, int]:
        return self.fund_store.import_nav_csv(content)

    def sync_nav(self, code: str) -> dict[str, Any]:
        """拉取净值和除息记录，校验后一次性写入持久表。"""
        nav, meta = self.get_nav(code)
        dividends = {
            item["date"]: item["dividend_per_share"]
            for item in eastmoney_dividends.fetch_fund_dividends(code)
        }
        if set(dividends) - {item["date"] for item in nav}:
            raise SourceUnavailable("分红除息日缺少对应基金净值，不能完成复权")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(("fund_code", "date", "unit_nav", "dividend_per_share"))
        for item in nav:
            writer.writerow((code, item["date"], item["nav"], dividends.get(item["date"], 0)))
        return {**self.import_nav_csv(output.getvalue()), "nav_source": meta["source"]}

    # ---------- 基金信息 ----------

    def get_fund(self, code: str) -> dict[str, Any]:
        key = f"fund:basic:{code}"
        cached = self.cache.get(key)
        if cached is not None:
            return {**cached, "cached": True}
        try:
            info = akshare_source.fetch_fund_basic(code)
        except SourceUnavailable:
            if not self.fund_store.nav_series(code):
                raise
            info = {
                "code": code,
                "name": f"基金 {code}",
                "type": "",
                "company": "",
                "source": "local_import",
            }
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
            try:
                outcome = self.nav_chain.fetch(code)
                series = outcome.data
                source = outcome.source
                attempts = outcome.attempts
                self.cache.set(key, series, ttl_seconds=NAV_TTL_SECONDS)
            except SourceUnavailable as exc:
                attempts = [str(exc)]
                series = self.fund_store.nav_series(code)
                if not series:
                    raise
                source = "local_import"

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
        if source == "local_import":
            meta.update(fallback=True, as_of=series[-1]["date"])
        return filtered, meta

    def _fetch_dividends(self, code: str) -> list[dict[str, Any]]:
        """分红记录带缓存：变动极少，每次请求都抓会拖慢页面并可能触发风控。

        与 sync_nav 的区别：sync_nav 是用户主动同步，要最新数据，因此不走缓存。
        """
        key = f"dividends:{code}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        rows = eastmoney_dividends.fetch_fund_dividends(code)
        self.cache.set(key, rows, ttl_seconds=DIVIDEND_TTL_SECONDS)
        return rows

    def get_nav_adjusted(
        self, code: str, month: str | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Compute the total-return index over the full history, then select a month.

        返回的 total_return_index 以**数据源首日**锚定为 1（通常是基金成立附近），
        不是月初归一化。插件应使用首末比值计算区间收益，不要直接展示绝对值。
        """
        nav, nav_meta = self.get_nav(code)
        warnings: list[str] = []
        dividend_source = "eastmoney"
        if nav_meta["source"] == "local_import":
            dividends = {
                p["date"]: p["dividend_per_share"] for p in self.fund_store.nav_points(code)
            }
            dividend_source = "local_import"
        else:
            try:
                dividends = {
                    p["date"]: p["dividend_per_share"] for p in self._fetch_dividends(code)
                }
                missing = set(dividends) - {p["date"] for p in nav}
                if missing:
                    raise SourceUnavailable(f"除息日缺少对应净值：{sorted(missing)[0]}")
            except SourceUnavailable as exc:
                dividends = {}
                dividend_source = "unavailable"
                warnings.append(f"分红数据不可用，本次未做复权：{exc}")
        points = [
            {
                "date": p["date"],
                "unit_nav": p["nav"],
                "dividend_per_share": dividends.get(p["date"], 0.0),
            }
            for p in nav
        ]
        result = total_return_index(points)
        if month:
            result = [p for p in result if p["date"].startswith(month)]
        return (
            [{"date": p["date"], "total_return_index": p["total_return_index"]} for p in result],
            {**nav_meta, "dividend_source": dividend_source, "warnings": warnings},
        )

    # ---------- 持仓 ----------

    def get_holdings(
        self, code: str, year: str, month: str | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        key = f"holdings:{code}:{year}"
        rows = self.cache.get(key)
        cached = rows is not None
        source = "cache"
        attempts: list[str] = []

        if rows is None:
            try:
                outcome = self.holdings_chain.fetch(code, year)
                rows = outcome.data
                source = outcome.source
                attempts = outcome.attempts
                self.cache.set(key, rows, ttl_seconds=HOLDINGS_TTL_SECONDS)
            except SourceUnavailable as exc:
                attempts = [str(exc)]
                snapshot = self.month_snapshots(code, month or f"{year}-12")["end"]
                rows = snapshot["positions"] if snapshot else []
                source = "local_import" if rows else "unavailable"

        latest_quarter = rows[0].get("quarter", "") if rows else ""
        latest = [r for r in rows if r.get("quarter", "") == latest_quarter]
        meta = {
            "source": source,
            "cached": cached,
            "quarter": latest_quarter,
            "count": len(latest),
            "attempts": attempts,
        }
        if source == "local_import":
            meta.update(fallback=True, as_of=snapshot["as_of"])
        return latest, meta

    def close(self) -> None:
        if self._fund_store is not None:
            self._fund_store.close()
        close = getattr(self.cache, "close", None)
        if callable(close):
            close()
