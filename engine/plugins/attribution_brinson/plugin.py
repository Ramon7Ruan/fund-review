"""Brinson 归因插件（占位）。

status=stub 表示算法尚未接入。前端会显示统一的占位卡，
并在卡片上展示 inputs/outputs 契约，组员照着契约实现即可。
"""

from __future__ import annotations

from engine.runtime import AlgorithmPlugin, PluginContext, PluginResult


def run(ctx: PluginContext) -> PluginResult:
    return PluginResult.stub("Brinson 归因尚未接入：需持仓权重、个股收益与行业基准收益")


PLUGIN = AlgorithmPlugin(
    id="attribution.brinson",
    title="Brinson 归因",
    run=run,
    version="0.1.0",
    status="stub",
    description="把基金收益拆为行业配置、个股选择与交互项",
    inputs="positions[{code, name, weight, industry}], benchmark_returns{industry: r}",
    outputs="AttributionResult{items, industries, total_contribution, residual_return}",
    owner="待认领",
    tags=("attribution",),
)
