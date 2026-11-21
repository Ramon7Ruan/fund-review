"""组合收益测试。

覆盖：等权、不等权、现金、空组合、越界、无数据、对账一致。
"""

from __future__ import annotations

import pytest

from engine.returns.core import compute_portfolio_return


def _index(code: str, start: float, end: float) -> list[dict]:
    """构造一条两点复权序列。"""
    return [
        {"date": "2026-10-01", "total_return_index": start},
        {"date": "2026-10-30", "total_return_index": end},
    ]


def test_equal_weight_portfolio() -> None:
    weights = {"110022": 0.5, "003095": 0.5}
    index_map = {
        "110022": _index("110022", 1.0, 1.10),
        "003095": _index("003095", 1.0, 0.90),
    }
    result = compute_portfolio_return(weights, index_map, "2026-10")

    # 0.5 × 10% + 0.5 × (-10%) = 0
    assert result.total_return == pytest.approx(0.0, abs=1e-6)
    assert result.cash_weight == pytest.approx(0.0, abs=1e-6)
    assert len(result.contributions) == 2
    # 按 code 排序：003095 在前，110022 在后
    assert result.contributions[0].contribution == pytest.approx(-0.05, abs=1e-6)
    assert result.contributions[1].contribution == pytest.approx(0.05, abs=1e-6)


def test_unequal_weight_with_cash() -> None:
    weights = {"110022": 0.4, "003095": 0.3}
    index_map = {
        "110022": _index("110022", 1.0, 1.20),
        "003095": _index("003095", 1.0, 1.05),
    }
    result = compute_portfolio_return(weights, index_map, "2026-10")

    # 0.4 × 20% + 0.3 × 5% = 8% + 1.5% = 9.5%
    assert result.total_return == pytest.approx(0.095, abs=1e-6)
    assert result.cash_weight == pytest.approx(0.3, abs=1e-6)

    # 对账：Σ contribution + cash × 0 + residual = total
    total = sum(c.contribution for c in result.contributions)
    assert total + result.cash_weight * 0 + result.residual_return == pytest.approx(
        result.total_return, abs=1e-6
    )


def test_empty_portfolio() -> None:
    result = compute_portfolio_return({}, {}, "2026-10")
    assert result.total_return == 0.0
    assert result.cash_weight == 1.0
    assert result.contributions == ()


def test_weight_sum_over_one_raises() -> None:
    with pytest.raises(ValueError, match="超过 1"):
        compute_portfolio_return({"A": 0.7, "B": 0.5}, {}, "2026-10")


def test_negative_weight_raises() -> None:
    with pytest.raises(ValueError, match="不能为负"):
        compute_portfolio_return({"A": -0.1}, {}, "2026-10")


def test_missing_data_fund_counts_zero() -> None:
    weights = {"110022": 0.6, "003095": 0.4}
    index_map = {"110022": _index("110022", 1.0, 1.10)}
    result = compute_portfolio_return(weights, index_map, "2026-10")

    assert result.total_return == pytest.approx(0.06, abs=1e-6)
    assert any("003095" in note for note in result.notes)
    # 排序后 003095 在前（无数据），110022 在后
    assert result.contributions[0].period_return == 0.0
    assert result.contributions[0].contribution == 0.0


def test_reconciliation_always_holds() -> None:
    weights = {"A": 0.3, "B": 0.2, "C": 0.1}
    index_map = {
        "A": _index("A", 1.0, 1.15),
        "B": _index("B", 1.0, 0.85),
        "C": _index("C", 1.0, 1.0),
    }
    result = compute_portfolio_return(weights, index_map, "2026-10")

    total = sum(c.contribution for c in result.contributions)
    assert total + result.cash_weight * 0 + result.residual_return == pytest.approx(
        result.total_return, abs=1e-8
    )
    assert result.cash_weight == pytest.approx(0.4, abs=1e-6)


# ---------- 真实样本验收 ----------


def test_real_fixtures_portfolio() -> None:
    """用 tests/fixtures 的三只真实基金构造等权组合。"""
    import json
    from pathlib import Path

    funds = json.loads(
        (Path(__file__).parent / "fixtures" / "funds.json").read_text(encoding="utf-8")
    )
    codes = ["110022", "003095", "519674"]
    index_map = {code: funds[code]["nav_total_return"] for code in codes}
    weights = {code: 1.0 / 3 for code in codes}

    result = compute_portfolio_return(weights, index_map, "2026-10")

    # 三只基金当月复权收益：+3.984064% / -7.159473% / -15.646462%
    # 等权组合 = 三者平均 = -6.273957%
    expected = (0.03984064 - 0.07159473 - 0.15646462) / 3
    assert result.total_return == pytest.approx(expected, abs=1e-6)
    assert len(result.contributions) == 3
    assert result.cash_weight == pytest.approx(0.0, abs=1e-6)

    # 对账：Σ contribution = total_return
    total = sum(c.contribution for c in result.contributions)
    assert total == pytest.approx(result.total_return, abs=1e-8)
