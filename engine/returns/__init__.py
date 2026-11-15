"""收益计算包：区间收益、组合收益、权重漂移。

本包只做算术，不发起网络请求。数据由调用方准备好后传入。
"""

from engine.returns.core import compute_interval_return, compute_weight_drift
from engine.returns.types import NavPoint, ReturnSummary

__all__ = ["NavPoint", "ReturnSummary", "compute_interval_return", "compute_weight_drift"]
