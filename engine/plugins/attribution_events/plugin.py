"""相关事件插件：陈列与基金或披露持仓直接相关的可核验公开事件。

只陈列事实，不做因果判断、不标注正负面、不给建议。
没有通过筛选的事件时，明确显示空状态，不补内容。
"""

from __future__ import annotations

from engine.attribution import DISCLAIMER, EMPTY_TEXT, filter_events
from engine.runtime import AlgorithmPlugin, PluginContext, PluginResult


def run(ctx: PluginContext) -> PluginResult:
    raw = ctx.data.get("events") or []
    fund_code = str(ctx.fund.get("code", ""))
    holdings = ctx.data.get("holdings") or []
    holding_codes = [str(row["code"]) for row in holdings]

    kept, dropped = filter_events(raw, fund_code, holding_codes, ctx.month)
    items = [
        {
            "date": item.date,
            "title": item.title,
            "url": item.url,
            "source": item.source,
            "related_code": item.related_code,
            "event_type": item.event_type,
        }
        for item in kept
    ]

    notes: list[str] = []
    if dropped:
        notes.append(f"{dropped} 条公告未通过可核验或直接相关筛选，未展示")
    if not items:
        notes.append(EMPTY_TEXT)
    notes.append(DISCLAIMER)

    return PluginResult(
        status="ready",
        data={"count": len(items), "dropped": dropped, "items": items},
        notes=tuple(notes),
    )


PLUGIN = AlgorithmPlugin(
    id="attribution.events",
    title="相关事件",
    run=run,
    version="0.3.0",
    status="ready",
    description="陈列与基金或披露持仓直接相关、可溯源的公开公告，不做因果判断",
    inputs="events[{date, title, url, source, related_code, event_type}], holdings, fund.code",
    outputs="{count, dropped, items[{date, title, url, source, related_code, event_type}]}",
    owner="组长",
    tags=("attribution", "events"),
)
