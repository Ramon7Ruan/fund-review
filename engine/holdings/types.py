"""持仓变动：把两期披露持仓按同口径比较。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ChangeStatus = Literal["added", "removed", "increased", "decreased", "unchanged"]


@dataclass(frozen=True)
class HoldingPeriod:
    """一期披露持仓。

    disclosure_type 由持仓条数判断：季报只披露前十大（top10），
    中报/年报披露全持仓（full）。两者直接比较会产生假清仓，必须先统一口径。
    """

    quarter: str
    disclosure_type: Literal["top10", "full"]
    positions: tuple[dict, ...]


@dataclass(frozen=True)
class HoldingChange:
    """单只持仓两期之间的变化。权重为占基金净值比例，小数。"""

    code: str
    name: str
    industry: str
    current_weight: float
    previous_weight: float
    delta: float
    status: ChangeStatus
