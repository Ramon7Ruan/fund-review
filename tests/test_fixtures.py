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
    points = [NavPoint(**p) for p in funds[code]["nav_series"]]
    summary = compute_interval_return(points)

    answer = expected[code]
    assert summary.period_return == pytest.approx(answer["period_return"], abs=1e-6)
    assert summary.max_drawdown == pytest.approx(answer["max_drawdown"], abs=1e-6)
    assert summary.points == answer["points"]


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
