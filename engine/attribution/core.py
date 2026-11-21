"""归因计算实现。

compute_contributions 是最小贡献度算术；compute_attribution 是带对账的完整拆解。
归因只陈述数字事实，不解释原因、不给建议。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from engine.attribution.types import (
    AttributionResult,
    ContributionItem,
    HoldingPosition,
    IndustryBreakdown,
)

UNMAPPED_INDUSTRY = "未映射"
ATTRIBUTION_METHOD = "holding_contribution+industry+selection"
RECONCILE_TOLERANCE = 0.001


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


def period_return_from_bars(bars: Sequence[Mapping[str, Any]]) -> float | None:
    """区间收益 = 末收盘 / 首收盘 − 1。有效点不足两点或首价非正时返回 None。"""
    closes = [float(b["close"]) for b in bars if b.get("close") is not None]
    if len(closes) < 2 or closes[0] <= 0:
        return None
    return closes[-1] / closes[0] - 1.0


def compute_attribution(
    holdings: Sequence[HoldingPosition],
    quotes: Mapping[str, Sequence[Mapping[str, Any]]],
    industry_returns: Mapping[str, float],
    fund_return: float,
    month: str = "",
    *,
    quote_adjust: str = "none",
    weight_basis: str = "disclosed",
) -> AttributionResult:
    """把基金区间收益拆到持仓与行业，并显式给出残差。

    口径（见 docs/归因口径.md）：
      contribution   = weight × 个股区间收益
      industry_part  = weight × 行业区间收益
      selection_part = contribution − industry_part（恒等，不引入额外误差）
      residual       = 基金区间收益 − Σcontribution

    缺失行情的持仓被跳过并写入 notes，绝不填 0；行业缺失时第二层为 None。
    """
    if fund_return is None:
        raise ValueError("缺少基金区间收益，无法对账")
    total_weight = sum(p.weight for p in holdings)
    if total_weight > 1 + 1e-6:
        raise ValueError(f"持仓权重和 {total_weight:.4f} 超过 1")

    items: list[ContributionItem] = []
    missing: list[str] = []
    unmapped: list[str] = []
    without_industry_return: list[str] = []

    for position in holdings:
        value = position.period_return
        if value is None:
            value = period_return_from_bars(quotes.get(position.code, ()))
        if value is None:
            missing.append(position.code)
            continue

        period_return = round(value, 8)
        contribution = round(position.weight * period_return, 8)
        industry = position.industry
        if not industry:
            unmapped.append(position.code)

        industry_part: float | None = None
        selection_part: float | None = None
        industry_return = industry_returns.get(industry) if industry else None
        if industry_return is None:
            if industry:
                without_industry_return.append(industry)
        else:
            industry_part = round(position.weight * industry_return, 8)
            selection_part = round(contribution - industry_part, 8)

        items.append(
            ContributionItem(
                code=position.code,
                name=position.name,
                industry=industry,
                weight=round(position.weight, 8),
                period_return=period_return,
                contribution=contribution,
                industry_part=industry_part,
                selection_part=selection_part,
            )
        )

    items.sort(key=lambda x: (x.contribution, x.code))

    grouped: dict[str, list[ContributionItem]] = {}
    for item in items:
        grouped.setdefault(item.industry or UNMAPPED_INDUSTRY, []).append(item)

    industries = tuple(
        IndustryBreakdown(
            industry=name,
            weight=round(sum(i.weight for i in group), 8),
            contribution=round(sum(i.contribution for i in group), 8),
            codes=tuple(i.code for i in group),
        )
        for name, group in sorted(grouped.items())
    )

    accounted = round(sum(i.contribution for i in items), 8)
    residual = round(fund_return - accounted, 8)
    coverage = round(sum(i.weight for i in items), 8)

    notes: list[str] = []
    if weight_basis == "disclosed":
        notes.append("权重取最近一期披露值，未做区间前漂移")
    if quote_adjust != "qfq":
        notes.append(f"个股行情复权方式：{quote_adjust}，除权除息影响计入残差")
    if missing:
        notes.append(f"{len(missing)} 只持仓缺区间行情，未计入分项：{', '.join(missing)}")
    if unmapped:
        notes.append(f"{len(unmapped)} 只持仓未映射行业：{', '.join(unmapped)}")
    if without_industry_return:
        names = sorted(set(without_industry_return))
        notes.append(f"{', '.join(names)} 缺行业指数收益，第二层拆分缺失")
    notes.append("残差包含未披露持仓、债券、现金与费用，不摊薄到已知项")
    notes.append("仅陈列数字拆解，不构成因果判断或投资建议")

    return AttributionResult(
        month=month,
        items=tuple(items),
        industries=industries,
        total_contribution=accounted,
        residual_return=residual,
        notes=tuple(notes),
        method=ATTRIBUTION_METHOD,
        coverage=coverage,
    )
