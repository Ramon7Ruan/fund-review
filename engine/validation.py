"""数据校验：进入 engine 之前的守门人。

对应 `docs/数据口径与契约.md` 第 9 节。三条约定：

1. **不修改输入**。清洗函数返回新对象，原数据保持不变。
2. **能修的修，不能修的报错**。净值异常点剔除并记 warning；权重越界记 error。
3. **调用方决定严格程度**。默认返回 ValidationReport，需要强制失败时调 assert_valid。

组员写插件时可以信任 `ctx.data` 已过这层校验，不必重复写防御代码。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_TOLERANCE = 0.001  # 对账容差，见契约第 11 节
WEIGHT_EPS = 1e-6  # 浮点比较容差
RESIDUAL_MIN = 0.999  # 权重和高于此值视为"没有残差空间"
MIN_NAV_POINTS = 2

_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class ValidationReport:
    """校验结果。errors 非空表示数据不可用，warnings 表示已自动处理但需知会。"""

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: ValidationReport) -> ValidationReport:
        return ValidationReport(
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
        )


class ValidationError(ValueError):
    """数据不符合契约，且已无法自动修复。"""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        super().__init__("；".join(report.errors) or "数据校验失败")


def assert_valid(report: ValidationReport) -> None:
    """需要强制失败时使用：有 error 就抛 ValidationError。"""
    if not report.ok:
        raise ValidationError(report)


# ---------- 月份 ----------


def is_valid_month(month: str) -> bool:
    return bool(_MONTH_PATTERN.match(str(month)))


def validate_month(month: str) -> ValidationReport:
    if not is_valid_month(month):
        return ValidationReport(errors=(f"月份格式应为 YYYY-MM 且月份在 01-12 之间：{month!r}",))
    return ValidationReport()


# ---------- 净值序列 ----------


def clean_nav_series(
    points: Sequence[Mapping[str, Any]],
    month: str | None = None,
) -> tuple[list[dict[str, Any]], ValidationReport]:
    """清洗净值序列：剔除非法点、去重、排序，可选按月份过滤。

    返回 (清洗后的序列, 校验结果)。清洗后不足两个点时 errors 非空。
    """
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []

    for point in points:
        date = str(point.get("date", "")).strip()
        raw_nav = point.get("nav")

        if not date:
            warnings.append(f"净值点缺少日期，已剔除：{dict(point)}")
            continue

        try:
            nav = float(raw_nav)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            warnings.append(f"净值不是数字，已剔除：{date} {raw_nav!r}")
            continue

        if nav <= 0:
            warnings.append(f"净值非正，已剔除：{date} nav={nav}")
            continue

        if date in seen:
            warnings.append(f"净值日期重复，保留首个：{date}")
            continue

        seen.add(date)
        cleaned.append({"date": date, "nav": nav})

    cleaned.sort(key=lambda x: x["date"])

    if month:
        cleaned = [p for p in cleaned if p["date"].startswith(month)]

    if len(cleaned) < MIN_NAV_POINTS:
        errors.append(
            f"有效净值点不足 {MIN_NAV_POINTS} 个（当前 {len(cleaned)} 个），无法计算区间收益"
        )

    return cleaned, ValidationReport(tuple(errors), tuple(warnings))


# ---------- 持仓 ----------


def validate_holdings(holdings: Sequence[Mapping[str, Any]]) -> ValidationReport:
    """校验持仓：代码格式、权重范围、权重和与残差空间。"""
    errors: list[str] = []
    warnings: list[str] = []
    total = 0.0

    for item in holdings:
        code = str(item.get("code", "")).strip()
        if len(code) != 6 or not code.isdigit():
            errors.append(f"持仓代码应为 6 位数字：{code!r}")

        try:
            weight = float(item.get("weight", 0.0))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            errors.append(f"持仓权重不是数字：{code} {item.get('weight')!r}")
            continue

        if not 0 <= weight <= 1:
            errors.append(f"持仓权重越界，应在 [0,1]：{code} weight={weight}")

        total += weight

    if total > 1 + WEIGHT_EPS:
        errors.append(f"前十大权重和 {total:.4f} 超过 1，数据可能有误")
    elif holdings and total >= RESIDUAL_MIN:
        warnings.append(
            f"权重和 {total:.4f} 接近 1，未披露残差几乎为零，请确认披露口径是否为全部持仓"
        )

    return ValidationReport(tuple(errors), tuple(warnings))


# ---------- 归因对账 ----------


def validate_attribution(
    items: Sequence[Mapping[str, Any]],
    total_return: float,
    residual_return: float,
    tolerance: float = DEFAULT_TOLERANCE,
) -> ValidationReport:
    """对账：Σ贡献度 + 残差 应等于组合区间收益。

    items 里的 contribution 用小数，与 total_return 同量纲。
    """
    contribution = 0.0
    for item in items:
        try:
            contribution += float(item.get("contribution", 0.0))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            code = item.get("code")
            value = item.get("contribution")
            return ValidationReport(errors=(f"贡献度不是数字，无法对账：{code} {value!r}",))

    diff = contribution + float(residual_return) - float(total_return)
    if abs(diff) > tolerance:
        return ValidationReport(
            errors=(
                f"归因对账失败：分项和 {contribution:.6f} + 残差 {residual_return:.6f} "
                f"与组合收益 {total_return:.6f} 相差 {diff:.6f}，超过容差 {tolerance}",
            )
        )
    return ValidationReport()
