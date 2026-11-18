"""Source precedence and adjusted-NAV contract without network access."""

from __future__ import annotations

import pytest

from api.routes.review import review
from api.schemas import ReviewRequest
from data_pipeline.cache.store import MemoryCache
from data_pipeline.fallback import SourceChain
from data_pipeline.fund_store import FundDataStore
from data_pipeline.service import DataService
from data_pipeline.sources import akshare_source, eastmoney_dividends
from data_pipeline.sources.akshare_source import SourceUnavailable
from tests.fakes import FakeService


def _fail(*args):
    raise SourceUnavailable("offline")


def _service(tmp_path, fetchers):
    return DataService(
        cache=MemoryCache(),
        fund_store=FundDataStore(tmp_path / "fund.db"),
        nav_chain=SourceChain("净值", fetchers),
        holdings_chain=SourceChain("持仓", [("remote", _fail)]),
    )


def test_public_nav_name_and_source_order(tmp_path):
    points = [{"date": "2026-09-30", "nav": 1.0}]
    service = _service(tmp_path, [("akshare.eastmoney", lambda code: points)])
    assert service.get_nav("110022")[1]["source"] == "akshare.eastmoney"
    service.close()
    service = _service(
        tmp_path,
        [("akshare.eastmoney", _fail), ("danjuan", lambda code: points)],
    )
    assert service.get_nav("110022")[1]["source"] == "danjuan"
    service.close()


def test_offline_local_nav_and_holdings(tmp_path):
    service = _service(tmp_path, [("akshare.eastmoney", _fail), ("danjuan", _fail)])
    with pytest.raises(SourceUnavailable):
        service.get_nav("110022")
    service.import_nav_csv(
        "fund_code,date,unit_nav,dividend_per_share\n"
        "110022,2026-09-30,1,0\n110022,2026-10-30,1.1,0\n"
    )
    service.import_holdings_csv(
        "fund_code,as_of,stock_code,stock_name,weight\n110022,2026-10-30,600519,贵州茅台,0.1\n"
    )
    assert service.fund_store.nav_series("110022")[0] == {"date": "2026-09-30", "nav": 1.0}
    assert service.fund_store.nav_points("110022")[0]["dividend_per_share"] == 0.0
    rows, meta = service.get_nav("110022", "2026-10")
    assert rows == [{"date": "2026-10-30", "nav": 1.1}]
    assert meta["source"] == "local_import"
    assert meta["fallback"] is True
    assert meta["as_of"] == "2026-10-30"
    holdings, meta = service.get_holdings("110022", "2026", "2026-10")
    assert holdings[0]["code"] == "600519"
    assert meta["source"] == "local_import"
    assert meta["as_of"] == "2026-10-30"
    assert service.get_holdings("110022", "2026", "2026-11")[0] == []
    service.close()


def test_offline_local_fund_identity(tmp_path, monkeypatch):
    service = _service(tmp_path, [("remote", _fail)])
    service.import_nav_csv("fund_code,date,unit_nav,dividend_per_share\n110022,2026-10-30,1,0\n")
    monkeypatch.setattr(akshare_source, "fetch_fund_basic", _fail)
    fund = service.get_fund("110022")
    assert fund["code"] == "110022"
    assert fund["source"] == "local_import"
    service.close()


@pytest.mark.parametrize("dividend,expected", [(0.2, 1.21), (0.0, 0.99)])
def test_adjusted_nav_dividend_branches(tmp_path, monkeypatch, dividend, expected):
    nav = [
        {"date": "2026-09-30", "nav": 1.0},
        {"date": "2026-10-15", "nav": 0.9},
        {"date": "2026-10-30", "nav": 0.99},
    ]
    service = _service(tmp_path, [("akshare.eastmoney", lambda code: nav)])
    monkeypatch.setattr(
        eastmoney_dividends,
        "fetch_fund_dividends",
        lambda code: [{"date": "2026-10-15", "dividend_per_share": dividend}] if dividend else [],
    )
    rows, meta = service.get_nav_adjusted("110022", "2026-10")
    assert rows[-1]["total_return_index"] == pytest.approx(expected)
    assert meta["dividend_source"] == "eastmoney"
    service.close()


def test_dividend_failure_is_explicit_and_nonblocking(tmp_path, monkeypatch):
    service = _service(
        tmp_path,
        [
            (
                "akshare.eastmoney",
                lambda code: [
                    {"date": "2026-10-01", "nav": 1.0},
                    {"date": "2026-10-30", "nav": 1.1},
                ],
            )
        ],
    )
    monkeypatch.setattr(eastmoney_dividends, "fetch_fund_dividends", _fail)
    rows, meta = service.get_nav_adjusted("110022", "2026-10")
    assert rows[-1]["total_return_index"] == pytest.approx(1.1)
    assert meta["dividend_source"] == "unavailable"
    assert "未做复权" in meta["warnings"][0]
    service.close()


def test_review_exposes_adjusted_source_and_keeps_results():
    response = review(ReviewRequest(fund_code="110022", month="2026-10"), FakeService())
    assert response.results["returns.interval"].status == "ready"
    assert response.meta["nav_total_return"]["dividend_source"] == "fake"


def test_dividends_are_cached_across_calls(tmp_path, monkeypatch):
    """分红记录变动极少，重复请求不应反复访问数据源。"""
    calls: list[str] = []

    def fake_dividends(code):
        calls.append(code)
        return [{"date": "2026-10-15", "dividend_per_share": 0.2}]

    monkeypatch.setattr(eastmoney_dividends, "fetch_fund_dividends", fake_dividends)
    service = _service(
        tmp_path,
        [
            (
                "remote",
                lambda code: [
                    {"date": "2026-10-15", "nav": 0.9},
                    {"date": "2026-10-30", "nav": 0.99},
                ],
            )
        ],
    )
    service.get_nav_adjusted("110022", "2026-10")
    service.get_nav_adjusted("110022", "2026-10")

    assert len(calls) == 1, "第二次请求应命中分红缓存"
    service.close()
