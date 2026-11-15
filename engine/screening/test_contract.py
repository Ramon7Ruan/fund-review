"""异动检测包的契约测试。"""

from __future__ import annotations

import pytest

from engine.screening import Anomaly, AnomalyRule, detect_anomalies
from engine.screening._template import detect


def test_default_thresholds() -> None:
    rule = AnomalyRule()
    assert rule.price_move_pct == 0.05
    assert rule.volume_ratio == 2.0
    assert rule.relative_pct == 0.04
    assert rule.industry_top_n == 3


def test_anomaly_is_fact_only() -> None:
    anomaly = Anomaly(code="600519", name="贵州茅台", date="2026-10-15", kind="price", value=-0.062)
    assert anomaly.kind == "price"
    assert anomaly.note == ""


def test_detect_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        detect_anomalies({})


def test_template_is_stub() -> None:
    with pytest.raises(NotImplementedError):
        detect({})
