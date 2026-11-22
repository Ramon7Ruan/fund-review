"""持仓变动的纯函数实现。

职责边界：
- 只处理已归一化的 L1 数据（dict/list），不抓取、不读数据库。
- 「选哪两期」和「怎么比较」都在这里，接口层只负责取数与组装。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from engine.holdings.types import ChangeStatus, HoldingChange, HoldingPeriod

TOP_N = 10
WEIGHT_TOLERANCE = 1e-6


def quarter_key(quarter: str) -> tuple[int, int]:
    """从「2026年3季度股票投资明细」提取 (2026, 3)；无法解析返回 (0, 0)。"""
    match = re.search(r"(\d{4})\D*?(\d)\s*季度", quarter)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 0, 0


def build_periods(rows: Sequence[Mapping[str, Any]]) -> tuple[HoldingPeriod, ...]:
    """把原始持仓行按披露期分组，时间倒序，并按条数标注口径。

    注意：季报「前十大」实际可能返回 11–15 条（含港股、存托凭证），
    所以条数只用于界面说明，不用于决定是否截取——比较时一律取前 TOP_N。
    """
    groups: dict[str, list[dict]] = {}
    for row in rows:
        quarter = str(row.get("quarter") or "").strip()
        if not quarter:
            continue
        groups.setdefault(quarter, []).append(dict(row))

    periods = [
        HoldingPeriod(
            quarter=quarter,
            disclosure_type="full" if len(positions) > 20 else "top10",
            positions=tuple(positions),
        )
        for quarter, positions in groups.items()
    ]
    periods.sort(key=lambda item: quarter_key(item.quarter), reverse=True)
    return tuple(periods)


def _top_positions(positions: Sequence[Mapping[str, Any]], top_n: int) -> list[dict]:
    ordered = sorted(positions, key=lambda row: float(row.get("weight") or 0), reverse=True)
    return [dict(row) for row in ordered[:top_n]]


def select_comparable_periods(
    periods: Sequence[HoldingPeriod], top_n: int = TOP_N
) -> tuple[list[dict], list[dict], str]:
    """选最近两期并统一按前 top_n 截取后比较。

    始终截取是刻意的：季报条数不固定（可能 11–15 条），中报是全持仓；
    只有统一到前十大，才不会把上期非重仓持仓误判为「清仓」。
    返回 (本期, 上期, 口径说明)。
    """
    if len(periods) < 2:
        return [], [], "上一期持仓未披露，无法计算变动"

    current, previous = periods[0], periods[1]
    return (
        _top_positions(current.positions, top_n),
        _top_positions(previous.positions, top_n),
        f"两期均按前 {top_n} 大截取后比较",
    )


def _normalize_code(value: Any) -> str:
    """纯数字代码补足 6 位；非数字（测试或特殊代码）保持原样。"""
    code = str(value).strip()
    return code.zfill(6) if code.isdigit() else code


def compute_holding_changes(
    previous: Sequence[Mapping[str, Any]],
    current: Sequence[Mapping[str, Any]],
    tolerance: float = WEIGHT_TOLERANCE,
) -> tuple[HoldingChange, ...]:
    """比较两期持仓，输出新增/清仓/增持/减持/持平。

    缺上一期时调用方不应调用本函数，避免把全部持仓标为新增。
    """
    prev_map = {_normalize_code(row["code"]): row for row in previous}
    curr_map = {_normalize_code(row["code"]): row for row in current}

    changes: list[HoldingChange] = []
    for code in sorted(set(prev_map) | set(curr_map)):
        prev_row = prev_map.get(code)
        curr_row = curr_map.get(code)
        previous_weight = round(float(prev_row.get("weight") or 0), 8) if prev_row else 0.0
        current_weight = round(float(curr_row.get("weight") or 0), 8) if curr_row else 0.0
        delta = round(current_weight - previous_weight, 8)

        status: ChangeStatus
        if prev_row is None:
            status = "added"
        elif curr_row is None:
            status = "removed"
        elif abs(delta) <= tolerance:
            status = "unchanged"
        elif delta > 0:
            status = "increased"
        else:
            status = "decreased"

        source = curr_row or prev_row or {}
        changes.append(
            HoldingChange(
                code=code,
                name=str(source.get("name") or code),
                industry=str(source.get("industry") or ""),
                current_weight=current_weight,
                previous_weight=previous_weight,
                delta=delta,
                status=status,
            )
        )

    changes.sort(key=lambda item: (-abs(item.delta), item.code))
    return tuple(changes)
