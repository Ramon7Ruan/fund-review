"""归因插件在 /api/review 中的接入与降级。"""

from __future__ import annotations

import json

from api.routes.review import review
from api.schemas import ReviewRequest
from data_pipeline.service import INDUSTRY_BARS_SNAPSHOT_PATH, DataService
from data_pipeline.sources import akshare_source
from data_pipeline.sources.akshare_source import SourceUnavailable
from tests.fakes import FakeService


def test_sw_snapshot_outage_still_produces_industry_attribution(monkeypatch):
    def offline(*args):
        raise SourceUnavailable("申万暂不可用")

    for name in ("fetch_sw_industries", "fetch_sw_constituents", "fetch_sw_index_bars"):
        monkeypatch.setattr(akshare_source, name, offline)
    service = FakeService()
    with_data = DataService()
    monkeypatch.setattr(service, "get_industry_map", with_data.get_industry_map)
    monkeypatch.setattr(service, "get_industry_returns", with_data.get_industry_returns)
    snapshot = json.loads(INDUSTRY_BARS_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    request = ReviewRequest(fund_code="110022", month=snapshot["window_end"][:7])
    try:
        response = review(request, service)
    finally:
        with_data.close()
    assert response.meta["industry_map"]["source"] == "snapshot:akshare.sw"
    assert response.meta["benchmark_returns"]["source"] == "snapshot:akshare.sw"
    assert response.results["attribution.brinson"].data["items"][0]["industry_part"] is not None


def test_attribution_plugin_ready_and_reconciled():
    response = review(ReviewRequest(fund_code="110022", month="2026-10"), FakeService())
    result = response.results["attribution.brinson"]

    assert result.status == "ready"
    assert result.data["items"], "应至少有一只持仓的贡献度"
    assert result.data["industries"], "应有行业汇总"
    assert (
        abs(
            result.data["total_contribution"]
            + result.data["residual_return"]
            - result.data["fund_return"]
        )
        < 1e-8
    )
    assert any("不构成因果" in note for note in result.notes)
    assert response.meta["quotes"]["adjust"] == "none"
    assert response.meta["industry_map"]["mapped"] == 1


def test_attribution_degrades_without_quotes():
    class NoQuotes(FakeService):
        def get_quotes(self, codes, month):
            return {}, {
                "source": "none",
                "adjust": "none",
                "requested": len(list(codes)),
                "count": 0,
                "cached": False,
                "missing": ["no quotes"],
            }

    response = review(ReviewRequest(fund_code="110022", month="2026-10"), NoQuotes())
    result = response.results["attribution.brinson"]
    assert result.status == "stub"
    assert "个股行情" in result.notes[0]
    # 其他插件不受影响
    assert response.results["returns.interval"].status == "ready"


def test_attribution_degrades_without_holdings():
    class NoHoldings(FakeService):
        def get_holdings(self, code, year, month=None):
            return [], {
                "source": "fake",
                "cached": False,
                "quarter": "",
                "count": 0,
                "attempts": [],
            }

    response = review(ReviewRequest(fund_code="110022", month="2026-10"), NoHoldings())
    result = response.results["attribution.brinson"]
    assert result.status == "stub"
    assert "持仓" in result.notes[0]


def test_industry_map_failure_keeps_other_partitions():
    class NoIndustry(FakeService):
        def get_industry_map(self, codes):
            from data_pipeline.sources.akshare_source import SourceUnavailable

            raise SourceUnavailable("offline")

    response = review(ReviewRequest(fund_code="110022", month="2026-10"), NoIndustry())
    assert response.results["attribution.brinson"].status == "ready"
    assert any("行业映射不可用" in item for item in response.errors)
    # 行业缺失时第二层为 None，但第一层仍可对账
    item = response.results["attribution.brinson"].data["items"][0]
    assert item["industry_part"] is None
