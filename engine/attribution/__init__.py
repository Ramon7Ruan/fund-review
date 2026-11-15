"""归因计算包：个股贡献度、行业拆解、Brinson。

v0.1 只有类型、样板与占位实现，算法由组员在 engine/plugins/ 下接入。
"""

from engine.attribution.core import compute_contributions
from engine.attribution.types import (
    AttributionResult,
    ContributionItem,
    HoldingPosition,
    IndustryBreakdown,
)

__all__ = [
    "AttributionResult",
    "ContributionItem",
    "HoldingPosition",
    "IndustryBreakdown",
    "compute_contributions",
]
