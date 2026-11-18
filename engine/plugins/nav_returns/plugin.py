"""区间收益插件（已实现）。

这是"已接入"插件的样板：调用 engine.returns 的纯函数，把结果转成可序列化的 dict。
组员可以复制本目录结构，改成自己的算法。
"""

from __future__ import annotations

from engine.returns import NavPoint, compute_interval_return
from engine.runtime import AlgorithmPlugin, PluginContext, PluginResult


def run(ctx: PluginContext) -> PluginResult:
    adjusted = ctx.data.get("nav_total_return") or []
    raw = adjusted or ctx.data.get("nav_series") or []
    field = "total_return_index" if adjusted else "nav"
    points = [NavPoint(date=str(item["date"]), nav=float(item[field])) for item in raw]
    summary = compute_interval_return(points)
    return PluginResult(
        status="ready",
        data={
            "start_date": summary.start_date,
            "end_date": summary.end_date,
            "start_nav": (ctx.data.get("nav_series") or [{}])[0].get("nav", summary.start_nav),
            "end_nav": (ctx.data.get("nav_series") or [{}])[-1].get("nav", summary.end_nav),
            "period_return": summary.period_return,
            "max_drawdown": summary.max_drawdown,
            "points": summary.points,
        },
        notes=("区间收益按分红复权指数计算" if adjusted else "复权数据缺失，按单位净值计算",),
    )


PLUGIN = AlgorithmPlugin(
    id="returns.interval",
    title="区间收益",
    run=run,
    version="0.1.0",
    status="ready",
    description="按单位净值序列计算区间收益与最大回撤",
    inputs="nav_series: [{date, nav}]",
    outputs="{period_return, max_drawdown, start_nav, end_nav}",
    owner="组长",
    tags=("returns",),
)
