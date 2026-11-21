"""收益计算的数据类型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NavPoint:
    """一个净值点。date 为 ISO 字符串 YYYY-MM-DD。"""

    date: str
    nav: float


@dataclass(frozen=True)
class ReturnSummary:
    """区间收益摘要。"""

    start_date: str
    end_date: str
    start_nav: float
    end_nav: float
    period_return: float
    max_drawdown: float
    points: int = 0


@dataclass(frozen=True)
class WeightDriftResult:
    """权重漂移结果：从期初权重推到期末权重。"""

    start_weights: dict[str, float] = field(default_factory=dict)
    end_weights: dict[str, float] = field(default_factory=dict)
    residual_weight: float = 0.0


@dataclass(frozen=True)
class PortfolioContribution:
    """单只基金对组合收益的贡献。"""

    fund_code: str
    weight: float
    period_return: float
    contribution: float


@dataclass(frozen=True)
class PortfolioReturn:
    """组合收益结果。

    对账：Σ contributions.contribution + cash_weight × 0 + residual_return = total_return
    """

    month: str = ""
    total_return: float = 0.0
    contributions: tuple[PortfolioContribution, ...] = ()
    cash_weight: float = 0.0
    residual_return: float = 0.0
    notes: tuple[str, ...] = ()
    segments: tuple[dict, ...] = ()  # 分段明细（v0.2 用）
