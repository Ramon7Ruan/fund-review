"""归因计算实现。

v0.1 只提供贡献度的基础算术，Brinson 与行业拆解由插件接入。
"""

from __future__ import annotations

from collections.abc import Sequence

from engine.attribution.types import ContributionItem, HoldingPosition


def compute_contributions(positions: Sequence[HoldingPosition]) -> tuple[ContributionItem, ...]:
    """计算单只资产的贡献度：contribution = weight * period_return。

    缺少区间收益的持仓会被跳过，由调用方以残差项说明。
    """
    items: list[ContributionItem] = []
    for p in positions:
        if p.period_return is None:
            continue
        items.append(
            ContributionItem(
                code=p.code,
                name=p.name,
                industry=p.industry,
                weight=round(p.weight, 8),
                period_return=round(p.period_return, 8),
                contribution=round(p.weight * p.period_return, 8),
            )
        )
    items.sort(key=lambda x: x.contribution)
    return tuple(items)
