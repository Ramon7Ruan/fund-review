"""Issue #1：时点持仓、净值复权与重复导入。"""

from __future__ import annotations

import pytest

from data_pipeline.cache.store import MemoryCache
from data_pipeline.fallback import SourceChain
from data_pipeline.fund_store import FundDataStore
from data_pipeline.service import DataService
from data_pipeline.sources import akshare_source, danjuan_fund, eastmoney_dividends
from data_pipeline.sources.akshare_source import SourceUnavailable
from engine.returns.dividend import total_return_index

HOLDINGS = """fund_code,as_of,stock_code,stock_name,weight
110022,2026-09-30,600519,贵州茅台,0.40
110022,2026-09-30,000333,美的集团,0.30
110022,2026-10-30,600519,贵州茅台,0.35
110022,2026-10-30,000333,美的集团,0.34
"""

NAV = """fund_code,date,unit_nav,dividend_per_share
110022,2026-09-30,1.00,0
110022,2026-10-15,0.90,0.20
110022,2026-10-30,0.99,0
"""


def test_monthly_snapshots_are_dated_and_reimport_is_idempotent(tmp_path) -> None:
    store = FundDataStore(tmp_path / "fund.db")
    assert store.import_holdings_csv(HOLDINGS.encode("utf-8-sig")) == {
        "imported": 2,
        "unchanged": 0,
    }
    assert store.import_holdings_csv(HOLDINGS) == {"imported": 0, "unchanged": 2}
    month = store.month_snapshots("110022", "2026-10")
    assert month["start"]["as_of"] == "2026-09-30"
    assert month["end"]["as_of"] == "2026-10-30"
    assert month["start"]["positions"][0]["weight"] == 0.4
    assert month["end"]["positions"][0]["weight"] == 0.35
    assert store.month_snapshots("110022", "2026-11")["end"] is None
    store.close()


def test_conflicting_snapshot_rolls_back_whole_import(tmp_path) -> None:
    store = FundDataStore(tmp_path / "fund.db")
    store.import_holdings_csv(HOLDINGS)
    conflict = """fund_code,as_of,stock_code,stock_name,weight
110022,2026-11-30,600519,贵州茅台,0.20
110022,2026-10-30,600519,贵州茅台,0.50
"""
    with pytest.raises(ValueError, match="拒绝覆盖"):
        store.import_holdings_csv(conflict)
    assert store.snapshot("110022", "2026-11-30") is None
    assert store.snapshot("110022", "2026-10-30")["positions"][0]["weight"] == 0.35
    store.close()


def test_dividend_reinvestment_and_duplicate_nav(tmp_path) -> None:
    store = FundDataStore(tmp_path / "fund.db")
    assert store.import_nav_csv(NAV) == {"imported": 3, "unchanged": 0}
    assert store.import_nav_csv(NAV) == {"imported": 0, "unchanged": 3}
    series = total_return_index(store.nav_points("110022"))
    assert [row["total_return_index"] for row in series] == pytest.approx([1.0, 1.1, 1.21])
    assert series[1]["unit_nav"] == 0.9
    assert series[1]["dividend_per_share"] == 0.2
    with pytest.raises(ValueError, match="拒绝覆盖"):
        store.import_nav_csv(NAV.replace("0.90,0.20", "0.90,0.10"))
    store.close()


def test_invalid_weight_and_duplicate_stock_are_rejected(tmp_path) -> None:
    store = FundDataStore(tmp_path / "fund.db")
    with pytest.raises(ValueError, match="0 到 1"):
        store.import_holdings_csv(HOLDINGS.replace("0.40", "40"))
    with pytest.raises(ValueError, match="重复"):
        store.import_holdings_csv(HOLDINGS + "110022,2026-09-30,600519,贵州茅台,0.20\n")
    assert store.snapshot("110022", "2026-09-30") is None
    store.close()


