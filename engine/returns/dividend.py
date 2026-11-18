"""将单位净值和每份现金分红转换为红利再投资总回报指数。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def total_return_index(points: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """按日期顺序逐日复权；第一点锚定为 1。输入不变。"""
    result: list[dict[str, Any]] = []
    adjusted = 1.0
    previous: float | None = None
    for point in points:
        nav = float(point["unit_nav"])
        dividend = float(point["dividend_per_share"])
        if previous is not None:
            adjusted *= (nav + dividend) / previous
        result.append({**point, "total_return_index": adjusted})
        previous = nav
    return result
