"""归因插件：把基金区间收益拆到持仓与行业。

只陈述数字事实，不解释原因、不给建议。数据不足时明确降级，不猜测。
"""

from __future__ import annotations

from typing import Any

from engine.attribution import HoldingPosition, compute_attribution
from engine.runtime import AlgorithmPlugin, PluginContext, PluginResult


def _fund_return(data: dict[str, Any]) -> tuple[float, str]:
    """优先用复权指数；缺失时退回单位净值并标注。"""
    adjusted = data.get("nav_total_return") or []
    if len(adjusted) >= 2:
        start = float(adjusted[0]["total_return_index"])
        end = float(adjusted[-1]["total_return_index"])
        if start > 0:
            return end / start - 1.0, "复权"
    raw = data.get("nav_series") or []
    if len(raw) >= 2:
        start = float(raw[0]["nav"])
        end = float(raw[-1]["nav"])
        if start > 0:
            return end / start - 1.0, "单位净值"
    raise ValueError("缺少可用于对账的区间收益")


def run(ctx: PluginContext) -> PluginResult:
    holdings_raw = ctx.data.get("holdings") or []
    quotes = ctx.data.get("quotes") or {}
    benchmark = ctx.data.get("benchmark_returns") or {}
    industry_map = ctx.data.get("industry_map") or {}

    if not holdings_raw:
        return PluginResult.stub("等待持仓数据接入")
    if not quotes:
        return PluginResult.stub("等待个股行情数据接入")

    holdings = [
        HoldingPosition(
            code=str(row["code"]),
            name=str(row.get("name", row["code"])),
            weight=float(row["weight"]),
            industry=str(row.get("industry") or industry_map.get(str(row["code"]), "")),
        )
        for row in holdings_raw
    ]

    try:
        fund_return, return_basis = _fund_return(dict(ctx.data))
        result = compute_attribution(
            holdings,
            quotes,
            benchmark,
            fund_return,
            month=ctx.month,
            quote_adjust=str(ctx.data.get("quote_adjust", "none")),
        )
    except ValueError as exc:
        return PluginResult.stub(f"归因数据不完整：{exc}")

    notes = list(result.notes)
    if return_basis != "复权":
        notes.append("复权指数缺失，基金收益按单位净值计算")

    return PluginResult(
        status="ready",
        data={
            "month": result.month,
            "fund_return": round(fund_return, 8),
            "total_contribution": result.total_contribution,
            "residual_return": result.residual_return,
            "coverage": result.coverage,
            "method": result.method,
            "items": [
                {
                    "code": item.code,
                    "name": item.name,
                    "industry": item.industry,
                    "weight": item.weight,
                    "period_return": item.period_return,
                    "contribution": item.contribution,
                    "industry_part": item.industry_part,
                    "selection_part": item.selection_part,
                }
                for item in result.items
            ],
            "industries": [
                {
                    "industry": group.industry,
                    "weight": group.weight,
                    "contribution": group.contribution,
                    "codes": list(group.codes),
                }
                for group in result.industries
            ],
        },
        notes=tuple(notes),
    )


PLUGIN = AlgorithmPlugin(
    id="attribution.brinson",
    title="收益拆解",
    run=run,
    version="0.3.0",
    status="ready",
    description="把区间收益拆为持仓贡献、行业贡献与个股超额，残差显式对账",
    inputs=(
        "holdings, quotes{code: bars}, industry_map{code: industry}, benchmark_returns{industry: r}"
    ),
    outputs="items[], industries[], total_contribution, residual_return, coverage",
    owner="组长",
    tags=("attribution",),
)
