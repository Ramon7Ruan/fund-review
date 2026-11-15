"""可复制的异动检测样板。

组员新增检测规则时，复制本文件到自己目录，改函数体即可。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from engine.screening.types import Anomaly, AnomalyRule


def detect(
    quotes: Mapping[str, Sequence[Mapping[str, object]]],
    rule: AnomalyRule | None = None,
) -> tuple[Anomaly, ...]:
    """一句话说明这条规则。

    约定：
        1. 纯函数，不发起网络请求。
        2. 只描述事实（幅度、量能、排名），不解释原因、不给结论。
        3. 没有异动时返回空元组，不要返回 None。
    """
    raise NotImplementedError("请在此实现检测规则")
