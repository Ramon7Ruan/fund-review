"""异动检测插件（占位）。"""

from __future__ import annotations

from engine.runtime import AlgorithmPlugin, PluginContext, PluginResult


def run(ctx: PluginContext) -> PluginResult:
    return PluginResult.stub("异动检测尚未接入：需个股行情与行业指数")


PLUGIN = AlgorithmPlugin(
    id="screening.anomaly",
    title="异动清单",
    run=run,
    version="0.1.0",
    status="stub",
    description="按价格、量能、相对、行业四类规则筛选本月异动",
    inputs="quotes{code: [{date, close, amount}]}, rule{price_move_pct, volume_ratio, ...}",
    outputs="Anomaly[{code, name, date, kind, value, note}]",
    owner="待认领",
    tags=("screening",),
)
