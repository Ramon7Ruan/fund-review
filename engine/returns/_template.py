"""可复制的估算法样板。

组员新增收益类算法时，复制本文件到自己的目录，改函数体即可。
不要修改本文件本身。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from engine.returns.types import NavPoint, WeightDriftResult


def estimate_something(
    points: Sequence[NavPoint],
    params: Mapping[str, float] | None = None,
) -> WeightDriftResult:
    """一句话说明这个算法算什么。

    参数：
        points: 净值序列，已按日期升序。
        params: 可选参数，缺省值在函数内部给出。

    返回：
        WeightDriftResult，字段含义见 engine/returns/types.py。

    约定：
        1. 纯函数，不发起网络请求，不读写数据库。
        2. 输入不足时抛 ValueError，不要返回 None。
    """
    raise NotImplementedError("请在此实现算法")
