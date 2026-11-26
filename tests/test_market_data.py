"""归因数据接入：个股行情、行业映射、行业收益。全部用假数据源，不联网。"""

from __future__ import annotations

from types import SimpleNamespace

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


def test_quote_adapter_uses_current_sina_and_tencent_fallback(monkeypatch):
    data = _bars(["2026-09-30"])[0]

    def sina(**kwargs):
        assert kwargs == {"symbol": "sh600519", "start_date": "20260901", "end_date": "20260930"}
        return SimpleNamespace(empty=False, iterrows=lambda: [(0, data)])

    def tencent(**kwargs):
        assert kwargs["end_date"] == "2026-09-30"
        return SimpleNamespace(empty=False, iterrows=lambda: [(0, data)])

    ak = SimpleNamespace(stock_zh_a_hist_sina=sina, stock_zh_a_hist_tx=tencent)
    monkeypatch.setattr(akshare_source, "_akshare", lambda: ak)
    args = ("600519", "2026-09-01", "2026-09-30")
    assert akshare_source.fetch_stock_bars(*args) == ([data], "sina")
    ak.stock_zh_a_hist_sina = lambda **_: SimpleNamespace(empty=True)
    assert akshare_source.fetch_stock_bars(*args) == ([data], "tencent")


@pytest.mark.parametrize(("month", "end"), [("2026-09", "2026-09-30"), ("2024-02", "2024-02-29")])
def test_quotes_and_events_use_actual_month_end(service, monkeypatch, month, end):
    start = f"{month}-01"

    def quotes(code, first, last):
        assert (code, first, last) == ("600519", start, end)
        return _bars([start, end]), "sina"

    def notices(*, symbol, indicator, start_date, end_date):
        assert (symbol, indicator, start_date, end_date) == ("600519", "全部", start, end)
        row = {"代码": "600519", "名称": "茅台", "公告标题": "测试", "公告日期": end, "网址": ""}
        return SimpleNamespace(empty=False, iterrows=lambda: [(0, row)])

    monkeypatch.setattr(akshare_source, "fetch_stock_bars", quotes)
    monkeypatch.setattr(akshare_source, "fetch_fund_announcements", lambda _: [])
    monkeypatch.setattr(
        akshare_source,
        "_akshare",
        lambda: SimpleNamespace(__version__="1.20.65", stock_individual_notice_report=notices),
    )
    bars, _ = service.get_quotes(["600519"], month)
    events, meta = service.get_events("110022", ["600519"], month)

    assert bars["600519"][-1]["date"] == end
    assert events[0]["date"] == end
    assert not meta["missing"]


def test_partial_event_failure_can_recover(service, monkeypatch):
    def unavailable(*args):
        raise SourceUnavailable("暂不可用")

    monkeypatch.setattr(akshare_source, "fetch_fund_announcements", lambda _: [{"fund": True}])
    monkeypatch.setattr(akshare_source, "fetch_stock_announcements", unavailable)
    _, partial = service.get_events("110022", ["600519"], "2026-09")
    assert partial["missing"]

    monkeypatch.setattr(akshare_source, "fetch_stock_announcements", lambda *_: [{"stock": True}])
    events, recovered = service.get_events("110022", ["600519"], "2026-09")
    assert events == [{"fund": True}, {"stock": True}]
    assert not recovered["missing"]


@pytest.mark.parametrize("count", [0, 1])
def test_notice_missing_columns_only_degrade_to_empty_when_confirmed(monkeypatch, count):
    def fail(**kwargs):
        raise KeyError("代码")

    def verify(url, *, params, timeout):
        assert params["stock_list"] == "600519"
        assert params["end_time"] == "2026-09-30"
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"success": 1, "data": {"total_hits": count, "list": []}},
        )

    monkeypatch.setattr(
        akshare_source,
        "_akshare",
        lambda: SimpleNamespace(__version__="1.20.65", stock_individual_notice_report=fail),
    )
    monkeypatch.setattr(akshare_source.httpx, "get", verify)
    args = ("600519", "2026-09-01", "2026-09-30")
    if count == 0:
        assert akshare_source.fetch_stock_announcements(*args) == []
    else:
        with pytest.raises(SourceUnavailable, match="KeyError"):
            akshare_source.fetch_stock_announcements(*args)


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


def test_industry_returns_missing(service, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_pipeline.service.INDUSTRY_BARS_SNAPSHOT_PATH", tmp_path / "absent.json"
    )
    monkeypatch.setattr(akshare_source, "fetch_sw_industries", lambda: [])

    def boom(sw, start, end):
        raise SourceUnavailable("no data")

    monkeypatch.setattr(akshare_source, "fetch_sw_index_bars", boom)
    values, meta = service.get_industry_returns("2026-10", ["食品饮料"])
    assert values == {}
    assert any("食品饮料" in item for item in meta["missing"])


def test_announcements_require_min_akshare_version(monkeypatch):
    """旧版 akshare 的公告签名不同，必须在调用前给出明确的版本提示。"""

    class OldAk:
        __version__ = "1.18.94"

    monkeypatch.setattr(akshare_source, "_akshare", lambda: OldAk())

    with pytest.raises(SourceUnavailable) as exc:
        akshare_source.fetch_stock_announcements("600519", "2026-09-01", "2026-09-30")

    message = str(exc.value)
    assert "1.20.65" in message
    assert "1.18.94" in message


def test_version_tuple_handles_rc_suffix():
    assert akshare_source._version_tuple("1.20.65rc1") == (1, 20, 65)
    assert akshare_source._version_tuple("1.18.94") < akshare_source._version_tuple("1.20.65")
