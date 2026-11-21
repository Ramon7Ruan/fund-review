"""收益计算实现。

约定：所有函数都是纯函数，输入相同则输出相同，不读取全局状态。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from engine.returns.types import (
    NavPoint,
    PortfolioContribution,
    PortfolioReturn,
    ReturnSummary,
)


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


def compute_portfolio_return(
    weights: Mapping[str, float],
    index_map: Mapping[str, Sequence[Mapping[str, Any]]],
    month: str,
) -> PortfolioReturn:
    """组合收益 = Σ(期初权重 × 单基金复权收益)。

    weights: {基金代码: 期初权重}，权重和 ≤ 1，差额为现金。
    index_map: {基金代码: [{date, total_return_index}]}，当月复权序列。
    月内持仓变动请用 compute_segmented_portfolio_return。
    """
    if not weights:
        return PortfolioReturn(
            month=month,
            total_return=0.0,
            contributions=(),
            cash_weight=1.0,
            residual_return=0.0,
            notes=("组合为空",),
        )

    total_weight = sum(weights.values())
    if total_weight > 1 + 1e-6:
        raise ValueError(f"组合权重和 {total_weight:.4f} 超过 1")
    if any(w < 0 for w in weights.values()):
        raise ValueError("权重不能为负")

    cash_weight = 1.0 - total_weight
    contributions: list[PortfolioContribution] = []
    notes: list[str] = []
    total_return = 0.0

    for code, weight in sorted(weights.items()):
        rows = index_map.get(code, [])
        if len(rows) < 2:
            notes.append(f"{code} 当月复权序列不足两点，收益记 0")
            period_return = 0.0
        else:
            period_return = rows[-1]["total_return_index"] / rows[0]["total_return_index"] - 1.0
        contribution = weight * period_return
        contributions.append(
            PortfolioContribution(
                fund_code=code,
                weight=round(weight, 8),
                period_return=round(period_return, 8),
                contribution=round(contribution, 8),
            )
        )
        total_return += contribution

    return PortfolioReturn(
        month=month,
        total_return=round(total_return, 8),
        contributions=tuple(contributions),
        cash_weight=round(cash_weight, 8),
        residual_return=0.0,
        notes=tuple(notes),
    )


def compute_segmented_portfolio_return(
    snapshots: Sequence[Mapping[str, Any]],
    index_map: Mapping[str, Sequence[Mapping[str, Any]]],
    month: str,
) -> PortfolioReturn:
    """月内持仓变动时，按快照分段加权，段间几何链接。

    snapshots: [{as_of, positions: [{code, weight}]}]，按 as_of 排序。
    新增持仓在该段快照中出现即参与；清仓持仓在后续快照中消失即停止。
    每段单独对账，段收益几何链接：R_total = ∏(1 + R_segment) - 1。
    """
    if not snapshots:
        return PortfolioReturn(month=month, notes=("无快照，无法分段",))

    all_dates = sorted({p["date"] for rows in index_map.values() for p in rows})
    if len(all_dates) < 2:
        return PortfolioReturn(month=month, notes=("净值序列不足两点",))

    ordered = sorted(snapshots, key=lambda s: s["as_of"])

    # 分段边界：首日 + 月内快照日 + 末日
    bounds = [all_dates[0]]
    for snap in ordered:
        day = snap["as_of"]
        if all_dates[0] < day <= all_dates[-1]:
            bounds.append(day)
    bounds.append(all_dates[-1])
    bounds = sorted(set(bounds))

    segments: list[dict] = []
    total_return = 1.0
    notes: list[str] = []

    for i in range(len(bounds) - 1):
        start, end = bounds[i], bounds[i + 1]
        if start == end:
            continue

        # 该段期初权重：as_of <= start 的最新快照
        eligible = [s for s in ordered if s["as_of"] <= start]
        snap = eligible[-1] if eligible else ordered[0]
        weights = {p["code"]: p["weight"] for p in snap["positions"]}

        seg_map = {}
        for code, rows in index_map.items():
            seg_map[code] = [p for p in rows if start <= p["date"] <= end]

        seg = compute_portfolio_return(weights, seg_map, month)
        segments.append(
            {
                "start_date": start,
                "end_date": end,
                "weights": weights,
                "period_return": seg.total_return,
                "cash_weight": seg.cash_weight,
                "notes": list(seg.notes),
            }
        )
        total_return *= 1.0 + seg.total_return
        notes.extend(seg.notes)

    total_return -= 1.0

    return PortfolioReturn(
        month=month,
        total_return=round(total_return, 8),
        contributions=(),
        cash_weight=0.0,
        residual_return=0.0,
        notes=tuple(notes),
        segments=tuple(segments),
    )
