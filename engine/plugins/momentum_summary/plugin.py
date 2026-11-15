"""示例插件（已实现）：统计区间内的涨跌天数分布。

这个目录是给组员看的完整样板 —— 后端算法 + 前端卡片 + 自动发现，
三样齐备，可以整目录复制后改名使用。
"""

from __future__ import annotations

from engine.runtime import AlgorithmPlugin, PluginContext, PluginResult


def run(ctx: PluginContext) -> PluginResult:
    raw = ctx.data.get("nav_series") or []
    points = sorted(
        ((str(item["date"]), float(item["nav"])) for item in raw),
        key=lambda x: x[0],
    )
    if len(points) < 2:
        return PluginResult(
            status="ready", data={"up_days": 0, "down_days": 0}, notes=("净值点不足",)
        )

    up = down = flat = 0
    changes: list[float] = []
    for prev, cur in zip(points, points[1:], strict=False):
        change = cur[1] / prev[1] - 1.0
        changes.append(change)
        if change > 0:
            up += 1
        elif change < 0:
            down += 1
        else:
            flat += 1

    best = max(changes)
    worst = min(changes)
    return PluginResult(
        status="ready",
        data={
            "up_days": up,
            "down_days": down,
            "flat_days": flat,
            "trading_days": len(changes),
            "best_day": round(best, 6),
            "worst_day": round(worst, 6),
            "up_ratio": round(up / len(changes), 4) if changes else 0.0,
        },
        notes=("示例插件：仅统计，不构成任何判断",),
    )


PLUGIN = AlgorithmPlugin(
    id="example.momentum_summary",
    title="涨跌天数分布（示例）",
    run=run,
    version="0.1.0",
    status="ready",
    description="统计区间内上涨、下跌、持平天数与最佳最差单日",
    inputs="nav_series: [{date, nav}]",
    outputs="{up_days, down_days, flat_days, best_day, worst_day, up_ratio}",
    owner="组长（示例）",
    tags=("example",),
)
