"""归因包的契约测试。"""

from __future__ import annotations

import pytest

from engine.attribution import HoldingPosition, compute_contributions
from engine.attribution._template import attribute


def test_types_are_instantiable() -> None:
    position = HoldingPosition(code="600519", name="贵州茅台", weight=0.0974, industry="食品饮料")
    assert position.weight == 0.0974


def test_contributions_skip_missing_returns() -> None:
    positions = [
        HoldingPosition(code="600519", name="贵州茅台", weight=0.1, period_return=0.05),
        HoldingPosition(code="000001", name="平安银行", weight=0.1, period_return=None),
    ]
    items = compute_contributions(positions)
    assert len(items) == 1
    assert items[0].contribution == pytest.approx(0.005)


def test_contributions_sorted_ascending() -> None:
    positions = [
        HoldingPosition(code="A", name="甲", weight=0.1, period_return=0.10),
        HoldingPosition(code="B", name="乙", weight=0.1, period_return=-0.10),
    ]
    items = compute_contributions(positions)
    assert items[0].code == "B"


def test_template_is_stub() -> None:
    with pytest.raises(NotImplementedError):
        attribute([])
