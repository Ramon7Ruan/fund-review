"""分段组合收益测试：新增、清仓、权重调整、几何链接。"""

from __future__ import annotations

import pytest

from engine.returns.core import compute_segmented_portfolio_return


def _nav(dates: list[str], values: list[float]) -> list[dict]:
    return [
        {"date": d, "total_return_index": v} for d, v in zip(dates, values, strict=True)
    ]


def test_single_snapshot_single_segment() -> None:
    snapshots = [
        {
            "as_of": "2026-09-30",
            "positions": [
                {"code": "A", "weight": 0.5},
                {"code": "B", "weight": 0.5},
            ],
        }
    ]
    index_map = {
        "A": _nav(["2026-10-01", "2026-10-15", "2026-10-30"], [1.0, 1.1, 1.155]),
        "B": _nav(["2026-10-01", "2026-10-15", "2026-10-30"], [1.0, 0.95, 0.855]),
    }
    result = compute_segmented_portfolio_return(snapshots, index_map, "2026-10")

    # 单快照在月初之前，不产生分段边界，只有一段
    # 全月：0.5×(1.155-1) + 0.5×(0.855-1) = 0.0775 - 0.0725 = 0.005
    assert len(result.segments) == 1
    assert result.total_return == pytest.approx(0.005, abs=1e-6)


def test_weight_rebalance_across_segments() -> None:
    snapshots = [
        {
            "as_of": "2026-09-30",
            "positions": [
                {"code": "A", "weight": 0.5},
                {"code": "B", "weight": 0.5},
            ],
        },
        {
            "as_of": "2026-10-15",
            "positions": [
                {"code": "A", "weight": 0.6},
                {"code": "B", "weight": 0.4},
            ],
        },
    ]
    index_map = {
        "A": _nav(["2026-10-01", "2026-10-15", "2026-10-30"], [1.0, 1.1, 1.155]),
        "B": _nav(["2026-10-01", "2026-10-15", "2026-10-30"], [1.0, 0.95, 0.855]),
    }
    result = compute_segmented_portfolio_return(snapshots, index_map, "2026-10")

    # 第一段：0.5×0.1 + 0.5×(-0.05) = 0.025
    # 第二段：0.6×0.05 + 0.4×(-0.1) = -0.01
    # 几何链接：(1.025)(0.99) - 1 = 0.01475
    assert len(result.segments) == 2
    assert result.segments[0]["period_return"] == pytest.approx(0.025, abs=1e-6)
    assert result.segments[1]["period_return"] == pytest.approx(-0.01, abs=1e-6)
    assert result.total_return == pytest.approx(0.01475, abs=1e-6)


def test_new_position_appears_in_later_segment() -> None:
    snapshots = [
        {
            "as_of": "2026-09-30",
            "positions": [{"code": "A", "weight": 1.0}],
        },
        {
            "as_of": "2026-10-15",
            "positions": [
                {"code": "A", "weight": 0.5},
                {"code": "B", "weight": 0.5},
            ],
        },
    ]
    index_map = {
        "A": _nav(["2026-10-01", "2026-10-15", "2026-10-30"], [1.0, 1.1, 1.155]),
        "B": _nav(["2026-10-01", "2026-10-15", "2026-10-30"], [1.0, 0.95, 0.855]),
    }
    result = compute_segmented_portfolio_return(snapshots, index_map, "2026-10")

    # 第一段：只有 A，1.0×0.1 = 0.1
    # 第二段：A 0.5×0.05 + B 0.5×(-0.1) = -0.025
    # 几何链接：(1.1)(0.975) - 1 = 0.0725
    assert result.segments[0]["period_return"] == pytest.approx(0.1, abs=1e-6)
    assert result.segments[1]["period_return"] == pytest.approx(-0.025, abs=1e-6)
    assert result.total_return == pytest.approx(0.0725, abs=1e-6)


def test_position_closed_in_later_segment() -> None:
    snapshots = [
        {
            "as_of": "2026-09-30",
            "positions": [
                {"code": "A", "weight": 0.5},
                {"code": "B", "weight": 0.5},
            ],
        },
        {
            "as_of": "2026-10-15",
            "positions": [{"code": "A", "weight": 1.0}],
        },
    ]
    index_map = {
        "A": _nav(["2026-10-01", "2026-10-15", "2026-10-30"], [1.0, 1.1, 1.155]),
        "B": _nav(["2026-10-01", "2026-10-15", "2026-10-30"], [1.0, 0.95, 0.855]),
    }
    result = compute_segmented_portfolio_return(snapshots, index_map, "2026-10")

    # 第一段：0.5×0.1 + 0.5×(-0.05) = 0.025
    # 第二段：清仓 B，1.0×0.05 = 0.05
    # 几何链接：(1.025)(1.05) - 1 = 0.07625
    assert result.segments[1]["weights"] == {"A": 1.0}
    assert result.segments[1]["period_return"] == pytest.approx(0.05, abs=1e-6)
    assert result.total_return == pytest.approx(0.07625, abs=1e-6)


def test_geometric_linking_not_arithmetic() -> None:
    """段间必须几何链接，不能算术相加。"""
    snapshots = [
        {
            "as_of": "2026-09-30",
            "positions": [{"code": "A", "weight": 1.0}],
        }
    ]
    index_map = {
        "A": _nav(["2026-10-01", "2026-10-15", "2026-10-30"], [1.0, 1.1, 1.21]),
    }
    result = compute_segmented_portfolio_return(snapshots, index_map, "2026-10")

    # 两段各 10%，几何链接：(1.1)(1.1) - 1 = 0.21
    assert result.total_return == pytest.approx(0.21, abs=1e-6)
