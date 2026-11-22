"""数据服务：缓存 + 降级链的唯一入口。

上层（api）只与本模块打交道，不直接调用 akshare。
测试环境注入 MemoryCache 与假数据源即可，不访问网络。
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from data_pipeline.cache.store import Cache, MemoryCache
from data_pipeline.fallback import SourceChain
from data_pipeline.fund_store import FundDataStore
from data_pipeline.sources import akshare_source, danjuan_fund, eastmoney_dividends
from data_pipeline.sources.akshare_source import SourceUnavailable
from engine.holdings import build_periods
from engine.returns.dividend import total_return_index

NAV_TTL_SECONDS = 6 * 3600
HOLDINGS_TTL_SECONDS = 7 * 24 * 3600
# 分红变动极少，缓存一周；sync_nav 主动同步时不走缓存
DIVIDEND_TTL_SECONDS = 7 * 24 * 3600
# 行业映射抓取失败后的退避窗口：期间不再重试 31 个行业
INDUSTRY_FAIL_KEY = "industry:map:failed"
INDUSTRY_FAIL_TTL_SECONDS = 60
# 快照是降级数据，只缓存 10 分钟，接口恢复后尽快重试实时映射
INDUSTRY_SNAPSHOT_TTL_SECONDS = 600
INDUSTRY_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "snapshots" / "sw_industry_map.json"
)


def load_industry_snapshot(path: Path | None = None) -> dict[str, Any] | None:
    """读取本地行业映射快照；文件缺失或格式不对时返回 None，不抛错。"""
    target = path or INDUSTRY_SNAPSHOT_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    mapping = payload.get("map")
    if not isinstance(mapping, dict) or not mapping:
        return None
    return {
        "map": {str(code).zfill(6): str(industry) for code, industry in mapping.items()},
        "as_of": str(payload.get("as_of", "")),
        "source": str(payload.get("source", "snapshot")),
    }


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

    def get_holdings_periods(
        self, code: str, year: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """返回该年所有披露期（时间倒序），每期含 quarter / disclosure_type / positions。

        与 get_holdings 共用同一份缓存，不重复抓取。抓取失败返回空列表并标注来源，
        由调用方决定是否降级，不在这里抛错。
        """
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
                rows = []
                source = "unavailable"

        periods = build_periods(rows or [])
        return (
            [
                {
                    "quarter": period.quarter,
                    "disclosure_type": period.disclosure_type,
                    "positions": list(period.positions),
                }
                for period in periods
            ],
            {
                "source": source,
                "cached": cached,
                "periods": len(periods),
                "attempts": attempts,
            },
        )

    # ---------- 归因：个股行情与申万行业 ----------

    def get_quotes(
        self, codes: list[str] | tuple[str, ...], month: str
    ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        """批量获取持仓个股当月日线。单只失败只记录，不阻塞其他股票。"""
        wanted = {str(c).zfill(6) for c in codes}
        result: dict[str, list[dict[str, Any]]] = {}
        missing: list[str] = []
        sources: set[str] = set()
        cached_hits = 0

        for code in sorted(wanted):
            key = f"quotes:{code}:{month}"
            bars = self.cache.get(key)
            if bars is not None:
                result[code] = bars
                cached_hits += 1
                continue
            try:
                bars, source = akshare_source.fetch_stock_bars(code, f"{month}-01", f"{month}-31")
            except SourceUnavailable as exc:
                missing.append(f"{code}：{exc}")
                continue
            month_bars = [b for b in bars if str(b["date"]).startswith(month)]
            if not month_bars:
                missing.append(f"{code}：{month} 无行情")
                continue
            result[code] = month_bars
            sources.add(source)
            self.cache.set(key, month_bars, ttl_seconds=NAV_TTL_SECONDS)

        meta = {
            "source": "akshare." + ",".join(sorted(sources)) if sources else "cache",
            "adjust": "none",
            "requested": len(wanted),
            "count": len(result),
            "cached": cached_hits == len(result) and not missing,
            "missing": missing,
        }
        return result, meta

    def get_industry_map(
        self, codes: list[str] | tuple[str, ...]
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """个股 → 申万一级行业。

        缓存 7 天。抓取失败时依次：本地快照 → 60 秒退避。
        退避期间直接抛错，避免每次请求都重试 31 个行业拖慢页面。
        """
        key = "industry:map:v2"
        cached = self.cache.get(key)
        attempts: list[str] = []

        if cached is not None:
            mapping: dict[str, str] = cached["map"]
            source = str(cached.get("source", "cache"))
            as_of = str(cached.get("as_of", ""))
        else:
            if self.cache.get(INDUSTRY_FAIL_KEY):
                raise SourceUnavailable("行业映射暂不可用（退避中），请稍后重试")

            mapping = {}
            source = "akshare.sw"
            as_of = ""
            try:
                for item in akshare_source.fetch_sw_industries():
                    try:
                        members = akshare_source.fetch_sw_constituents(item["sw_code"])
                    except SourceUnavailable as exc:
                        attempts.append(f"{item['industry']}：{exc}")
                        continue
                    for member in members:
                        mapping.setdefault(member["code"], item["industry"])
                if not mapping:
                    raise SourceUnavailable("申万成分股全部抓取失败，无法建立行业映射")
            except SourceUnavailable as exc:
                snapshot = load_industry_snapshot()
                if snapshot is None:
                    self.cache.set(INDUSTRY_FAIL_KEY, True, ttl_seconds=INDUSTRY_FAIL_TTL_SECONDS)
                    raise
                mapping = snapshot["map"]
                source = f"snapshot:{snapshot['source']}"
                as_of = snapshot["as_of"]
                attempts.append(f"实时抓取失败，改用快照（{as_of or '未知日期'}）：{exc}")

            ttl = HOLDINGS_TTL_SECONDS if source == "akshare.sw" else INDUSTRY_SNAPSHOT_TTL_SECONDS
            self.cache.set(
                key,
                {"map": mapping, "source": source, "as_of": as_of},
                ttl_seconds=ttl,
            )

        wanted = {str(c).zfill(6) for c in codes}
        subset = {c: mapping[c] for c in sorted(wanted) if c in mapping}
        meta = {
            "source": source,
            "as_of": as_of,
            "requested": len(wanted),
            "mapped": len(subset),
            "unmapped": sorted(wanted - set(subset)),
            "attempts": attempts,
        }
        return subset, meta

    def get_industry_returns(
        self, month: str, industries: list[str] | tuple[str, ...] | None = None
    ) -> tuple[dict[str, float], dict[str, Any]]:
        """申万一级行业指数区间收益 {industry: r}，用首末收盘比值。"""
        listing_key = "industry:list:v1"
        listing = self.cache.get(listing_key)
        if listing is None:
            listing = akshare_source.fetch_sw_industries()
            self.cache.set(listing_key, listing, ttl_seconds=HOLDINGS_TTL_SECONDS)
        code_by_name = {item["industry"]: item["sw_code"] for item in listing}

        targets = list(industries) if industries is not None else sorted(code_by_name)
        result: dict[str, float] = {}
        missing: list[str] = []
        for name in targets:
            sw_code = code_by_name.get(name)
            if not sw_code:
                missing.append(f"{name}：无对应申万代码")
                continue
            key = f"industry:return:{sw_code}:{month}"
            cached = self.cache.get(key)
            if cached is not None:
                result[name] = cached
                continue
            try:
                bars = akshare_source.fetch_sw_index_bars(sw_code, f"{month}-01", f"{month}-31")
            except SourceUnavailable as exc:
                missing.append(f"{name}：{exc}")
                continue
            if len(bars) < 2:
                missing.append(f"{name}：有效点不足两点")
                continue
            value = round(bars[-1]["close"] / bars[0]["close"] - 1.0, 8)
            result[name] = value
            self.cache.set(key, value, ttl_seconds=NAV_TTL_SECONDS)

        return result, {
            "source": "akshare.sw",
            "count": len(result),
            "missing": missing,
            "adjust": "none",
        }

    def get_events(
        self, fund_code: str, holding_codes: list[str] | tuple[str, ...], month: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """抓取基金自身与披露持仓个股的当月公告。

        数据层只负责抓取与归一化；是否展示由 engine.attribution.events 的
        四条准入规则决定，抓到的原始公告不直接等同于可展示事件。
        """
        key = f"events:{fund_code}:{month}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached, {"source": "cache", "cached": True, "count": len(cached), "missing": []}

        compact = month.replace("-", "")
        start, end = f"{compact}01", f"{compact}31"
        raw: list[dict[str, Any]] = []
        missing: list[str] = []

        try:
            raw.extend(akshare_source.fetch_fund_announcements(fund_code))
        except SourceUnavailable as exc:
            missing.append(f"基金公告：{exc}")

        for code in sorted({str(c).zfill(6) for c in holding_codes}):
            try:
                raw.extend(akshare_source.fetch_stock_announcements(code, start, end))
            except SourceUnavailable as exc:
                missing.append(f"{code}：{exc}")

        if not raw and missing:
            raise SourceUnavailable("；".join(missing))

        self.cache.set(key, raw, ttl_seconds=NAV_TTL_SECONDS)
        return raw, {
            "source": "akshare.eastmoney",
            "cached": False,
            "count": len(raw),
            "missing": missing,
        }

    def close(self) -> None:
        if self._fund_store is not None:
            self._fund_store.close()
        close = getattr(self.cache, "close", None)
        if callable(close):
            close()
