"""异动检测包：价格、量能、相对、行业四类规则。

v0.1 只有类型、样板与占位实现。
"""

from engine.screening.core import detect_anomalies
from engine.screening.types import Anomaly, AnomalyRule

__all__ = ["Anomaly", "AnomalyRule", "detect_anomalies"]
