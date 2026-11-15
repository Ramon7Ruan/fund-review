"""收益包的契约测试。

这些测试是组员实现算法时的验收靶子：
占位实现必须抛 NotImplementedError，已实现的部分必须有已知答案。
"""

from __future__ import annotations

import pytest

from engine.returns import NavPoint, compute_interval_return, compute_weight_drift
from engine.returns._template import estimate_something


def test_interval_return_known_answer() -> None:
    points = [
        NavPoint(date="2026-10-09", nav=2.0),
        NavPoint(date="2026-10-10", nav=2.2),
        NavPoint(date="2026-10-31", nav=2.1),
    ]
    summary = compute_interval_return(points)
    assert summary.start_nav == 2.0
    assert summary.end_nav == 2.1
    assert summary.period_return == pytest.approx(0.05)
    assert summary.max_drawdown == pytest.approx(2.1 / 2.2 - 1)
    assert summary.points == 3


def test_interval_return_sorts_by_date() -> None:
    points = [
        NavPoint(date="2026-10-31", nav=3.0),
        NavPoint(date="2026-10-01", nav=2.0),
    ]
    assert compute_interval_return(points).period_return == pytest.approx(0.5)


def test_interval_return_needs_two_points() -> None:
    with pytest.raises(ValueError):
        compute_interval_return([NavPoint(date="2026-10-01", nav=1.0)])


def test_weight_drift_keeps_total() -> None:
    drifted = compute_weight_drift(
        start_weights={"600519": 0.5, "000001": 0.5},
        period_returns={"600519": 0.2, "000001": 0.0},
        total_return=0.1,
    )
    assert sum(drifted.values()) == pytest.approx(1.0, abs=1e-6)


def test_template_is_stub() -> None:
    with pytest.raises(NotImplementedError):
        estimate_something([])
