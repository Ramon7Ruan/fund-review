"""月度回顾聚合接口。

这是插件的唯一编排点：
1. 准备数据（净值、持仓），放进 PluginContext.data。
2. 逐个执行插件，任何单个插件失败只写进 errors，不影响其他插件。
3. 返回结构按插件 id 分区，新增插件不改变整体结构。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_service
from api.schemas import ReviewRequest, ReviewResponse
from data_pipeline.service import DataService
from data_pipeline.sources.akshare_source import SourceUnavailable
from engine.runtime import PluginContext, registry
from engine.validation import clean_nav_series, validate_holdings

router = APIRouter(prefix="/api", tags=["review"])


@router.post("/review", response_model=ReviewResponse)
def review(payload: ReviewRequest, service: DataService = Depends(get_service)) -> ReviewResponse:
    registry.ensure_loaded()

    errors: list[str] = []
    month = payload.month
    year = month[:4]

    try:
        fund = service.get_fund(payload.fund_code)
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"基金信息不可用：{exc}") from exc

    try:
        nav_series, nav_meta = service.get_nav(payload.fund_code, month)
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"净值数据不可用：{exc}") from exc

    if not nav_series:
        raise HTTPException(
            status_code=404,
            detail=f"{payload.fund_code} 在 {month} 没有净值数据，可能尚未披露或月份写错",
        )

    # 进入 engine 之前统一清洗：非法点剔除，不足两点则拒绝继续
    nav_series, nav_report = clean_nav_series(nav_series, month=month)
    errors.extend(nav_report.warnings)
    if not nav_report.ok:
        raise HTTPException(
            status_code=404,
            detail=f"{payload.fund_code} 在 {month} 的净值数据无法用于计算："
            + "；".join(nav_report.errors),
        )

    nav_total_return, tr_meta = service.get_nav_adjusted(payload.fund_code, month)
    errors.extend(tr_meta.get("warnings", []))

    holdings: list[dict] = []
    holdings_meta: dict = {}
    try:
        holdings, holdings_meta = service.get_holdings(payload.fund_code, year, month)
    except SourceUnavailable as exc:
        errors.append(f"持仓数据不可用：{exc}")

    # 持仓问题不阻塞主流程，但必须写进 errors，不允许静默
    holdings_report = validate_holdings(holdings)
    errors.extend(holdings_report.errors)
    errors.extend(holdings_report.warnings)

    ctx = PluginContext(
        fund=fund,
        month=month,
        data={
            "nav_series": nav_series,
            "nav_total_return": nav_total_return,
            "holdings": holdings,
            "quotes": {},
            "benchmark_returns": {},
        },
    )

    results: dict[str, dict] = {}
    for item in registry.all():
        plugin_id = item.id
        meta = item.describe()
        result, error = registry.execute_safely(plugin_id, ctx)
        if error is not None:
            errors.append(error)
            results[plugin_id] = {
                "status": "error",
                "title": meta["title"],
                "data": {},
                "notes": [],
                "error": error,
            }
            continue
        assert result is not None
        results[plugin_id] = {
            "status": result.status,
            "title": meta["title"],
            "data": dict(result.data),
            "notes": [*result.notes, *tr_meta.get("warnings", [])],
            "error": None,
        }

    return ReviewResponse(
        fund=fund,
        month=month,
        nav_series=nav_series,
        holdings=holdings,
        results=results,
        plugins=registry.describe(),
        errors=errors,
        meta={"nav": nav_meta, "nav_total_return": tr_meta, "holdings": holdings_meta},
    )
