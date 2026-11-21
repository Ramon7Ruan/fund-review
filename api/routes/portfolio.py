"""组合收益接口。

与单基金 /api/review 并列：接受多只基金与期初权重，返回组合区间收益。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_service
from api.schemas import PortfolioRequest, PortfolioResponse
from data_pipeline.service import DataService
from data_pipeline.sources.akshare_source import SourceUnavailable
from engine.returns import compute_portfolio_return

router = APIRouter(prefix="/api", tags=["portfolio"])


@router.post("/portfolio/review", response_model=PortfolioResponse)
def portfolio_review(
    payload: PortfolioRequest, service: DataService = Depends(get_service)
) -> PortfolioResponse:
    if not payload.weights:
        raise HTTPException(status_code=400, detail="组合不能为空")

    index_map: dict[str, list[dict]] = {}
    errors: list[str] = []
    meta: dict[str, Any] = {}

    for code in sorted(payload.weights):
        try:
            rows, nav_meta = service.get_nav_adjusted(code, payload.month)
            index_map[code] = rows
            meta[code] = {
                "source": nav_meta.get("source"),
                "dividend_source": nav_meta.get("dividend_source"),
                "fallback": nav_meta.get("fallback", False),
            }
        except SourceUnavailable as exc:
            errors.append(f"{code} 净值不可用：{exc}")
            index_map[code] = []

    try:
        result = compute_portfolio_return(payload.weights, index_map, payload.month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PortfolioResponse(
        month=result.month,
        total_return=result.total_return,
        contributions=[
            {
                "fund_code": c.fund_code,
                "weight": c.weight,
                "period_return": c.period_return,
                "contribution": c.contribution,
            }
            for c in result.contributions
        ],
        cash_weight=result.cash_weight,
        residual_return=result.residual_return,
        notes=list(result.notes),
        errors=errors,
        meta=meta,
    )
