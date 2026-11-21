"""归因数据接入：个股行情、行业映射、行业收益。全部用假数据源，不联网。"""

from __future__ import annotations

import pytest

from data_pipeline.cache.store import MemoryCache
from data_pipeline.service import DataService
from data_pipeline.sources import akshare_source
from data_pipeline.sources.akshare_source import SourceUnavailable


@pytest.fixture
def service():
    svc = DataService(cache=MemoryCache())
    yield svc
    svc.close()


def _bars(days: list[str], start: float = 10.0) -> list[dict]:
    return [
        {
            "date": day,
            "open": start,
            "high": start,
            "low": start,
            "close": start + i,
            "volume": 1.0,
            "amount": 1.0,
        }
        for i, day in enumerate(days)
    ]


def test_quotes_skip_failed_codes(service, monkeypatch):
    def fake(code, start, end):
        if code == "000001":
            raise SourceUnavailable("boom")
        return _bars(["2026-10-08", "2026-10-30"]), "sina"

    monkeypatch.setattr(akshare_source, "fetch_stock_bars", fake)
    rows, meta = service.get_quotes(["600519", "000001"], "2026-10")

    assert set(rows) == {"600519"}
    assert meta["count"] == 1
    assert meta["adjust"] == "none"
    assert any("000001" in item for item in meta["missing"])


def test_quotes_filter_month_and_cache(service, monkeypatch):
    calls: list[str] = []

    def fake(code, start, end):
        calls.append(code)
        return _bars(["2026-09-30", "2026-10-08", "2026-10-30"]), "sina"

    monkeypatch.setattr(akshare_source, "fetch_stock_bars", fake)
    rows, _ = service.get_quotes(["600519"], "2026-10")
    assert [b["date"] for b in rows["600519"]] == ["2026-10-08", "2026-10-30"]

    service.get_quotes(["600519"], "2026-10")
    assert calls == ["600519"], "第二次应命中缓存"


def test_industry_map_subset_and_unmapped(service, monkeypatch):
    monkeypatch.setattr(
        akshare_source,
        "fetch_sw_industries",
        lambda: [
            {"industry": "食品饮料", "sw_code": "801120"},
            {"industry": "电子", "sw_code": "801080"},
        ],
    )

    def fake_cons(sw_code):
        if sw_code == "801120":
            return [{"code": "600519", "name": "贵州茅台"}]
        return [{"code": "000001", "name": "平安银行"}]

    monkeypatch.setattr(akshare_source, "fetch_sw_constituents", fake_cons)
    mapping, meta = service.get_industry_map(["600519", "999999"])

    assert mapping == {"600519": "食品饮料"}
    assert meta["mapped"] == 1
    assert meta["unmapped"] == ["999999"]


def test_industry_map_cached(service, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        akshare_source,
        "fetch_sw_industries",
        lambda: [{"industry": "电子", "sw_code": "801080"}],
    )

    def fake_cons(sw_code):
        calls.append(sw_code)
        return [{"code": "000001", "name": "平安银行"}]

    monkeypatch.setattr(akshare_source, "fetch_sw_constituents", fake_cons)
    service.get_industry_map(["000001"])
    service.get_industry_map(["000001"])
    assert calls == ["801080"]


def test_industry_returns_ratio(service, monkeypatch):
    monkeypatch.setattr(
        akshare_source,
        "fetch_sw_industries",
        lambda: [{"industry": "食品饮料", "sw_code": "801120"}],
    )
    monkeypatch.setattr(
        akshare_source,
        "fetch_sw_index_bars",
        lambda sw, start, end: [
            {"date": "2026-10-08", "close": 100.0},
            {"date": "2026-10-30", "close": 110.0},
        ],
    )
    values, meta = service.get_industry_returns("2026-10", ["食品饮料"])
    assert values["食品饮料"] == pytest.approx(0.1)
    assert meta["count"] == 1
    assert meta["missing"] == []


def test_industry_returns_missing(service, monkeypatch):
    monkeypatch.setattr(akshare_source, "fetch_sw_industries", lambda: [])

    def boom(sw, start, end):
        raise SourceUnavailable("no data")

    monkeypatch.setattr(akshare_source, "fetch_sw_index_bars", boom)
    values, meta = service.get_industry_returns("2026-10", ["食品饮料"])
    assert values == {}
    assert any("食品饮料" in item for item in meta["missing"])
