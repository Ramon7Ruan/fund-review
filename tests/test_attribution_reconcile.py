"""归因核心：真实样本对账、两层拆分、缺失降级、可复现。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.attribution import (
    AttributionResult,
    HoldingPosition,
    compute_attribution,
    period_return_from_bars,
)
from engine.validation import validate_attribution

FIXTURES = Path(__file__).parent / "fixtures"
FUNDS = json.loads((FIXTURES / "funds.json").read_text(encoding="utf-8"))
QUOTES = json.loads((FIXTURES / "quotes.json").read_text(encoding="utf-8"))
INDUSTRIES = json.loads((FIXTURES / "industries.json").read_text(encoding="utf-8"))
INDUSTRY_MAP = json.loads((FIXTURES / "industry_map.json").read_text(encoding="utf-8"))["map"]


def fund_return(code: str) -> float:
    series = FUNDS[code]["nav_total_return"]
    return series[-1]["total_return_index"] / series[0]["total_return_index"] - 1.0


def industry_returns() -> dict[str, float]:
    out: dict[str, float] = {}
    for item in INDUSTRIES:
        bars = item["bars"]
        out[item["industry"]] = bars[-1]["close"] / bars[0]["close"] - 1.0
    return out


def quote_map() -> dict[str, list[dict]]:
    return {code: item["bars"] for code, item in QUOTES.items()}


def holdings_of(code: str, mapping: dict[str, str] | None = None) -> list[HoldingPosition]:
    mapping = INDUSTRY_MAP if mapping is None else mapping
    return [
        HoldingPosition(
            code=row["code"],
            name=row["name"],
            weight=row["weight"],
            industry=mapping.get(row["code"], ""),
        )
        for row in FUNDS[code]["holdings"]
    ]


@pytest.mark.parametrize("code", ["110022", "003095", "519674"])
def test_reconciles_on_real_fixtures(code):
    result = compute_attribution(
        holdings_of(code),
        quote_map(),
        industry_returns(),
        fund_return(code),
        "2026-10",
    )

    assert result.month == "2026-10"
    assert result.items, "至少应有可计算的持仓"
    assert abs(result.total_contribution + result.residual_return - fund_return(code)) < 1e-8
    assert abs(sum(i.contribution for i in result.items) - result.total_contribution) < 1e-8
    assert abs(sum(i.contribution for i in result.industries) - result.total_contribution) < 1e-8
    assert result.method == "holding_contribution+industry+selection"
    assert result.coverage == pytest.approx(
        sum(h["weight"] for h in FUNDS[code]["holdings"]), abs=1e-8
    )


@pytest.mark.parametrize("code", ["110022", "003095", "519674"])
def test_two_layer_split_is_additive(code):
    result = compute_attribution(
        holdings_of(code), quote_map(), industry_returns(), fund_return(code), "2026-10"
    )
    for item in result.items:
        assert item.industry_part is not None
        assert item.selection_part is not None
        assert item.industry_part + item.selection_part == pytest.approx(
            item.contribution, abs=1e-8
        )


def test_same_input_twice_gives_identical_result():
    kwargs = (
        holdings_of("110022"),
        quote_map(),
        industry_returns(),
        fund_return("110022"),
        "2026-10",
    )
    first = compute_attribution(*kwargs)
    second = compute_attribution(*kwargs)
    assert first == second


def test_missing_quote_is_skipped_and_disclosed():
    holdings = holdings_of("110022")
    quotes = quote_map()
    missing_code = holdings[0].code
    quotes.pop(missing_code)

    result = compute_attribution(
        holdings, quotes, industry_returns(), fund_return("110022"), "2026-10"
    )

    assert missing_code not in [i.code for i in result.items]
    assert any(missing_code in note for note in result.notes)
    assert result.coverage < sum(h.weight for h in holdings)


def test_missing_industry_return_disables_second_layer():
    result = compute_attribution(
        holdings_of("110022"), quote_map(), {}, fund_return("110022"), "2026-10"
    )
    assert all(i.industry_part is None for i in result.items)
    assert all(i.selection_part is None for i in result.items)
    assert any("第二层拆分缺失" in note for note in result.notes)
    # 第一层仍然可对账
    assert abs(result.total_contribution + result.residual_return - fund_return("110022")) < 1e-8


def test_unmapped_industry_grouped_explicitly():
    result = compute_attribution(
        holdings_of("110022", mapping={}), quote_map(), industry_returns(), fund_return("110022")
    )
    groups = {i.industry for i in result.industries}
    assert groups == {"未映射"}
    assert any("未映射行业" in note for note in result.notes)


def test_synthetic_full_coverage_has_zero_residual():
    holdings = [
        HoldingPosition(code="A", name="甲", weight=0.5, industry="食品饮料"),
        HoldingPosition(code="B", name="乙", weight=0.5, industry="电子"),
    ]
    quotes = {
        "A": [{"date": "2026-10-08", "close": 100}, {"date": "2026-10-30", "close": 110}],
        "B": [{"date": "2026-10-08", "close": 100}, {"date": "2026-10-30", "close": 90}],
    }
    result = compute_attribution(holdings, quotes, {"食品饮料": 0.05, "电子": 0.02}, 0.0)
    assert result.total_contribution == pytest.approx(0.0, abs=1e-8)
    assert result.residual_return == pytest.approx(0.0, abs=1e-8)
    assert result.coverage == pytest.approx(1.0)


def test_residual_is_not_spread_into_known_items():
    """前十大只覆盖部分权重，残差必须单独存在且随基金收益变化。"""
    holdings = holdings_of("110022")
    result = compute_attribution(holdings, quote_map(), industry_returns(), fund_return("110022"))
    assert result.residual_return != 0
    assert 0 < result.coverage < 1


def test_weight_sum_above_one_raises():
    holdings = [
        HoldingPosition(code="A", name="甲", weight=0.7, industry="电子"),
        HoldingPosition(code="B", name="乙", weight=0.4, industry="电子"),
    ]
    with pytest.raises(ValueError, match="超过 1"):
        compute_attribution(holdings, {}, {}, 0.0)


def test_period_return_needs_two_points():
    assert period_return_from_bars([{"date": "2026-10-30", "close": 10}]) is None
    assert period_return_from_bars([]) is None
    assert period_return_from_bars(
        [{"date": "2026-10-08", "close": 10}, {"date": "2026-10-30", "close": 12}]
    ) == pytest.approx(0.2)


def test_validate_attribution_accepts_result():
    expected = fund_return("110022")
    result: AttributionResult = compute_attribution(
        holdings_of("110022"), quote_map(), industry_returns(), expected
    )
    items = [{"code": i.code, "contribution": i.contribution} for i in result.items]
    report = validate_attribution(items, expected, result.residual_return)
    assert report.ok, report.errors
