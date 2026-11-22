"""持仓变动：口径选择与差异计算。"""

from __future__ import annotations

import pytest

from data_pipeline.cache.store import MemoryCache
from data_pipeline.fallback import SourceChain
from data_pipeline.service import DataService
from data_pipeline.sources.akshare_source import SourceUnavailable
from engine.holdings import (
    build_periods,
    compute_holding_changes,
    select_comparable_periods,
)


def row(code: str, weight: float, quarter: str, name: str = "", industry: str = "") -> dict:
    return {
        "code": code,
        "name": name or code,
        "weight": weight,
        "quarter": quarter,
        "industry": industry,
    }


def test_build_periods_sorted_desc_and_typed():
    rows = [
        row("A", 0.1, "2026年1季度股票投资明细"),
        row("B", 0.09, "2026年3季度股票投资明细"),
        row("C", 0.08, "2026年2季度股票投资明细"),
    ] + [row(f"X{i}", 0.001, "2026年2季度股票投资明细") for i in range(24)]

    periods = build_periods(rows)

    assert [p.quarter for p in periods] == [
        "2026年3季度股票投资明细",
        "2026年2季度股票投资明细",
        "2026年1季度股票投资明细",
    ]
    assert periods[0].disclosure_type == "top10"
    assert periods[1].disclosure_type == "full"  # 27 条，中报全持仓


def test_select_periods_truncates_both_when_mixed():
    periods = build_periods(
        [row(f"A{i}", 0.2 - i * 0.01, "2026年3季度股票投资明细") for i in range(13)]
        + [row(f"B{i}", 0.1 - i * 0.001, "2026年2季度股票投资明细") for i in range(48)]
    )
    current, previous, note = select_comparable_periods(periods)

    assert len(current) == 10
    assert len(previous) == 10
    assert "前 10 大" in note
    # 截取时按权重降序
    assert current[0]["code"] == "A0"
    assert previous[0]["code"] == "B0"


def test_select_periods_always_top10_even_when_both_full():
    """两期都是全持仓时也统一到前十大，避免口径漂移。"""
    periods = build_periods(
        [row(f"A{i}", 0.01, "2026年2季度股票投资明细") for i in range(25)]
        + [row(f"B{i}", 0.01, "2025年4季度股票投资明细") for i in range(25)]
    )
    current, previous, note = select_comparable_periods(periods)
    assert len(current) == 10
    assert len(previous) == 10
    assert "前 10 大" in note


def test_select_periods_without_previous_is_explicit():
    periods = build_periods([row("A", 0.1, "2026年3季度股票投资明细")])
    current, previous, note = select_comparable_periods(periods)
    assert current == []
    assert previous == []
    assert "未披露" in note


def test_changes_cover_all_statuses():
    previous = [
        row("A", 0.10, "Q1", "甲"),
        row("B", 0.05, "Q1", "乙"),
        row("C", 0.02, "Q1", "丙"),
        row("E", 0.01, "Q1", "戊"),
    ]
    current = [
        row("A", 0.12, "Q3", "甲"),
        row("B", 0.03, "Q3", "乙"),
        row("D", 0.04, "Q3", "丁"),
        row("E", 0.01, "Q3", "戊"),
    ]

    changes = {item.code: item for item in compute_holding_changes(previous, current)}

    assert changes["A"].status == "increased"
    assert changes["A"].delta == pytest.approx(0.02)
    assert changes["B"].status == "decreased"
    assert changes["B"].delta == pytest.approx(-0.02)
    assert changes["C"].status == "removed"
    assert changes["C"].delta == pytest.approx(-0.02)
    assert changes["D"].status == "added"
    assert changes["D"].delta == pytest.approx(0.04)
    assert changes["E"].status == "unchanged"


def test_changes_sorted_by_absolute_delta():
    previous = [row("A", 0.10, "Q1")]
    current = [row("A", 0.11, "Q3"), row("B", 0.05, "Q3")]
    changes = compute_holding_changes(previous, current)
    assert [item.code for item in changes] == ["B", "A"]
    assert [round(item.delta, 4) for item in changes] == [0.05, 0.01]


def test_changes_tolerance_absorbs_float_noise():
    previous = [row("A", 0.1, "Q1")]
    current = [row("A", 0.1000001, "Q3")]
    changes = compute_holding_changes(previous, current)
    assert changes[0].status == "unchanged"


def test_changes_keep_missing_industry_empty():
    previous = [row("A", 0.1, "Q1")]
    current = [row("A", 0.12, "Q3")]
    assert compute_holding_changes(previous, current)[0].industry == ""


def test_service_periods_reuses_cache():
    calls: list[str] = []
    rows = [
        row("A", 0.1, "2026年1季度股票投资明细"),
        row("B", 0.09, "2026年3季度股票投资明细"),
    ]

    def fetch(code, year):
        calls.append(year)
        return rows

    service = DataService(
        cache=MemoryCache(),
        nav_chain=SourceChain("净值", [("x", lambda c: [])]),
        holdings_chain=SourceChain("持仓", [("fake", fetch)]),
    )
    periods, meta = service.get_holdings_periods("110022", "2026")
    assert [p["quarter"] for p in periods][0] == "2026年3季度股票投资明细"
    assert meta["periods"] == 2

    service.get_holdings_periods("110022", "2026")
    assert calls == ["2026"], "第二次应命中缓存"
    service.close()


def test_service_periods_degrades_without_raising():
    def fail(code, year):
        raise SourceUnavailable("offline")

    service = DataService(
        cache=MemoryCache(),
        nav_chain=SourceChain("净值", [("x", lambda c: [])]),
        holdings_chain=SourceChain("持仓", [("fake", fail)]),
    )
    periods, meta = service.get_holdings_periods("110022", "2026")
    assert periods == []
    assert meta["source"] == "unavailable"
    assert meta["attempts"]
    service.close()
