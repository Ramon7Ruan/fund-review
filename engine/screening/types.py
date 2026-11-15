"""异动检测的数据类型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AnomalyKind = Literal["price", "volume", "relative", "industry"]


@dataclass(frozen=True)
class AnomalyRule:
    """异动阈值。所有阈值集中在配置里，不散落在代码中。"""

    price_move_pct: float = 0.05
    volume_ratio: float = 2.0
    relative_pct: float = 0.04
    industry_top_n: int = 3


@dataclass(frozen=True)
class Anomaly:
    """一条异动记录。只描述事实，不解释原因。"""

    code: str
    name: str
    date: str
    kind: AnomalyKind
    value: float
    note: str = ""
