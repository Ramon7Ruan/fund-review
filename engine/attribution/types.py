"""归因计算的数据类型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HoldingPosition:
    """一只持仓。weight 为占基金净值比例，用小数表示（0.0974 而非 9.74）。"""

    code: str
    name: str
    weight: float
    industry: str = ""
    period_return: float | None = None


@dataclass(frozen=True)
class ContributionItem:
    """单只资产对基金区间收益的贡献。contribution = weight * period_return。

    industry_part / selection_part 为可选的第二层拆分：
      industry_part  = weight * 行业区间收益
      selection_part = weight * (个股区间收益 - 行业区间收益)
    两者之和恒等于 contribution；行业收益缺失时为 None，不硬算。
    """

    code: str
    name: str
    industry: str
    weight: float
    period_return: float
    contribution: float
    industry_part: float | None = None
    selection_part: float | None = None


@dataclass(frozen=True)
class IndustryBreakdown:
    """行业汇总。"""

    industry: str
    weight: float
    contribution: float
    codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttributionResult:
    """一次归因的完整结果。

    residual_return 为未解释部分（未披露持仓、债券、现金、费用）。
    对账要求：sum(item.contribution) + residual_return ≈ 组合区间收益。
    """

    month: str = ""
    items: tuple[ContributionItem, ...] = ()
    industries: tuple[IndustryBreakdown, ...] = ()
    total_contribution: float = 0.0
    residual_return: float = 0.0
    notes: tuple[str, ...] = field(default_factory=tuple)
    method: str = "holding_contribution+industry+selection"
    coverage: float = 0.0
