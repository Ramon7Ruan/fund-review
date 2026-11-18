"""数据校验层测试。

除了常规边界，最后几项会用 tests/fixtures 的真实样本过一遍校验，
确保"真实数据符合契约"这件事是被持续验证的。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.validation import (
    ValidationError,
    assert_valid,
    clean_nav_series,
    is_valid_month,
    validate_attribution,
    validate_holdings,
    validate_month,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------- 月份 ----------


@pytest.mark.parametrize("month", ["2026-10", "2026-01", "2026-12"])
def test_valid_month(month: str) -> None:
    assert is_valid_month(month)
    assert validate_month(month).ok


@pytest.mark.parametrize("month", ["2026-13", "2026-00", "2026-1", "26-10", "", "2026/10"])
def test_invalid_month(month: str) -> None:
    assert not is_valid_month(month)
    assert not validate_month(month).ok


# ---------- 净值 ----------


def test_clean_nav_sorts_and_keeps_valid_points() -> None:
    raw = [
        {"date": "2026-10-30", "nav": 1.1},
        {"date": "2026-10-08", "nav": 1.0},
    ]
    cleaned, report = clean_nav_series(raw)

    assert [p["date"] for p in cleaned] == ["2026-10-08", "2026-10-30"]
    assert report.ok
    assert report.warnings == ()


def test_clean_nav_drops_bad_points_with_warning() -> None:
    raw = [
        {"date": "2026-10-08", "nav": 1.0},
        {"date": "2026-10-09", "nav": -0.5},
        {"date": "2026-10-10", "nav": "abc"},
        {"date": "2026-10-13", "nav": 0},
        {"date": "2026-10-14", "nav": 1.2},
    ]
    cleaned, report = clean_nav_series(raw)

    assert len(cleaned) == 2
    assert report.ok
    assert len(report.warnings) == 3


def test_clean_nav_deduplicates_dates() -> None:
    raw = [
        {"date": "2026-10-08", "nav": 1.0},
        {"date": "2026-10-08", "nav": 9.9},
        {"date": "2026-10-09", "nav": 1.1},
    ]
    cleaned, report = clean_nav_series(raw)

    assert len(cleaned) == 2
    assert cleaned[0]["nav"] == 1.0, "重复日期应保留首个"
    assert any("重复" in w for w in report.warnings)


def test_clean_nav_filters_by_month() -> None:
    raw = [
        {"date": "2026-09-30", "nav": 1.0},
        {"date": "2026-10-08", "nav": 1.1},
        {"date": "2026-10-09", "nav": 1.2},
    ]
    cleaned, report = clean_nav_series(raw, month="2026-10")

    assert [p["date"] for p in cleaned] == ["2026-10-08", "2026-10-09"]
    assert report.ok


def test_clean_nav_requires_two_points() -> None:
    cleaned, report = clean_nav_series([{"date": "2026-10-08", "nav": 1.0}], month="2026-10")

    assert cleaned == [{"date": "2026-10-08", "nav": 1.0}]
    assert not report.ok
    assert "不足" in report.errors[0]


def test_clean_nav_does_not_mutate_input() -> None:
    raw = [
        {"date": "2026-10-30", "nav": 1.1},
        {"date": "2026-10-08", "nav": 1.0},
    ]
    snapshot = json.dumps(raw, ensure_ascii=False)
    clean_nav_series(raw)
    assert json.dumps(raw, ensure_ascii=False) == snapshot


# ---------- 持仓 ----------


def test_holdings_valid_with_residual() -> None:
    holdings = [
        {"code": "600519", "weight": 0.1},
        {"code": "000858", "weight": 0.09},
    ]
    report = validate_holdings(holdings)

    assert report.ok
    assert report.warnings == ()


def test_holdings_rejects_bad_code() -> None:
    report = validate_holdings([{"code": "60051", "weight": 0.1}])
    assert not report.ok
    assert "6 位数字" in report.errors[0]


def test_holdings_rejects_weight_out_of_range() -> None:
    report = validate_holdings([{"code": "600519", "weight": 1.2}])
    assert not report.ok
    assert "越界" in report.errors[0]


def test_holdings_rejects_weight_sum_over_one() -> None:
    report = validate_holdings(
        [
            {"code": "600519", "weight": 0.6},
            {"code": "000858", "weight": 0.6},
        ]
    )
    assert not report.ok
    assert "超过 1" in report.errors[0]


def test_holdings_warns_when_no_residual() -> None:
    report = validate_holdings([{"code": "600519", "weight": 1.0}])
    assert report.ok
    assert any("残差" in w for w in report.warnings)


def test_holdings_rejects_non_numeric_weight() -> None:
    report = validate_holdings([{"code": "600519", "weight": "abc"}])
    assert not report.ok


# ---------- 对账 ----------


def test_attribution_reconciles() -> None:
    items = [{"code": "A", "contribution": 0.02}, {"code": "B", "contribution": -0.005}]
    report = validate_attribution(items, total_return=0.035, residual_return=0.02)

    assert report.ok


def test_attribution_detects_mismatch() -> None:
    items = [{"code": "A", "contribution": 0.02}]
    report = validate_attribution(items, total_return=0.10, residual_return=0.0)

    assert not report.ok
    assert "对账失败" in report.errors[0]


def test_attribution_tolerance_boundary() -> None:
    items = [{"code": "A", "contribution": 0.02}]
    # 差 0.0009 < 0.001，应通过
    assert validate_attribution(items, total_return=0.0209, residual_return=0.0).ok
    # 差 0.0011 > 0.001，应失败
    assert not validate_attribution(items, total_return=0.0211, residual_return=0.0).ok


def test_assert_valid_raises() -> None:
    with pytest.raises(ValidationError):
        assert_valid(validate_holdings([{"code": "bad", "weight": 0.1}]))


# ---------- 真实样本必须符合契约 ----------


def test_real_fixtures_pass_validation() -> None:
    funds = json.loads((FIXTURES / "funds.json").read_text(encoding="utf-8"))

    for code, payload in funds.items():
        cleaned, report = clean_nav_series(payload["nav_series"], month=payload["month"])
        assert report.ok, f"{code} 净值未通过校验：{report.errors}"
        assert len(cleaned) == len(payload["nav_series"]), f"{code} 有净值点被剔除"

        holdings_report = validate_holdings(payload["holdings"])
        assert holdings_report.ok, f"{code} 持仓未通过校验：{holdings_report.errors}"
        assert holdings_report.warnings == (), f"{code} 持仓不应有 warning"
