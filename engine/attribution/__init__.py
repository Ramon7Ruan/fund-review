"""归因计算包：个股贡献度、行业拆解、两层拆分。"""

from engine.attribution.core import (
    ATTRIBUTION_METHOD,
    RECONCILE_TOLERANCE,
    UNMAPPED_INDUSTRY,
    compute_attribution,
    compute_contributions,
    period_return_from_bars,
)
from engine.attribution.events import (
    ADVICE_TERMS,
    DISCLAIMER,
    EMPTY_TEXT,
    EventItem,
    filter_events,
    has_advice_language,
)
from engine.attribution.types import (
    AttributionResult,
    ContributionItem,
    HoldingPosition,
    IndustryBreakdown,
)

__all__ = [
    "ADVICE_TERMS",
    "ATTRIBUTION_METHOD",
    "DISCLAIMER",
    "EMPTY_TEXT",
    "RECONCILE_TOLERANCE",
    "UNMAPPED_INDUSTRY",
    "AttributionResult",
    "ContributionItem",
    "EventItem",
    "HoldingPosition",
    "IndustryBreakdown",
    "compute_attribution",
    "compute_contributions",
    "filter_events",
    "has_advice_language",
    "period_return_from_bars",
]