def test_sync_nav_combines_history_and_ex_dividend_events(tmp_path, monkeypatch) -> None:
    store = FundDataStore(tmp_path / "fund.db")
    nav = [
        {"date": "2026-09-30", "nav": 1.0},
        {"date": "2026-10-15", "nav": 0.9},
        {"date": "2026-10-30", "nav": 0.99},
    ]
    service = DataService(
        cache=MemoryCache(),
        fund_store=store,
        nav_chain=SourceChain("净值", [("fake", lambda code: nav)]),
    )
    monkeypatch.setattr(
        eastmoney_dividends,
        "fetch_fund_dividends",
        lambda code: [{"date": "2026-10-15", "dividend_per_share": 0.2}],
    )
    assert service.sync_nav("110022")["imported"] == 3
    assert service.sync_nav("110022")["unchanged"] == 3
    assert total_return_index(store.nav_points("110022"))[-1][
        "total_return_index"
    ] == pytest.approx(1.21)
    service.close()


def test_nav_source_falls_back_when_primary_fails(monkeypatch) -> None:
    def unavailable(code):
        raise SourceUnavailable("主源不可用")

    monkeypatch.setattr(akshare_source, "fetch_fund_nav", unavailable)
    monkeypatch.setattr(
        danjuan_fund,
        "fetch_fund_nav",
        lambda code: [{"date": "2026-10-30", "nav": 1.2}],
    )
    service = DataService(cache=MemoryCache())
    rows, meta = service.get_nav("110022")
    assert rows == [{"date": "2026-10-30", "nav": 1.2}]
    assert meta["source"] == "danjuan"


def test_dividend_source_converts_per_ten_and_never_hides_bad_fields(monkeypatch) -> None:
    class Page:
        text = """<title>测试基金(161606)基金分红送配 _ 天天基金网</title>
        <table><tr><td>其他表格</td></tr></table>
        <table class="w782 comm cfxq"><tr><th>年份</th><th>权益登记日</th>
        <th>除息日</th><th>每10份分红</th><th>分红发放日</th></tr>
        <tr><td>2026</td><td>2026-10-14</td><td>2026-10-15</td>
        <td>每10份派现金0.0500元</td><td>2026-10-17</td></tr></table>"""

        def raise_for_status(self):
            pass

    page = Page()
    monkeypatch.setattr(eastmoney_dividends.httpx, "get", lambda *args, **kwargs: page)
    assert eastmoney_dividends.fetch_fund_dividends("161606") == [
        {"date": "2026-10-15", "dividend_per_share": 0.005}
    ]
    page.text = page.text.replace("每10份派现金0.0500元", "unknown")
    with pytest.raises(SourceUnavailable, match="分红信息不可用"):
        eastmoney_dividends.fetch_fund_dividends("161606")
    page.text = page.text.replace("161606", "110022")
    with pytest.raises(SourceUnavailable, match="基金代码"):
        eastmoney_dividends.fetch_fund_dividends("161606")
    page.text = """<title>测试基金(161606)基金分红送配</title>
    <table class="cfxq"><tr><th>年份</th><th>权益登记日</th><th>除息日</th>
    <th>每10份分红</th><th>分红发放日</th></tr></table>"""
    with pytest.raises(SourceUnavailable, match="未返回数据状态"):
        eastmoney_dividends.fetch_fund_dividends("161606")


def test_explicit_no_dividend_page_is_accepted(monkeypatch) -> None:
    class Page:
        text = """<title>测试基金(110022)基金分红送配 _ 天天基金网</title>
        <table class="comm cfxq"><tr><th>年份</th><th>权益登记日</th>
        <th>除息日</th><th>每10份分红</th><th>分红发放日</th></tr>
        <tr><td colspan="5">暂无分红信息!</td></tr></table>"""

        def raise_for_status(self):
            pass

    monkeypatch.setattr(eastmoney_dividends.httpx, "get", lambda *args, **kwargs: Page())
    assert eastmoney_dividends.fetch_fund_dividends("110022") == []


def test_nav_import_requires_explicit_dividend_column(tmp_path) -> None:
    store = FundDataStore(tmp_path / "fund.db")
    with pytest.raises(ValueError, match="dividend_per_share"):
        store.import_nav_csv("fund_code,date,unit_nav\n110022,2026-10-30,1.0\n")
    store.close()
