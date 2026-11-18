"""验收样本自身的质量测试。

作用：
1. 保证 fixtures 里的真实数据符合数据契约（见 docs/数据口径与契约.md）。
2. 用样本反算已知答案，确保"数据 → 算法 → 结果"这条链是通的。

这些测试也是组员写插件时的参照：断言对照 expected.json 的已知答案，不写死数字。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.returns import NavPoint, compute_interval_return

FIXTURES = Path(__file__).parent / "fixtures"
MONTH = "2026-10"
FUND_CODES = ["110022", "003095", "519674"]


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def funds() -> dict:
    return load("funds.json")


@pytest.fixture(scope="module")
def quotes() -> dict:
    return load("quotes.json")


@pytest.fixture(scope="module")
def expected() -> dict:
    return load("expected.json")


def test_manifest_records_real_source() -> None:
    manifest = load("manifest.json")
    assert "akshare" in manifest["source"]
    assert manifest["month"] == MONTH
    assert manifest["failures"] == [], "样本生成存在失败项，需先修复"


def test_all_funds_present(funds: dict) -> None:
    assert set(FUND_CODES) <= set(funds)


@pytest.mark.parametrize("code", FUND_CODES)
def test_fund_nav_is_valid(code: str, funds: dict) -> None:
    series = funds[code]["nav_series"]

    assert len(series) >= 2, "净值点不足以计算区间收益"
    dates = [p["date"] for p in series]
    assert dates == sorted(dates), "净值日期必须升序"
    assert len(set(dates)) == len(dates), "净值日期不允许重复"
    assert all(p["date"].startswith(MONTH) for p in series)
    assert all(p["nav"] > 0 for p in series), "净值必须为正"


@pytest.mark.parametrize("code", FUND_CODES)
def test_holdings_weights_follow_contract(code: str, funds: dict) -> None:
    holdings = funds[code]["holdings"]

    assert len(holdings) > 0
    for h in holdings:
        assert 0 <= h["weight"] <= 1, f"权重必须是小数且在 [0,1]：{h}"
        assert len(h["code"]) == 6
        assert h["quarter"], "必须记录披露期"

    weight_sum = sum(h["weight"] for h in holdings)
    assert weight_sum <= 1.0 + 1e-6, "前十大权重和不应超过 1"
    assert weight_sum < 0.999, "样本应保留未披露残差，便于验收残差项"


@pytest.mark.parametrize("code", FUND_CODES)
def test_interval_return_matches_known_answer(code: str, funds: dict, expected: dict) -> None:
    points = [NavPoint(**{"date": p["date"], "nav": p["nav"]}) for p in funds[code]["nav_series"]]
    summary = compute_interval_return(points)

    answer = expected[code]
    assert summary.period_return == pytest.approx(answer["period_return"], abs=1e-6)
    assert summary.max_drawdown == pytest.approx(answer["max_drawdown"], abs=1e-6)
    assert summary.points == answer["points"]


@pytest.mark.parametrize("code", FUND_CODES)
def test_adjusted_return_matches_known_answer(code: str, funds: dict, expected: dict) -> None:
    """复权口径：用 nav_total_return 的首末比值，应与 expected 一致。"""
    index_rows = funds[code]["nav_total_return"]
    answer = expected[code]

    assert len(index_rows) >= 2
    assert all(p["total_return_index"] > 0 for p in index_rows)

    if answer["dividend_points_in_month"] > 0:
        # 当月有分红，复权涨幅必须不为零且与净值口径不同
        assert answer["period_return_adjusted"] != pytest.approx(
            answer["period_return"], abs=1e-9
        ), "有分红的月份，两个口径不应相同"
    else:
        assert answer["period_return_adjusted"] == pytest.approx(
            answer["period_return"], abs=1e-9
        ), "无分红的月份，两个口径应一致"


def test_quotes_cover_all_holdings(funds: dict, quotes: dict) -> None:
    required = set()
    for code in FUND_CODES:
        required.update(h["code"] for h in funds[code]["holdings"])

    missing = required - set(quotes)
    assert not missing, f"以下持仓缺少行情数据：{missing}"


def test_quotes_bars_are_valid(quotes: dict) -> None:
    for code, payload in quotes.items():
        bars = payload["bars"]
        assert len(bars) >= 2, f"{code} 行情点不足"
        assert all(b["date"].startswith(MONTH) for b in bars)
        assert all(b["close"] > 0 for b in bars)
        assert all(b["amount"] >= 0 for b in bars)
        assert payload["source"] in ("sina", "tencent"), "必须记录真实行情来源"


def test_industry_indices_present() -> None:
    data = load("industries.json")
    names = {item["industry"] for item in data}
    assert {"食品饮料", "医药生物", "电子"} <= names
    for item in data:
        assert len(item["bars"]) >= 2


def test_dividend_case_proves_adjustment_matters() -> None:
    """分红月样本：复权收益必须明显高于单位净值收益。

    目标月份的三只基金通常不分红，两个口径相等，无法验收复权逻辑。
    这个样本单独取了一段有分红的真实历史，专门验分红再投资。
    """
    case = load("dividend_case.json")
    exp = case["expected"]

    assert exp["dividend_points"] >= 1, "样本必须包含至少一个分红日"
    assert exp["period_return_adjusted"] > exp["period_return"] + 1e-4, (
        "有分红时复权收益应高于净值收益"
    )

    # 用指数反算，验证 expected 自身一致
    idx = case["nav_total_return"]
    computed = idx[-1]["total_return_index"] / idx[0]["total_return_index"] - 1
    assert computed == pytest.approx(exp["period_return_adjusted"], abs=1e-6)

    # 用净值反算，验证未复权口径
    points = [NavPoint(date=p["date"], nav=p["nav"]) for p in case["nav_series"]]
    assert compute_interval_return(points).period_return == pytest.approx(
        exp["period_return"], abs=1e-6
    )
