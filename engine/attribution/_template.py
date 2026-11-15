"""可复制的归因算法样板。

组员新增归因算法时，复制本文件到 engine/plugins/<你的插件名>/，改函数体即可。
不要修改本文件本身。
"""

from __future__ import annotations

from collections.abc import Sequence

from engine.attribution.types import AttributionResult, HoldingPosition


def attribute(
    positions: Sequence[HoldingPosition],
    benchmark_returns: dict[str, float] | None = None,
) -> AttributionResult:
    """一句话说明这个归因口径。

    参数：
        positions: 期末持仓，weight 用小数表示。
        benchmark_returns: 行业基准收益，键为行业名。

    返回：
        AttributionResult，对账要求 sum(contribution) + residual_return ≈ 组合收益。

    约定：
        1. 纯函数，不发起网络请求，不读写数据库。
        2. 必须在 notes 里写清口径与已知限制。
    """
    raise NotImplementedError("请在此实现归因算法")
