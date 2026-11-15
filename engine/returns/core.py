"""收益计算实现。

约定：所有函数都是纯函数，输入相同则输出相同，不读取全局状态。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from engine.returns.types import NavPoint, ReturnSummary


def compute_interval_return(points: Sequence[NavPoint]) -> ReturnSummary:
    """计算区间收益与最大回撤。

    净值点会先按日期排序，再取首尾计算区间收益。
    少于两个有效点时抛出 ValueError，由调用方决定如何展示。
    """
    cleaned = sorted(
        (p for p in points if p.nav is not None and p.nav > 0),
        key=lambda p: p.date,
    )
    if len(cleaned) < 2:
        raise ValueError("净值点不足两个，无法计算区间收益")

    start, end = cleaned[0], cleaned[-1]
    period_return = end.nav / start.nav - 1.0

    peak = cleaned[0].nav
    max_drawdown = 0.0
    for p in cleaned:
        peak = max(peak, p.nav)
        drawdown = p.nav / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)

    return ReturnSummary(
        start_date=start.date,
        end_date=end.date,
        start_nav=round(start.nav, 6),
        end_nav=round(end.nav, 6),
        period_return=round(period_return, 8),
        max_drawdown=round(max_drawdown, 8),
        points=len(cleaned),
    )


def compute_weight_drift(
    start_weights: Mapping[str, float],
    period_returns: Mapping[str, float],
    total_return: float,
) -> dict[str, float]:
    """按 buy-and-hold 方式推算期末权重。

    w_end,i = w_start,i * (1 + r_i) / (1 + R)
    其中 R 为组合区间收益。未披露部分不参与计算，由调用方以残差项呈现。

    本阶段为占位实现：结构已定，是否启用由接入方决定。
    """
    if not start_weights:
        return {}
    denominator = 1.0 + total_return
    if denominator <= 0:
        raise ValueError("组合区间收益异常，无法推算权重漂移")
    drifted: dict[str, float] = {}
    for code, weight in start_weights.items():
        r = period_returns.get(code, 0.0)
        drifted[code] = round(weight * (1.0 + r) / denominator, 8)
    return drifted
